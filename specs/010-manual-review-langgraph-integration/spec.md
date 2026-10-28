# Feature Specification: LangGraph Native Human-in-the-Loop Checkpoint Integration

**Feature Branch**: `010-manual-review-langgraph-integration`  
**Created**: 2026-10-28  
**Status**: Draft  
**Input**: User description: "Integrar aprovação manual nativamente ao Checkpointer do LangGraph usando primitivas Human-in-the-Loop (interrupt/Command) para garantir persistência e retomada determinística após crash do container Docker"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Crash-Safe Approval Resume (Priority: P1)

The operator starts the pipeline against a YouTube URL. After the analysis phase, the pipeline pauses awaiting cut approval and displays the review URL in the terminal. The operator accesses the review interface in the browser, selects the approved cuts, and submits the decision. While the review server is waiting for input, the Docker container crashes (e.g., OOM or `docker restart`). Upon relaunching the container with the same URL and no `--restart` flag, the pipeline must resume from the approval checkpoint exactly — either serving the review page again if no decision was committed to disk, or reading the already-persisted `decision.json` and proceeding directly to the editor node without reprocessing the video.

**Why this priority**: This is the root architectural risk described in the issue. Without this, any crash during the review window forces a full pipeline rerun, wasting hours of transcription and LLM inference time and losing determinism guarantees.

**Independent Test**: Can be tested by running the pipeline to the review stage, sending `SIGKILL` to the container while the review server is running, restarting the container, and verifying that the pipeline resumes at the review or editor node — never at download/transcription.

**Acceptance Scenarios**:

1. **Given** the pipeline is paused at the review node with no `decision.json` present, **When** the container is killed and restarted with the same URL and no `--restart`, **Then** the pipeline resumes and serves the review page again at the same URL/port, preserving all generated previews and the `review.json` manifest.
2. **Given** `decision.json` has been written to the review directory (decision committed), **When** the container restarts, **Then** the pipeline reads the committed decision, skips the review server entirely, and proceeds directly to the editor node.
3. **Given** a completed run, **When** the container restarts with the same URL and no `--restart`, **Then** the pipeline logs "run already complete" and exits without reprocessing any node.
4. **Given** the pipeline is restarted with `--restart`, **When** it executes, **Then** it starts from the beginning, ignoring any existing checkpoint, decision, or review directory.

---

### User Story 2 - Synchronous Approval Server Decoupled from Graph Execution (Priority: P2)

The review web server must run **outside** the LangGraph execution thread. The graph's approval node must issue a native `interrupt()` and return control to the LangGraph runtime (and the SQLite checkpointer), not block the main thread in a `while` loop. The orchestrator then drives the external server in its own loop until the decision arrives, then resumes the graph with `Command(resume={...})`.

**Why this priority**: The current `approval_node` calling `wait_for_approval(...)` (which contains a blocking `while server.decision is None: server.handle_request()`) defeats the purpose of the LangGraph checkpointer — if the process is killed mid-loop, the interrupt state is never saved to SQLite before the decision is consumed.

**Independent Test**: Can be tested by inspecting the SQLite checkpoint immediately after the `approval_node` is reached and verifying the `__interrupt__` entry is present and the node's output is not committed yet.

**Acceptance Scenarios**:

1. **Given** the graph reaches the approval step, **When** `approval_node` executes, **Then** it calls `interrupt()` with the review directory path and returns without starting any HTTP server or blocking.
2. **Given** the graph has issued an `interrupt()`, **When** `app.invoke()` returns, **Then** the SQLite checkpoint contains the interrupt state and can be inspected with `app.get_state(config)`.
3. **Given** the orchestrator detects `snapshot.tasks` contains interrupt entries, **When** the external review server receives a valid POST to `/approve`, **Then** the orchestrator calls `app.invoke(Command(resume={"approved_ids": ids}), config=config)` to resume.

---

### User Story 3 - Decision Persistence Across Process Boundaries (Priority: P3)

The `decision.json` file written to the review directory acts as a crash-safe durability layer for the human decision. If the graph resumes from checkpoint and finds a `decision.json` already present for the current review directory, it must skip the HTTP server and inject the saved decision directly into the graph state via `Command(resume=...)`.

**Why this priority**: Covers the edge case where the review server received the POST and wrote `decision.json` but the process was killed before `app.invoke(Command(...))` could be called, leaving the SQLite checkpoint still in the interrupted state.

**Independent Test**: Can be tested by manually writing a valid `decision.json` to the review directory, then restarting the pipeline without `--restart`. The pipeline must not serve a review page and must proceed to the editor.

**Acceptance Scenarios**:

1. **Given** a valid `decision.json` exists in the review directory at resume time, **When** the orchestrator checks the interrupt state, **Then** it reads the file, validates it with `ApprovalDecision`, and calls `app.invoke(Command(resume={"approved_ids": ids}), config=config)` immediately.
2. **Given** a corrupted or missing `decision.json`, **When** the orchestrator resumes, **Then** it launches the review server to collect a fresh decision.

---

### Edge Cases

- What happens when `interrupt_before` is configured at compilation time but `approval_node` also calls `interrupt()` internally — does LangGraph double-interrupt or is one approach chosen?
- How does the system handle a `review_directory` path that no longer exists (e.g., volume unmounted) when resuming from checkpoint?
- What happens if two simultaneous container instances with the same `thread_id` try to resume from the same SQLite checkpoint concurrently?
- What happens if the user sends `--restart` while a `decision.json` exists — does the old decision directory get invalidated?
- How is a corrupted SQLite checkpoint (incomplete write during crash) handled at startup?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The `approval_node` in the LangGraph graph MUST use `interrupt()` from `langgraph.types` as its primary suspension mechanism, not a blocking `while` loop or `time.sleep`.
- **FR-002**: The `approval_node` MUST call `interrupt()` internally as the sole suspension mechanism. The graph MUST NOT be compiled with `interrupt_before=["approval"]` or any other compile-time pre-node interruption to eliminate double-interruption cycles.
- **FR-003**: The orchestrator MUST detect the interrupt state by inspecting `snapshot.tasks` after `app.invoke()` returns and drive the review HTTP server from outside the graph execution context.
- **FR-004**: The `decision.json` file MUST be written atomically (write to `.partial` then rename) before the HTTP server reports success to the browser, ensuring the decision survives a process crash.
- **FR-005**: When resuming from a checkpoint in interrupt state, the system MUST check for an existing valid `decision.json` before launching the review server, and if found, resume the graph immediately via `Command(resume={"approved_ids": ids})`.
- **FR-006**: The SQLite checkpoint (`estado.db`) MUST contain the interrupt snapshot before the review HTTP server starts accepting connections, so any crash after that point allows safe resumption.
- **FR-007**: The system MUST support resumption without `--restart` when the pipeline was killed in any of these states: (a) before the interrupt was issued, (b) during review server execution, (c) after `decision.json` was written but before `Command(resume=...)` was called.
- **FR-008**: The `--restart` flag MUST invalidate any existing checkpoint by purging all records for the target `thread_id` from the SQLite checkpointer (`checkpoints` and `writes` tables via `purge_thread_checkpoints`), generate a fresh `review_session` UUID, and MUST NOT reuse a prior `review_directory` or `decision.json`.
- **FR-009**: The review HTTP server MUST run in the orchestrator's event loop, not inside a LangGraph node, and MUST NOT block LangGraph's internal state machine.
- **FR-010**: All resumption logic MUST be encapsulated in `run_with_review()` in `orchestrator.py` without leaking HITL primitives into individual node functions (except `approval_node`'s `interrupt()` call).

### Key Entities

- **Checkpoint (SQLite thread)**: The persisted LangGraph state identified by `thread_id`. Contains all `VideoState` fields and the interrupt marker when the graph is paused at approval.
- **Interrupt Snapshot**: The LangGraph state entry created when `interrupt()` is called inside `approval_node`. Contains the `review_directory` path needed to resume serving the review page.
- **Decision Record (`decision.json`)**: A file written atomically to the review directory containing the `ApprovalDecision` (list of approved cut IDs). Acts as a crash-safe bridge between the HTTP server and the LangGraph `Command(resume=...)` call.
- **Review Session (`review_directory`)**: The directory containing `review.json`, `decision.json`, and preview MP4 files for a specific analysis run. Identified by a deterministic hash of video source, session ID, and cut metadata.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a pipeline crash during the review wait window (no `decision.json`), relaunching the container resumes and displays the review page within 30 seconds, without repeating download, transcription, or LLM inference.
- **SC-002**: After a pipeline crash post-`decision.json` write (decision committed), relaunching the container proceeds to video rendering without serving the review page, completing the full remaining pipeline in the same time as an uninterrupted run.
- **SC-003**: The SQLite checkpoint contains the interrupt state within 2 seconds of the `approval_node` being reached, verifiable by reading the database before the review server starts.
- **SC-004**: Zero data loss of approved cut selections across container restarts — the approved IDs recovered from checkpoint + `decision.json` are identical to what the user submitted in the browser.
- **SC-005**: The blocking `while server.decision is None` loop is eliminated from the LangGraph graph execution path; the only blocking I/O during the review phase occurs in the orchestrator's external loop, outside of any node function.
- **SC-006**: Running `--restart` on a URL with an existing completed checkpoint results in a fresh full pipeline run, ignoring all prior state, decisions, and review directories.

## Assumptions

- The existing `interrupt` import from `langgraph.types` and `Command` usage in `run_with_review` in `orchestrator.py` already establishes the intent; this feature formalizes and completes that pattern by removing the residual blocking `wait_for_approval` call from within `approval_node`.
- The `interrupt_before` approach at compile time and the in-node `interrupt()` call are mutually exclusive options; the implementation will choose one and remove the other to avoid double-interruption behavior.
- The review directory path stored in `VideoState.review_directory` is sufficient to locate `decision.json` and the `review.json` manifest upon resumption.
- The `SqliteSaver` checkpoint write completes synchronously before `app.invoke()` returns control to `run_with_review`, giving a safe window to start the HTTP server.
- No changes are needed to `review.py`'s HTTP server logic or the `decision.json` atomic write — only the caller (orchestrator) changes how it interacts with that server.
