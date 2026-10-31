---
description: "Task list for feature Align Instructor Nodes with LangGraph Synchronous Execution implementation"
---

# Tasks: Align Instructor Nodes with LangGraph Synchronous Execution

**Input**: Design documents from `/specs/014-align-instructor-nodes/`  
**Prerequisites**: [plan.md](plan.md) (required), [spec.md](spec.md) (required for user stories), [data-model.md](data-model.md), [research.md](research.md), [contracts/llm-node-sync-contract.md](contracts/llm-node-sync-contract.md), [quickstart.md](quickstart.md)

**Tests**: Unit, regression, and architectural contract tests are explicitly required by `spec.md` (FR-007, FR-008, SC-001–SC-004) and `plan.md`.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files or independent test scenarios)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Single Python project: `src/clipper/`, `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify virtual environment, core dependencies (`langgraph`, `instructor`, `openai`, `pydantic`), and existing test suite baseline before making modifications

- [X] T001 Verify Python virtual environment, dependencies (`langgraph`, `instructor`, `openai`, `pydantic`), and test runner baseline via tests/test_llm_api.py and tests/test_review.py
- [X] T002 [P] Inspect existing node definitions and client factory implementations against contracts/llm-node-sync-contract.md in src/clipper/core/orchestrator.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Scaffolding and shared fixtures/mock utilities required across all user story contract tests

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 Scaffold architectural contract test module structure with mock transport helpers in tests/test_instructor_sync_contract.py
- [X] T004 [P] Implement mock LLM client and ChatCompletion fixtures for isolated synchronous testing in tests/test_instructor_sync_contract.py

**Checkpoint**: Foundation ready - test suite structure initialized. User story implementation can now begin.

---

## Phase 3: User Story 1 - Execução Contínua e Previsível do Pipeline (Priority: P1) 🎯 MVP

**Goal**: Ensure that the Thinker (`thinker_node`) and Extractor (`extractor_node`) nodes execute deterministically and sequentially within the LangGraph StateGraph without blocking the thread, creating unawaited coroutines, or introducing event loop conflicts (FR-001, FR-003, FR-004, FR-006, SC-002).

**Independent Test**: Execute `thinker_node` and `extractor_node` sequentially with mock HTTP transport fixtures, verifying that data returns immediately as dictionary state updates (`raciocinio_bruto` and `cortes_finais`) without coroutine warnings or event loop stalls.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they fail before full implementation**

- [X] T005 [P] [US1] Unit test synchronous sequential execution of thinker_node returning raciocinio_bruto dictionary in tests/test_instructor_sync_contract.py
- [X] T006 [P] [US1] Unit test synchronous execution of extractor_node using instructor schema decoding returning cortes_finais dictionary in tests/test_instructor_sync_contract.py
- [X] T007 [P] [US1] Integration test verifying create_graph compilation and app.invoke execution with stubbed/mocked peripheral I/O nodes emits zero RuntimeWarning coroutine warnings (SC-002) in tests/test_instructor_sync_contract.py

### Implementation for User Story 1

- [X] T008 [US1] Verify and enforce strict synchronous def definitions and return payload structures for thinker_node and extractor_node in src/clipper/core/orchestrator.py
- [X] T009 [US1] Ensure create_graph compiles StateGraph for pure synchronous invocation via app.invoke in src/clipper/core/orchestrator.py

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently (MVP delivered!).

---

## Phase 4: User Story 2 - Blindagem e Verificação de Conformidade Arquitetural (Priority: P2)

**Goal**: Provide automated architectural contract assertions guaranteeing that 100% of StateGraph nodes are standard synchronous functions and that LLM client factories and Instructor wrappers never return asynchronous variants (FR-001, FR-002, FR-003, FR-007, FR-008, SC-001, SC-003).

**Independent Test**: Run contract tests inspecting all registered graph nodes via reflection (`inspect.iscoroutinefunction` and `asyncio.iscoroutinefunction`) and asserting instance types for `create_llm_client()` (`openai.OpenAI`, not `AsyncOpenAI`) and `instructor.from_openai()` (`instructor.Instructor`, not `AsyncInstructor`).

### Tests for User Story 2

- [X] T010 [P] [US2] Contract test auditing 100% of nodes in create_graph using inspect.iscoroutinefunction and asyncio.iscoroutinefunction (AC-01, FR-001, FR-007, SC-001) in tests/test_instructor_sync_contract.py
- [X] T011 [P] [US2] Contract test asserting create_llm_client returns an openai.OpenAI instance and not openai.AsyncOpenAI (AC-02, FR-002, FR-008) in tests/test_instructor_sync_contract.py
- [X] T012 [P] [US2] Contract test asserting instructor.from_openai wraps openai.OpenAI into synchronous instructor.Instructor (AC-03, FR-003) in tests/test_instructor_sync_contract.py

### Implementation for User Story 2

- [X] T013 [US2] Add runtime type assertions (openai.OpenAI and not AsyncOpenAI) to create_llm_client in src/clipper/core/orchestrator.py
- [X] T014 [US2] Audit all registered graph node signatures against NodeCallable contract specifications in src/clipper/core/orchestrator.py

**Checkpoint**: At this point, User Stories 1 AND 2 should both work together: execution is predictable and architectural compliance is guarded by contract assertions.

---

## Phase 5: User Story 3 - Liberação Confiável de Recursos e Conexões de Rede (Priority: P3)

**Goal**: Ensure reliable and deterministic closure of all network transports and socket descriptors in `thinker_node` and `extractor_node` immediately upon completion or failure (timeouts, HTTP errors, schema validation errors) using guaranteed `finally` teardown (FR-005, SC-004).

**Independent Test**: Simulate network success, HTTP timeout, API connection failure, and schema validation error in mock tests and assert that `raw_client.close()` is called exactly once in every execution branch.

### Tests for User Story 3

- [X] T015 [P] [US3] Unit test verifying deterministic raw_client.close invocation in thinker_node on success and exceptions (AC-04, FR-005, SC-004) in tests/test_instructor_sync_contract.py
- [X] T016 [P] [US3] Unit test verifying deterministic raw_client.close invocation in extractor_node on success, API timeout, and schema validation error (AC-05, FR-005, SC-004) in tests/test_instructor_sync_contract.py

### Implementation for User Story 3

- [X] T017 [US3] Harden try-finally blocks and deterministic raw_client.close teardown in thinker_node and extractor_node in src/clipper/core/orchestrator.py

**Checkpoint**: All three user stories are functional and verified with deterministic socket cleanup across all success and error paths.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories, test suite completion, and repository documentation synchronization

- [X] T018 Execute full test suite across the repository via tests/test_*.py
- [X] T019 [P] Run quickstart validation script commands from specs/014-align-instructor-nodes/quickstart.md
- [X] T020 [P] Synchronize documentation and feature guidelines in GEMINI.md and AGENTS.md
- [X] T021 Review code formatting, type annotations, and Clean Code compliance in src/clipper/core/orchestrator.py and tests/test_instructor_sync_contract.py

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Guards the signatures and client types established in US1
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Hardens connection teardown inside the nodes verified in US1

### Within Each User Story

- Tests MUST be written and fail before implementation
- Node definition before graph integration assertions
- Success paths before exception paths
- Story verified complete before proceeding to subsequent priorities

### Parallel Opportunities

- T001 and T002 can run in parallel during Setup
- T003 and T004 can run in parallel during Foundation
- Tests within each User Story (T005, T006, T007 in US1; T010, T011, T012 in US2; T015, T016 in US3) can be authored in parallel
- Documentation update (T020) can run in parallel with quickstart validation (T019) and final code review (T021)

---

## Parallel Example: User Story 1

```bash
# Launch test authoring for User Story 1 together:
Task: "Unit test synchronous sequential execution of thinker_node returning raciocinio_bruto dictionary in tests/test_instructor_sync_contract.py"
Task: "Unit test synchronous execution of extractor_node using instructor schema decoding returning cortes_finais dictionary in tests/test_instructor_sync_contract.py"
Task: "Integration test verifying create_graph compilation and app.invoke execution with stubbed/mocked peripheral I/O nodes emits zero RuntimeWarning coroutine warnings in tests/test_instructor_sync_contract.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001, T002)
2. Complete Phase 2: Foundational (T003, T004)
3. Complete Phase 3: User Story 1 (T005–T009)
4. **STOP and VALIDATE**: Run `PYTHONPATH=src venv/bin/python -m unittest tests/test_instructor_sync_contract.py` to confirm US1 is fully operational
5. Deliver MVP!

### Incremental Delivery

1. Complete Setup + Foundational → Core baseline ready
2. Deliver US1 (T005–T009) → Thinker and Extractor nodes operate purely synchronously without coroutine overhead (MVP)
3. Deliver US2 (T010–T014) → Automated architectural assertions prevent future async leaks or client misuse
4. Deliver US3 (T015–T017) → Deterministic HTTP socket closure guaranteed on all error branches
5. Deliver Polish (T018–T021) → Full repository test pass, quickstart validation, and documentation synchronization

### Parallel Team Strategy

With multiple developers:
1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: Implements and tests User Story 1 (`thinker_node` and `extractor_node` synchronous execution)
   - Developer B: Tests User Story 2 (graph node reflection and client factory type validation)
   - Developer C: Tests User Story 3 (`try-finally` teardown across timeout and error scenarios)
3. Stories integrate cleanly through `tests/test_instructor_sync_contract.py`

---

## Notes

- [P] tasks = different files or decoupled test scenarios, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability ([US1], [US2], [US3])
- Every task strictly adheres to `- [ ] [TaskID] [P?] [Story?] Description with file path`
- Clean Code rules from AGENTS.md §8 apply: English nomenclature, minimal comments focusing on "why"
