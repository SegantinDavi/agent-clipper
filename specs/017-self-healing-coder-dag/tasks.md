---
description: "Task list for feature Self-Healing Coder DAG implementation"
---

# Tasks: Self-Healing Coder DAG

**Input**: Design documents from `/specs/017-self-healing-coder-dag/`  
**Prerequisites**: [plan.md](plan.md) (required), [spec.md](spec.md) (required for user stories), [data-model.md](data-model.md), [research.md](research.md), [contracts/render_script_schema.json](contracts/render_script_schema.json), [contracts/coder_execution_contract.md](contracts/coder_execution_contract.md), [quickstart.md](quickstart.md)

**Tests**: Unit, regression, contract, and persistence tests are explicitly required by `spec.md` (FR-004, FR-006, FR-010, FR-012, SC-001–SC-005) and `plan.md`.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files or independent test scenarios)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Single Python project: `src/clipper/`, `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify virtual environment, core dependencies (`pydantic`, `instructor`, `openai`, `langgraph`), and test runner baseline before implementing new schemas and nodes.

- [X] T001 Verify virtual environment, core dependencies (pydantic, instructor, openai, langgraph), and test runner baseline via tests/test_instructor_sync_contract.py
- [X] T002 [P] Inspect specs/017-self-healing-coder-dag/contracts/render_script_schema.json and specs/017-self-healing-coder-dag/contracts/coder_execution_contract.md against target schema and node specifications

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models, configuration constants, and state extensions that MUST be complete before any user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 [P] Implement contract test verifying openai.pydantic_function_tool schema generation for RenderScriptPayload matches specs/017-self-healing-coder-dag/contracts/render_script_schema.json in tests/test_coder_dag.py
- [X] T004 [P] Implement unit tests for RenderScriptPayload validation constraints (min_length=1) in tests/test_coder_dag.py
- [X] T005 Implement RenderScriptPayload Pydantic model with strict validation in src/clipper/core/schemas.py
- [X] T006 [P] Add configuration settings for RENDER_TIMEOUT_SECONDS and RENDER_ERROR_MAX_CHARS in src/clipper/runtime/config.py
- [X] T007 Extend VideoState TypedDict with render_script_path, render_attempts, render_error, render_exit_code, render_aborted, current_cut_index, and rendered_video_paths in src/clipper/core/orchestrator.py

**Checkpoint**: Foundation ready - `RenderScriptPayload`, configuration constants, and `VideoState` extensions defined and validated. User story implementation can now begin.

---

## Phase 3: User Story 1 - LLM generates a render script from an approved cut (Priority: P1) 🎯 MVP

**Goal**: When a cut is approved, `coder_node` calls the configured LLM using Instructor Constrained Decoding with `RenderScriptPayload` to generate a self-contained Python render script (`render_script.py`) adhering to MoviePy 1.0.3, Pillow, and Liberation fonts, saved to `/app/output/<cut_id>/render_script.py`, with its path recorded in `VideoState["render_script_path"]`. Handles empty or malformed LLM completions gracefully by setting error diagnostics in `render_error` (FR-001, FR-002, FR-003, FR-010, FR-011).

**Independent Test**: Provide an approved cut in `VideoState`, invoke `coder_node` with a mocked LLM client, and verify that `render_script.py` is written to disk with UTF-8 encoding and its path is recorded in `VideoState["render_script_path"]`.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they fail before full implementation**

- [ ] T008 [P] [US1] Unit test coder_node generating render_script.py and storing path in VideoState with mocked instructor client in tests/test_coder_dag.py
- [ ] T009 [P] [US1] Unit test coder_node fail-fast and error handling on empty or malformed LLM completions in tests/test_coder_dag.py
- [ ] T010 [P] [US1] Unit test coder_node client lifecycle and resource cleanup ensuring raw_client.close is called deterministically in tests/test_coder_dag.py
- [ ] T011 [P] [US1] Contract test verifying coder_node strict synchronous function contract (inspect.iscoroutinefunction is False) in tests/test_instructor_sync_contract.py

### Implementation for User Story 1

- [ ] T012 [P] [US1] Define CODER_SYSTEM_PROMPT with strict MoviePy 1.0.3, Pillow, Liberation fonts, and even dimension constraints in src/clipper/core/prompts.py
- [ ] T013 [US1] Implement coder_node with Instructor constrained decoding, UTF-8 file writing, and error capture in src/clipper/core/orchestrator.py

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently (MVP delivered!).

---

## Phase 4: User Story 2 - Script is executed safely and outcome is captured (Priority: P2)

**Goal**: After `render_script.py` is written to disk, `execution_node` executes it in an isolated child subprocess with timeout protection (`RENDER_TIMEOUT_SECONDS`), captures stdout, stderr, and exit code into `VideoState`, increments `render_attempts`, and guarantees that child process failures or crashes never crash the orchestrator process (FR-004, FR-005, FR-007, FR-010).

**Independent Test**: Provide a valid Python script and a deliberately broken Python script, invoke `execution_node`, and verify exit codes (0 vs non-zero), `render_error` content, and `render_attempts` counter increments in `VideoState`.

### Tests for User Story 2

- [ ] T014 [P] [US2] Unit test execution_node running a successful script returning exit code 0 and empty render_error in tests/test_coder_dag.py
- [ ] T015 [P] [US2] Unit test execution_node running a failing script capturing non-zero exit code and stderr traceback without crashing orchestrator in tests/test_coder_dag.py
- [ ] T016 [P] [US2] Unit test execution_node timeout handling terminating hanging child process and recording timeout diagnostic in tests/test_coder_dag.py
- [ ] T017 [P] [US2] Contract test verifying execution_node strict synchronous function contract (inspect.iscoroutinefunction is False) in tests/test_instructor_sync_contract.py

### Implementation for User Story 2

- [ ] T018 [US2] Implement execution_node with isolated subprocess invocation, attempts counter increment, and safe error capture in src/clipper/core/orchestrator.py

**Checkpoint**: At this point, User Stories 1 AND 2 work together: scripts can be generated by `coder_node` and executed safely in subprocess isolation by `execution_node`.

---

## Phase 5: User Story 3 - Pipeline self-heals by retrying up to 3 times before giving up (Priority: P3)

**Goal**: LangGraph conditional edge routing and self-healing. When `execution_node` reports failure and `render_attempts < 3`, route back to `coder_node` with truncated `stderr` (`RENDER_ERROR_MAX_CHARS`) injected via `CODER_RETRY_PROMPT_TEMPLATE`. When `render_attempts >= 3`, route to `abort_node`, mark `render_aborted = True`, and continue safely. When execution succeeds (exit code 0), advance through all approved cuts or complete. Persist retry state across SQLite checkpoints via `SqliteSaver` (FR-006, FR-008, FR-009, FR-012, SC-002, SC-005).

**Independent Test**: Wire the LangGraph DAG, simulate transient failure fixed on retry 2, simulate persistent failure aborting after 3 attempts, and simulate container restart mid-retry verifying `SqliteSaver` state restoration.

### Tests for User Story 3

- [ ] T019 [P] [US3] Unit test route_execution_outcome conditional routing logic for complete (exit 0), retry (exit != 0, attempts < 3), and abort (exit != 0, attempts >= 3) in tests/test_coder_dag.py
- [ ] T020 [P] [US3] Unit test CODER_RETRY_PROMPT_TEMPLATE formatting and coder_node retry logic injecting truncated stderr into user prompt in tests/test_coder_dag.py
- [ ] T021 [P] [US3] Unit test abort_node setting render_aborted True and logging warning in tests/test_coder_dag.py
- [ ] T022 [P] [US3] Contract test verifying abort_node strict synchronous function contract (inspect.iscoroutinefunction is False) in tests/test_instructor_sync_contract.py
- [ ] T023 [US3] Integration test verifying end-to-end self-healing retry loop recovering from initial failure in tests/test_coder_dag.py
- [ ] T024 [US3] Integration test verifying abort edge termination after 3 consecutive execution failures without orchestrator crash in tests/test_coder_dag.py
- [ ] T025 [US3] Integration test verifying SqliteSaver checkpoint persistence and crash recovery of render_attempts and render_error mid-loop in tests/test_coder_dag.py

### Implementation for User Story 3

- [ ] T026 [P] [US3] Define CODER_RETRY_PROMPT_TEMPLATE with previous script and error diagnostic placeholders in src/clipper/core/prompts.py
- [ ] T027 [US3] Implement route_execution_outcome conditional router and abort_node in src/clipper/core/orchestrator.py
- [ ] T028 [US3] Update coder_node to detect retries and construct diagnostic retry prompts with truncated stderr in src/clipper/core/orchestrator.py
- [ ] T029 [US3] Update create_graph DAG topology adding coder, execution, abort nodes, conditional edges, and cut iteration in src/clipper/core/orchestrator.py (retaining editor_node in workflow.nodes for backwards compatibility and updating tests/test_instructor_sync_contract.py expected_nodes set)

**Checkpoint**: All user stories (US1, US2, US3) are implemented, tested, and integrated with the full self-healing LangGraph DAG.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verify non-regression across all existing tests (SC-004), verify static analysis compliance (zero regex/manual json.loads, SC-002), benchmark execution overhead (SC-003), validate quickstart workflow, and synchronize project documentation.

- [ ] T030 [P] Static analysis AST scan asserting zero occurrences of regex or manual json.loads in coder_node and execution layer (SC-002) in tests/test_coder_dag.py
- [ ] T031 [P] Benchmark execution overhead of coder_node and execution_node wrapper asserting overhead strictly under 500ms wall-clock (SC-003) in tests/test_coder_dag.py
- [ ] T032 Execute full discovery test suite across tests/ to verify zero regressions across existing 202 tests (SC-004)
- [ ] T033 Validate operational quickstart workflow per specs/017-self-healing-coder-dag/quickstart.md and verify end-to-end rendering success baseline (SC-001)
- [ ] T034 Synchronize project documentation, architecture details, and schema updates across README.md, AGENTS.md, and GEMINI.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 completion - BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Phase 2 completion. Delivers core script generation MVP.
- **User Story 2 (Phase 4)**: Depends on Phase 2 (VideoState) and Phase 3 (`render_script.py` generation). Delivers safe isolated execution.
- **User Story 3 (Phase 5)**: Depends on Phase 3 (`coder_node`), Phase 4 (`execution_node`), and Phase 2 (`VideoState`). Implements LangGraph conditional self-healing edges and recovery.
- **Polish (Phase 6)**: Depends on all user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Foundational prerequisites (T003–T007) must complete first.
- **User Story 2 (P2)**: Requires US1 script file path and foundational state (T007, T013).
- **User Story 3 (P3)**: Requires US1 `coder_node` (T013) and US2 `execution_node` (T018) to connect the feedback retry loop.

### Within Each User Story

- Test tasks marked `[P]` should be written and verified before or concurrently with implementation.
- Prompt definitions precede node orchestration.
- Standalone node functions precede DAG edge updates.
- Checkpoints validate each story independently before moving to next.

---

## Parallel Execution Examples

### User Story 1
```bash
# Run US1 tests and prompt template definition in parallel:
Task: "Unit test coder_node generating render_script.py and storing path in VideoState in tests/test_coder_dag.py"
Task: "Define CODER_SYSTEM_PROMPT with strict MoviePy 1.0.3 constraints in src/clipper/core/prompts.py"
```

### User Story 2
```bash
# Run US2 execution test scenarios in parallel:
Task: "Unit test execution_node running a successful script in tests/test_coder_dag.py"
Task: "Unit test execution_node running a failing script in tests/test_coder_dag.py"
Task: "Unit test execution_node timeout handling in tests/test_coder_dag.py"
```

### User Story 3
```bash
# Run routing and retry prompt tests in parallel:
Task: "Unit test route_execution_outcome conditional routing logic in tests/test_coder_dag.py"
Task: "Define CODER_RETRY_PROMPT_TEMPLATE in src/clipper/core/prompts.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently (`coder_node` writes valid `render_script.py`)
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → MVP!
3. Add User Story 2 → Test isolated script execution → Subprocess safety guaranteed
4. Add User Story 3 → Connect self-healing loop in LangGraph → Full resilience delivered
5. Polish → Benchmark, regression test, and synchronize documentation

---

## Notes

- `[P]` tasks = different files or independent test scenarios with no dependencies on incomplete tasks.
- `[Story]` label maps task to specific user story for full traceability.
- Each user story is independently completable and testable.
- Backward compatibility: `editor_node` remains callable to preserve existing tests.
- Every node remains a strict synchronous function (`def`).
- Constrained Decoding is enforced via `instructor` + Pydantic schema (zero regex/manual json parsing).
