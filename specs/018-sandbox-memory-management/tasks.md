---
description: "Task list for feature 018: Sandbox Memory Management"
---

# Tasks: Sandbox Memory Management

**Input**: Design documents from `/specs/018-sandbox-memory-management/`
**Prerequisites**: [plan.md](file:///home/davig/agents-workspace/agent-clipper/specs/018-sandbox-memory-management/plan.md), [spec.md](file:///home/davig/agents-workspace/agent-clipper/specs/018-sandbox-memory-management/spec.md), [research.md](file:///home/davig/agents-workspace/agent-clipper/specs/018-sandbox-memory-management/research.md), [data-model.md](file:///home/davig/agents-workspace/agent-clipper/specs/018-sandbox-memory-management/data-model.md), [contracts/](file:///home/davig/agents-workspace/agent-clipper/specs/018-sandbox-memory-management/contracts/)

**Tests**: Test tasks are included as specified in the implementation plan and quality gates (TDD approach for contract validation, AST static checks, and peak memory boundaries).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files or independent test suites, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (e.g., `[US1]`, `[US2]`)
- Exact file paths are included in all task descriptions

## Path Conventions

- **Single project layout**: `src/clipper/`, `tests/` at repository root
- Primary affected files:
  - `src/clipper/core/prompts.py`
  - `src/clipper/core/orchestrator.py`
  - `src/clipper/runtime/cuda_runtime.py`
  - `tests/test_sandbox_memory.py` (new)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Test environment verification and shared test harness configuration

- [X] T001 Verify runtime environment and test suite execution with venv in tests/
- [X] T002 Configure memory profiling test helpers (ru_maxrss / proc status) in tests/test_sandbox_memory.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Scaffold the test suite module and baseline fixtures required for all user stories

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 Scaffold sandbox memory test module with shared mock fixtures in tests/test_sandbox_memory.py

**Checkpoint**: Foundation ready — user story implementation can now begin in priority order

---

## Phase 3: User Story 1 - Stable Memory Footprint During Rendering (Priority: P1) 🎯 MVP

**Goal**: Instruct coder LLM to insert explicit intermediate-buffer cleanup calls (`del`, `gc.collect()`, `.close()`) in generated render scripts, keeping peak RAM below 2 GB during render subprocess execution.

**Independent Test**: Execute a generated render script against a ≥10-minute video cut. Monitor RSS during execution; assert peak usage stays below 2 GB and the process exits 0. Also perform static AST inspection verifying presence of cleanup constructs.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T004 [P] [US1] Add unit tests for Rule 6 prompt constants (CODER_SYSTEM_PROMPT and CODER_RETRY_PROMPT_TEMPLATE) in tests/test_sandbox_memory.py
- [X] T005 [P] [US1] Add AST verification tests for intermediate-buffer cleanup and gc.collect constructs in tests/test_sandbox_memory.py
- [X] T006 [US1] Add integration test asserting peak RSS < 2 GB during long video render execution in tests/test_sandbox_memory.py

### Implementation for User Story 1

- [X] T007 [US1] Add Rule 6 memory management directives to CODER_SYSTEM_PROMPT in src/clipper/core/prompts.py
- [X] T008 [US1] Reinforce memory management directives in CODER_RETRY_PROMPT_TEMPLATE in src/clipper/core/prompts.py

**Checkpoint**: At this point, User Story 1 is fully functional and testable independently. LLM prompts generate scripts with memory deallocation and peak RSS stays under 2 GB.

---

## Phase 4: User Story 2 - Automatic VRAM Flush After Render Subprocess (Priority: P2)

**Goal**: Unconditionally call `release_cuda_memory(cut_id=cut_id)` in `execution_node` via a guaranteed `finally:` block across all subprocess outcomes (exit code 0, non-zero exit code, timeout, unexpected exception), recording structured audit metrics in `pipeline.log` and executing silently in CPU/Ollama profile.

**Independent Test**: Run consecutive render cycles with a Gemini-profile pipeline. Inspect `pipeline.log` to confirm a VRAM-flush log entry appears after each cycle (success, failure, timeout alike) with `[cut={cut_id}]`, before/after/freed MB metrics, and verify silent no-op when `WHISPER_DEVICE != "cuda"`.

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T009 [P] [US2] Add unit tests for release_cuda_memory signature and cut_id audit logging using mock fixtures in tests/test_sandbox_memory.py
- [X] T010 [P] [US2] Add unit tests verifying release_cuda_memory silent no-op when WHISPER_DEVICE is cpu in tests/test_sandbox_memory.py
- [X] T011 [US2] Add unit tests for execution_node guaranteed finally block execution across success, failure, timeout, exceptions, and asserting flush overhead < 50ms (SC-005) in tests/test_sandbox_memory.py
- [X] T012 [US2] Add unit tests for execution_node resilience (FR-008) when release_cuda_memory raises an exception in tests/test_sandbox_memory.py

### Implementation for User Story 2

- [X] T013 [US2] Extend release_cuda_memory with cut_id parameter and structured audit logging in src/clipper/runtime/cuda_runtime.py
- [X] T014 [US2] Implement guaranteed post-subprocess VRAM flush in execution_node finally block in src/clipper/core/orchestrator.py

**Checkpoint**: At this point, User Stories 1 AND 2 are both fully functional and independently verified.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Regression testing, quality gate enforcement, and documentation synchronization

- [ ] T015 [P] Run regression validation against coder DAG and CUDA cleanup test suites in tests/test_coder_dag.py and tests/test_cuda_cleanup.py
- [ ] T016 Run full test discovery suite ensuring zero regressions across all 234+ tests in tests/
- [ ] T017 [P] Update feature documentation and architecture rules in README.md, AGENTS.md, and GEMINI.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational (Phase 2) completion
- **User Story 2 (Phase 4)**: Depends on Foundational (Phase 2) completion; can proceed after or in parallel with US1
- **Polish (Phase 5)**: Depends on completion of User Story 1 and User Story 2

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) — No dependencies on US2
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) — Integrates with `execution_node` and `cuda_runtime`, independent of prompt changes in US1

### Within Each User Story

- Tests MUST be written and fail before implementation begins
- Prompt updates and runtime function signatures must satisfy contracts before caller integration
- Story complete and verified before moving to next priority or Polish phase

### Parallel Opportunities

- Within Phase 3 (US1):
  - T004 (prompt tests) and T005 (AST tests) can run in parallel
- Within Phase 4 (US2):
  - T009 (signature and log tests) and T010 (CPU no-op tests) can run in parallel
- Within Phase 5 (Polish):
  - T015 (focused regression tests) and T017 (documentation updates) can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch prompt assertion and AST validation tests in parallel:
Task: "Add unit tests for Rule 6 prompt constants (CODER_SYSTEM_PROMPT and CODER_RETRY_PROMPT_TEMPLATE) in tests/test_sandbox_memory.py"
Task: "Add AST verification tests for intermediate-buffer cleanup and gc.collect constructs in tests/test_sandbox_memory.py"
```

---

## Parallel Example: User Story 2

```bash
# Launch CUDA runtime unit tests in parallel:
Task: "Add unit tests for release_cuda_memory signature and cut_id audit logging in tests/test_sandbox_memory.py"
Task: "Add unit tests verifying release_cuda_memory silent no-op when WHISPER_DEVICE is cpu in tests/test_sandbox_memory.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (`T001`, `T002`)
2. Complete Phase 2: Foundational (`T003`)
3. Complete Phase 3: User Story 1 (`T004`–`T008`)
4. **STOP and VALIDATE**: Verify peak RAM < 2 GB and AST assertions pass
5. Demo / Deliver MVP

### Incremental Delivery

1. Complete Setup + Foundational → Test foundation ready
2. Deliver User Story 1 (MVP) → Stable host RAM footprint during render execution (< 2 GB)
3. Deliver User Story 2 → Unconditional GPU VRAM reclamation post-subprocess with structured logging
4. Deliver Polish → Full 234+ regression pass, clean docs

---

## Notes

- All tasks follow strict checklist format: `- [ ] [TaskID] [P?] [Story?] Description with file path`
- Zero new external dependencies (uses standard library `gc`, `resource`, `ast`, `subprocess`)
- In Ollama/CPU mode, `release_cuda_memory()` returns immediately with zero CUDA calls
- Subprocess RAM limit is verified with `resource.getrusage(resource.RUSAGE_CHILDREN)`
- Backward compatibility preserved for all existing `release_cuda_memory` callers
