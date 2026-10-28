# Tasks: LangGraph Native Human-in-the-Loop Checkpoint Integration

**Input**: Design documents from `specs/010-manual-review-langgraph-integration/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/)

**Tests**: Test tasks are included per the specification and testing requirements in `spec.md` and `plan.md`.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `- [ ] [TaskID] [P?] [Story?] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Target paths under `src/clipper/` and `tests/` at repository root
- Storage output mapped to `/app/output/` (checkpointer in `estado.db`, review folders under `reviews/`)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Test harness preparation and environment baseline

- [X] T001 Verify testing environment and dependencies in `src/clipper/core/orchestrator.py` and `tests/test_review.py`
- [X] T002 [P] Set up test fixture helpers for SQLite checkpoint database and mock graph runners in `tests/test_review.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core durability and schema utilities required by all user stories

**⚠️ CRITICAL**: Must be completed before implementing user stories

- [X] T003 Implement SQLite thread checkpoint purge function `purge_thread_checkpoints` in `src/clipper/core/orchestrator.py`
- [X] T004 [P] Verify and enforce `ApprovalDecision` schema and atomic serialization helper in `src/clipper/review/review.py`

**Checkpoint**: Foundation ready - user story implementation can begin

---

## Phase 3: User Story 1 - Crash-Safe Approval Resume (Priority: P1) 🎯 MVP

**Goal**: The pipeline resumes deterministically from the approval checkpoint after container crashes without reprocessing prior nodes (download, fatiamento, transcription, thinker, extrator). Relaunching with `--restart` purges existing checkpoints and starts fresh, while completed runs exit immediately without reprocessing.

**Independent Test**: Run pipeline to approval interrupt, simulate process crash (restart container/call `run_with_review`), verify it resumes without reprocessing earlier nodes; test `--restart` clears checkpoint and restarts from START; test completed run exits without reprocessing.

### Tests for User Story 1

- [X] T005 [P] [US1] Add unit test for completed run early exit in `tests/test_review.py`
- [X] T006 [P] [US1] Add unit test for `--restart` purging SQLite checkpoints in `tests/test_review.py`
- [X] T007 [P] [US1] Add integration test for crash-safe resumption after interrupt without `--restart` in `tests/test_review.py`

### Implementation for User Story 1

- [X] T008 [US1] Implement `--restart` checkpoint purge and completed run handling in `run_with_review` in `src/clipper/core/orchestrator.py`
- [X] T009 [US1] Update `run_with_review` to access `app.checkpointer` for SQLite thread purge on `--restart` without altering CLI caller signature in `src/clipper/core/orchestrator.py`

**Checkpoint**: User Story 1 is functional and verifiable independently as the MVP increment.

---

## Phase 4: User Story 2 - Synchronous Approval Server Decoupled from Graph Execution (Priority: P2)

**Goal**: Decouple the review HTTP server from LangGraph's internal DAG execution by having `approval_node` call `interrupt()` with structured payload, ensuring SQLite commits the interrupt snapshot before the review server runs in `run_with_review()`, and resuming the graph via `Command(resume=...)`.

**Independent Test**: Inspect the SQLite checkpoint immediately after `approval_node` executes to verify `__interrupt__` is present and node output is not committed; verify `Command(resume=...)` resumes execution to `editor_node`.

### Tests for User Story 2

- [X] T010 [P] [US2] Add unit test verifying `approval_node` calls `interrupt()` with payload and commits interrupt state in `tests/test_review.py`
- [X] T011 [P] [US2] Add unit test for `run_with_review` managing external HTTP server and resuming with `Command(resume=...)` in `tests/test_review.py`

### Implementation for User Story 2

- [X] T012 [US2] Refactor `approval_node` to strictly adhere to the HITL interrupt and resume contract in `src/clipper/core/orchestrator.py`
- [X] T013 [US2] Refactor `run_with_review` external loop to drive review server without blocking graph threads in `src/clipper/core/orchestrator.py`

**Checkpoint**: User Story 2 is complete. Review server operates completely decoupled from graph threads.

---

## Phase 5: User Story 3 - Decision Persistence Across Process Boundaries (Priority: P3)

**Goal**: Check for existing valid `decision.json` on disk before launching the HTTP server upon resuming from an interrupt checkpoint, injecting the decision immediately into `Command(resume=...)`, and falling back to the review server if `decision.json` is corrupted or missing.

**Independent Test**: Place a valid `decision.json` in `review_directory` and resume interrupted graph; verify review server is bypassed and graph completes. Place a corrupted `decision.json` and verify review server is launched.

### Tests for User Story 3

- [X] T014 [P] [US3] Add unit test for resuming with pre-existing valid `decision.json` bypassing HTTP server in `tests/test_review.py`
- [X] T015 [P] [US3] Add unit test for corrupted or missing `decision.json` triggering fallback to review server in `tests/test_review.py`

### Implementation for User Story 3

- [X] T016 [US3] Implement pre-server `decision.json` check and validation before launching HTTP server in `run_with_review` in `src/clipper/core/orchestrator.py`

**Checkpoint**: All user stories (US1, US2, US3) are fully functional and integrated.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verification, non-regression testing, and static analysis

- [ ] T017 [P] Execute full test suite `PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"` to ensure zero regressions
- [ ] T018 [P] Run static analysis and style checks with `ruff check .` across `src/` and `tests/`
- [ ] T019 Validate crash resilience validation scenarios per `specs/010-manual-review-langgraph-integration/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational completion. Delivers the core MVP.
- **User Story 2 (Phase 4)**: Depends on Foundational completion. Refines in-node suspension and external server loop.
- **User Story 3 (Phase 5)**: Depends on Phase 3 and Phase 4. Adds disk-level decision recovery before launching server.
- **Polish (Phase 6)**: Depends on all user stories being implemented.

### User Story Dependencies

- **User Story 1 (P1)**: Independent of US2/US3; relies on basic checkpointer resume and purge capabilities.
- **User Story 2 (P2)**: Builds upon the thread execution loop in US1 to decouple the HTTP server from LangGraph.
- **User Story 3 (P3)**: Builds on US2's driver loop by adding pre-server `decision.json` inspection.

### Within Each User Story

- Unit/integration tests written first.
- Implementation tasks follow tests.
- Verify tests pass before closing the phase.

### Parallel Opportunities

- T002 can run in parallel with T001 during Setup.
- T004 (`review.py`) can run in parallel with T003 (`orchestrator.py`) during Foundational.
- Tests T005, T006, and T007 can be authored in parallel for US1.
- Tests T010 and T011 can be authored in parallel for US2.
- Tests T014 and T015 can be authored in parallel for US3.
- T017 and T018 can execute in parallel during Polish.

---

## Parallel Example: User Story 1

```bash
# Launch test creation for User Story 1 in parallel:
Task: "Add unit test for completed run early exit in tests/test_review.py"
Task: "Add unit test for --restart purging SQLite checkpoints in tests/test_review.py"
Task: "Add integration test for crash-safe resumption after interrupt without --restart in tests/test_review.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001, T002)
2. Complete Phase 2: Foundational (T003, T004)
3. Complete Phase 3: User Story 1 (T005-T009)
4. **STOP and VALIDATE**: Verify crash resumption without rerun of earlier nodes, `--restart` purging, and completed run exit.
5. Deploy MVP checkpoint capability.

### Incremental Delivery

1. Complete Setup + Foundational → Durable SQLite operations enabled.
2. Deliver US1 (MVP) → Crash-safe restart and clean rerun handling.
3. Deliver US2 → Native `interrupt()` payload and fully decoupled HTTP server loop.
4. Deliver US3 → Instant resumption from existing `decision.json` on disk.
5. Polish → Full test suite verification, ruff linting, and quickstart run.

---

## Notes

- All tasks follow `- [ ] [TaskID] [P?] [Story?] Description with file path`.
- In-node `interrupt()` is strictly used per `research.md` (no `interrupt_before`).
- Checkpoint purges only affect the specific `thread_id` to preserve other video runs in `estado.db`.
- Atomic writes via `.partial` file rename are maintained in all disk operations.
