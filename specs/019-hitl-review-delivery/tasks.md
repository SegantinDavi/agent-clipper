# Tasks: HITL Review Delivery — Script Display & Conditional Rendering

**Input**: Design documents from `/specs/019-hitl-review-delivery/`  
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/  

**Tests**: Tests are included as explicitly specified in spec.md (SC-004) and plan.md.  

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/clipper/`, `tests/` at repository root
- Affects `src/clipper/review/review.py`, `src/clipper/core/orchestrator.py`, and `tests/test_review_delivery.py`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Test infrastructure initialization and shared test fixtures

- [ ] T001 Initialize test suite structure and mock fixtures in tests/test_review_delivery.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core schema synchronizations that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T002 Implement bidirectional approved_ids and approved_cut_ids synchronization in ApprovalDecision, save_approval_decision, load_approval_decision, and update validate_approval to support string identifiers and integer indices safely in src/clipper/review/review.py
- [ ] T003 Update VideoState TypedDict to support approved_cut_ids: list[int | str] in src/clipper/core/orchestrator.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - View Scene Script Before Rendering (Priority: P1) 🎯 MVP

**Goal**: Reviewers can inspect visual metaphors, animation triggers, and scene timing in preview cards before approval, with explicit fallbacks ("No scene script available"), placeholders ("—"), and responsive styles across 320 px to 1920 px viewports.

**Independent Test**: Invoke `render_review_page()` with cuts containing complete scenes, empty scenes, and scenes with empty/whitespace fields, and assert correct DOM structure, escaped HTML, fallback elements, and CSS responsive rules.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T004 [P] [US1] Create unit and contract tests for render_review_page scene display, "No scene script available" fallback, and "—" placeholders in tests/test_review_delivery.py
- [ ] T005 [P] [US1] Create unit tests for viewport responsiveness CSS (meta viewport, word-break, mobile max-width 480px rules) in tests/test_review_delivery.py

### Implementation for User Story 1

- [ ] T006 [US1] Implement scene field sanitization and "—" placeholders for visual_metaphor, animation_trigger, and timing words with html.escape in src/clipper/review/review.py
- [ ] T007 [US1] Implement empty/null scenes fallback container rendering "No scene script available" in render_review_page in src/clipper/review/review.py
- [ ] T008 [US1] Add responsive CSS rules for scenes container and mobile viewports down to 320px in render_review_page in src/clipper/review/review.py
- [ ] T009 [US1] Run User Story 1 test suite to verify implementation passes independently via PYTHONPATH=src venv/bin/python -m unittest tests/test_review_delivery.py tests/test_review.py

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Approve Only Selected Cuts for Rendering (Priority: P2)

**Goal**: Ensure the coder and execution nodes process only cuts explicitly present in `approved_cut_ids` from `decision.json`, skipping unapproved cuts with INFO log, terminating empty approvals directly at `END` in < 5s without subprocesses, and failing fast on missing or malformed `decision.json`.

**Independent Test**: Execute `coder_node` and `create_graph` with mock decision payloads (partial approval, empty approval, missing `decision.json`, unknown cut IDs) and verify 0% subprocesses for unapproved cuts, skip logs, graceful empty-selection completion, and fast `ValueError` failure on corrupted `decision.json`.

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T010 [P] [US2] Create unit and contract tests for decision.json fail-fast validation (missing, malformed) in coder_node in tests/test_review_delivery.py
- [ ] T011 [P] [US2] Create unit and integration tests for cut gating, skip logging (INFO), unmatched cut ID handling (WARNING), and 0% subprocesses for unapproved cuts in tests/test_review_delivery.py
- [ ] T012 [P] [US2] Create unit and integration tests for route_approval_outcome empty approval routing to END with zero subprocesses in tests/test_review_delivery.py
- [ ] T013 [P] [US2] Create resumption test verifying checkpoint reload re-applies decision.json from review directory in tests/test_review_delivery.py

### Implementation for User Story 2

- [ ] T014 [US2] Implement fail-fast decision.json validation in coder_node (raising ValueError if missing or malformed when review_directory is present) in src/clipper/core/orchestrator.py
- [ ] T015 [US2] Implement deterministic cut resolution (dict id, cut-{i} 0-based pattern, 1-based integer), cut gating logic, and single-pass skip audit logging in coder_node in src/clipper/core/orchestrator.py
- [ ] T016 [US2] Implement route_approval_outcome conditional edge and wire conditional edges in create_graph in src/clipper/core/orchestrator.py
- [ ] T017 [US2] Add defensive safeguards for empty approved cuts in coder_node and execution_node in src/clipper/core/orchestrator.py
- [ ] T018 [US2] Run User Story 2 test suite to verify implementation passes independently via PYTHONPATH=src venv/bin/python -m unittest tests/test_review_delivery.py tests/test_coder_dag.py

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Regression prevention, end-to-end verification, and documentation synchronization across the project

- [ ] T019 [P] Run full project regression test suite via PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"
- [ ] T020 Execute interactive quickstart verification scenarios from specs/019-hitl-review-delivery/quickstart.md
- [ ] T021 [P] Synchronize feature documentation and operational guidelines in README.md, AGENTS.md, and GEMINI.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational (Phase 2) completion
- **User Story 2 (Phase 4)**: Depends on Foundational (Phase 2) completion (can be implemented in parallel with US1 if staffed, or sequentially P1 → P2)
- **Polish (Phase 5)**: Depends on completion of User Stories 1 and 2

### User Story Dependencies

- **User Story 1 (P1)**: Operates on `src/clipper/review/review.py`. Independent of User Story 2.
- **User Story 2 (P2)**: Operates on `src/clipper/core/orchestrator.py`. Integrates with schemas updated in Phase 2. Independent of User Story 1 UI display.

### Within Each User Story

- Write test tasks first and confirm they fail before implementation tasks
- Foundation schemas and validators before dependent node logic
- Core node logic before graph conditional routing
- Verify story independently before moving to polish

### Parallel Opportunities

- **Setup & Foundational**:
  - T002 and T003 touch different files (`src/clipper/review/review.py` vs `src/clipper/core/orchestrator.py`) and can run in parallel.
- **User Story 1**:
  - T004 and T005 test tasks can be authored in parallel.
- **User Story 2**:
  - T010, T011, T012, and T013 test tasks can be authored in parallel.
- **Between Stories**:
  - Once Phase 2 (Foundational) is complete, User Story 1 (UI in `src/clipper/review/review.py`) and User Story 2 (gating in `src/clipper/core/orchestrator.py`) can be worked on concurrently as they modify separate modules.

---

## Parallel Example: User Story 1

```bash
# Launch test creation for User Story 1 together:
Task: "Create unit and contract tests for render_review_page scene display, 'No scene script available' fallback, and '—' placeholders in tests/test_review_delivery.py"
Task: "Create unit tests for viewport responsiveness CSS (meta viewport, word-break, mobile max-width 480px rules) in tests/test_review_delivery.py"
```

## Parallel Example: User Story 2

```bash
# Launch test creation for User Story 2 together:
Task: "Create unit and contract tests for decision.json fail-fast validation (missing, malformed) in coder_node in tests/test_review_delivery.py"
Task: "Create unit and integration tests for cut gating, skip logging (INFO), unmatched cut ID handling (WARNING), and 0% subprocesses for unapproved cuts in tests/test_review_delivery.py"
Task: "Create unit and integration tests for route_approval_outcome empty approval routing to END with zero subprocesses in tests/test_review_delivery.py"
Task: "Create resumption test verifying checkpoint reload re-applies decision.json from review directory in tests/test_review_delivery.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002, T003)
3. Complete Phase 3: User Story 1 (T004 - T009)
4. **STOP and VALIDATE**: Verify scene script, metaphors, fallbacks, and responsiveness in review page independently
5. Deliver MVP slice!

### Incremental Delivery

1. Complete Setup + Foundational → Schemas ready for both `approved_ids` and `approved_cut_ids`
2. Add User Story 1 → Reviewers can inspect planned scenes and metaphors before approving (MVP)
3. Add User Story 2 → Coder and execution loop gated strictly to approved cuts; 0% subprocesses for rejected cuts; < 5s empty-selection termination
4. Polish & Cross-cutting → Full regression sweep across 256+ tests, quickstart validation, doc sync

---

## Notes

- All tasks follow strict format: `- [ ] [TaskID] [P?] [Story?] Description with file path`
- Zero new external libraries or telemetry tools introduced (WSL2 / 8 GB RAM compliance)
- Preserves all 256 existing test suites without regression
