# Research & Technical Decisions: LangGraph Native Human-in-the-Loop Checkpoint Integration

**Feature**: `010-manual-review-langgraph-integration`  
**Date**: 2026-10-28  
**Status**: Completed  
**Spec**: [spec.md](spec.md)

---

## 1. Executive Summary

This feature resolves the architectural gap between manual cut approval and LangGraph's persistent state machine. In the previous implementation, the review HTTP server was capable of blocking or executing synchronously without guaranteeing that the SQLite checkpointer had recorded an explicit interrupt state prior to decision arrival. Furthermore, when the container was restarted with `--restart`, residual checkpoints in SQLite could cause LangGraph to retain or replay the interrupted state instead of restarting from scratch.

This research establishes:
1. The native in-node `interrupt()` primitive as the sole suspension mechanism (rejecting `interrupt_before`).
2. An orchestrator-driven loop in `run_with_review()` that manages the external review server outside graph execution.
3. A two-tier durability architecture (`decision.json` on disk + SQLite thread checkpoint).
4. A deterministic checkpoint invalidation strategy for `--restart`.

---

## 2. Technical Decisions & Analysis

### Decision 1: Human-in-the-Loop Primitive (`interrupt()` vs `interrupt_before`)

- **Chosen Approach**: In-node `interrupt()` from `langgraph.types`.
- **Rationale**:
  - `interrupt(payload)` allows the node (`approval_node`) to pause execution and record a structured payload (e.g. `{"review_directory": state["review_directory"], "cut_count": len(cuts)}`) into the checkpoint snapshot.
  - When resumed via `app.invoke(Command(resume={"approved_ids": ids}), config=config)`, LangGraph injects the resume value directly into the return expression of `interrupt()`, enabling clean downstream validation with `validate_approval(decision, len(cuts))`.
  - The graph compilation remains clean and standard: `workflow.compile(checkpointer=checkpointer)`.
- **Alternatives Considered & Rejected**:
  - `interrupt_before=["approval"]` at `workflow.compile()`:
    - *Rejected because*: `interrupt_before` halts execution *prior* to executing the node. It does not allow the node to yield an interrupt payload. Resuming requires either `update_state` or calling `app.invoke(None)` which re-executes the node from the beginning.
  - *Prohibition of Mixing*: Mixing both `interrupt_before` and `interrupt()` leads to a double-interruption cycle where LangGraph pauses before the node, and upon initial resume pauses again inside the node. FR-002 strictly mandates selecting one approach; in-node `interrupt()` is chosen.

---

### Decision 2: Orchestrator Resumption State Machine & Decoupled Server Lifecycle

- **Chosen Approach**: Decouple the HTTP server from LangGraph graph execution by managing it exclusively inside `run_with_review()` in `src/clipper/core/orchestrator.py`.
- **Execution Flow**:
  1. Check `--restart` flag: If `True`, purge existing checkpoints for `thread_id` and initialize fresh state.
  2. Inspect state snapshot via `app.get_state(config)`:
     - **Case A (Fresh Run)**: No `snapshot.values` exists. Call `app.invoke(initial_state, config=config)`.
     - **Case B (Already Complete)**: `snapshot.values` exists, `snapshot.next` is empty, and no task has pending interrupts. Log `"This run is already complete. Use --restart to process it again."` and exit cleanly.
     - **Case C (Mid-Graph Interruption / Pending Resume)**: `snapshot.next` has unexecuted nodes (non-interrupt). Call `app.invoke(None, config=config)`.
     - **Case D (Interrupted at Approval)**: Tasks contain pending interrupts (`any(t.interrupts for t in snapshot.tasks)`).
  3. While execution result has `__interrupt__` or snapshot tasks contain interrupts:
     - Retrieve current snapshot and extract `review_directory = snapshot.values.get("review_directory")`.
     - **Durability check**: Check if a valid `decision.json` already exists in `review_directory`.
       - If valid `decision.json` exists: Read and parse `approved_ids`. Skip launching the HTTP server.
       - If `decision.json` is missing or invalid: Launch the HTTP server (via `wait_for_approval` or `create_review_server`), wait for browser submission, commit `decision.json` atomically, and retrieve `approved_ids`.
     - Resume graph: `app.invoke(Command(resume={"approved_ids": ids}), config=config)`.
- **Rationale**:
  - By the time `app.invoke()` returns with `__interrupt__`, `SqliteSaver` has already synchronously committed the interrupt checkpoint to `/app/output/estado.db`.
  - The HTTP server runs only while the graph is dormant, consuming minimal CPU and zero LangGraph executor resources.
- **Alternatives Considered & Rejected**:
  - Running HTTP server inside `approval_node`: Blocked state saving until after human interaction, defeating crash-safety guarantees.

---

### Decision 3: Deterministic Invalidation on `--restart`

- **Chosen Approach**: Direct SQLite checkpoint clearing for the targeted `thread_id` coupled with a fresh `review_session` UUID.
- **Implementation Detail**:
  When `restart=True`:
  ```python
  def purge_thread_checkpoints(conn, thread_id: str):
      with conn:
          conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
          conn.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,))
  ```
- **Rationale**:
  - In LangGraph with `SqliteSaver`, passing `initial_state` to `app.invoke(initial_state, config)` on a thread that already contains an active interrupt does *not* reset the graph; it returns the existing interrupt object.
  - Purging the database rows for that specific `thread_id` guarantees a 100% deterministic fresh execution from `START`, satisfying FR-008 and SC-006 without touching checkpoints of other videos or runs.
- **Alternatives Considered & Rejected**:
  - Deleting the entire `estado.db` file: Destroys checkpoints of other processed videos that may be sharing the SQLite checkpointer.
  - Generating a random UUID for `thread_id` on every execution: Breaks automatic resumption on container restart without manual thread tracking.

---

### Decision 4: Two-Tier Durability Protocol (`decision.json` + SQLite Checkpoint)

- **Chosen Approach**:
  - **Tier 1 (Disk)**: `decision.json` written atomically via `.partial` file rename in `review.py`.
  - **Tier 2 (Database)**: SQLite checkpoint updated upon `Command(resume=...)`.
- **Crash Recovery Matrix**:

| Crash Moment | State on Disk | SQLite Checkpoint State | Resume Action on Container Restart |
|---|---|---|---|
| **During Ingestion/Thinker** | No `review.json` | Progressed to last completed node | Resumes from `snapshot.next` without re-downloading |
| **During Preview generation** | `review.json` partial | Completed `extrator` | Re-runs `preview` node (resuming existing previews if cached) |
| **While Review Server is waiting** | `review.json` exists, no `decision.json` | Interrupted at `approval` (`snapshot.tasks` has interrupt) | Detects interrupt, starts review server again at same port/URL |
| **After browser submit, before Command invoke** | `decision.json` exists and valid | Interrupted at `approval` | Detects interrupt, discovers valid `decision.json`, skips HTTP server, invokes `Command(resume=...)` |
| **During final Video Editing** | `decision.json` exists | Progressed to `editor` | Resumes `editor` node directly |
| **After completion** | Video rendered | Graph finished (`snapshot.next` empty) | Logs "already complete", exits with code 0 |

---

## 3. Best Practices & Guidelines Compliance

- **Memory Management (AGENTS.md Rule 1)**: No additional models, threads, or GPU resources loaded during review. The HTTP server runs on 127.0.0.1, servicing small static assets and receiving short JSON payloads.
- **State Serialization (AGENTS.md Rule 3)**: Only JSON-serializable primitives in `VideoState`. Interrupt payloads strictly use path strings and integer counts.
- **Constrained Decoding (AGENTS.md Rule 5)**: `ApprovalDecision` validation uses Pydantic exclusively.
- **Clean Code (AGENTS.md Rule 8)**: Standard English naming, zero redundant comments.
- **Observabilidade (AGENTS.md Rule 9)**: Structured logs in `pipeline.log` for state transitions and resumption milestones.
