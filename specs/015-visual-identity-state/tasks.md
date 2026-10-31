---
description: "Task list for feature Visual Identity & Global State implementation"
---

# Tasks: Visual Identity & Global State

**Input**: Design documents from `/specs/015-visual-identity-state/`  
**Prerequisites**: [plan.md](plan.md) (required), [spec.md](spec.md) (required for user stories), [data-model.md](data-model.md), [research.md](research.md), [contracts/visual_identity_schema.json](contracts/visual_identity_schema.json), [quickstart.md](quickstart.md)

**Tests**: Unit, regression, and checkpoint integration tests are explicitly required by `spec.md` (FR-005, SC-001–SC-006) and `plan.md`.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files or independent test scenarios)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Single Python project: `src/clipper/`, `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify virtual environment, dependencies (`pydantic`, `langgraph`, `moviepy`), and existing test suite baseline before implementing new nodes.

- [X] T001 Verify virtual environment, core dependencies (pydantic, langgraph, moviepy), and test runner baseline via tests/test_editor_render.py
- [X] T002 [P] Inspect contracts/visual_identity_schema.json against CAPTION_* definitions in src/clipper/runtime/config.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data model and loader logic that MUST be complete before any user story or graph integration can proceed.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Implement VisualIdentityConfig Pydantic model with per-field defaults, positive numeric constraints, and hex validation in src/clipper/core/style_loader.py
- [X] T004 Implement load_visual_identity function with schema flattening, JSON syntax error handling (JSONDecodeError), and fallback logic in src/clipper/core/style_loader.py
- [X] T005 Scaffold unit and integration test suite with temporary file fixtures in tests/test_style_node.py

**Checkpoint**: Foundation ready - VisualIdentityConfig and loader logic ready. User story implementation can now begin.

---

## Phase 3: User Story 1 - Pipeline Runs with Custom Brand Style (Priority: P1) 🎯 MVP

**Goal**: Enable the pipeline to load visual style definitions from `estilo.json` via a new synchronous `style_node`, store them in `VideoState.visual_identity`, and apply typography, color palette, and motion rules during caption creation and video formatting in `editor.py` (FR-001, FR-002, FR-003, FR-004, FR-006, FR-007, FR-010, SC-001, SC-002).

**Independent Test**: Place a valid `estilo.json` in the workspace root, execute `style_node`, and verify `VideoState.visual_identity` receives the custom values. Then render a test clip using `cut_and_format_video` and assert captions reflect custom styling (e.g., custom caption color and font size) instead of module defaults; when `estilo.json` is missing, verify pipeline defaults are applied without exception.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they fail before full implementation**

- [X] T006 [P] [US1] Unit test VisualIdentityConfig validation, flattening, and defaults in tests/test_style_node.py
- [X] T007 [P] [US1] Unit test style_node execution and return dictionary update in tests/test_style_node.py
- [X] T008 [P] [US1] Contract test verifying create_graph DAG edges and synchronous node compliance in tests/test_style_node.py
- [X] T009 [P] [US1] Unit test create_caption_clip, position_caption_clip, and group_caption_words with custom visual_identity in tests/test_style_node.py

### Implementation for User Story 1

- [X] T010 [US1] Add visual_identity field to VideoState TypedDict and initial_state in src/clipper/core/orchestrator.py
- [X] T011 [US1] Implement synchronous style_node in src/clipper/core/orchestrator.py
- [X] T012 [US1] Wire style_node into create_graph between fatiamento and transcricao in src/clipper/core/orchestrator.py
- [X] T013 [US1] Update create_caption_clip, position_caption_clip, and group_caption_words to accept visual_identity in src/clipper/video/editor.py
- [X] T014 [US1] Update cut_and_format_video to accept visual_identity and pass to caption helpers in src/clipper/video/editor.py
- [X] T015 [US1] Update editor_node to pass visual_identity from state to cut_and_format_video in src/clipper/core/orchestrator.py

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently (MVP delivered!).

---

## Phase 4: User Story 2 - Visual Style Survives Checkpoint Recovery (Priority: P2)

**Goal**: Ensure `visual_identity` state survives pipeline crashes and process interruptions via `SqliteSaver` checkpoints, restoring the style without re-reading `estilo.json`, while honoring `--restart` thread checkpoint purges (FR-005, SC-003).

**Independent Test**: Execute the pipeline through `style_node`, save state via `SqliteSaver`, simulate crash/reload from SQLite database, and assert `visual_identity` is restored identical to the original state; verify `--restart` with `purge_thread_checkpoints` purges the thread and re-reads `estilo.json`.

### Tests for User Story 2

- [X] T016 [P] [US2] Integration test verifying SqliteSaver checkpoint persistence and state recovery for visual_identity in tests/test_style_node.py
- [X] T017 [P] [US2] Integration test verifying --restart purges checkpoints and re-executes style_node in tests/test_style_node.py

### Implementation for User Story 2

- [X] T018 [US2] Validate JSON-primitive serializability of visual_identity state dictionary in src/clipper/core/style_loader.py

**Checkpoint**: At this point, User Stories 1 AND 2 work together: custom styles are rendered and survive container crashes/restarts.

---

## Phase 5: User Story 3 - Operator Inspects Loaded Style at Runtime (Priority: P3)

**Goal**: Provide runtime observability in `pipeline.log` so operators can inspect all loaded style values, identify missing fields falling back to defaults, and spot malformed hex colors without inspecting SQLite database internals (FR-008, FR-009, SC-006).

**Independent Test**: Invoke `style_loader` and `style_node` under scenarios with valid file, absent file, missing fields, and invalid hex colors, asserting structured INFO and WARNING log entries are emitted to the logger/log file.

### Tests for User Story 3

- [X] T019 [P] [US3] Unit test verifying INFO log entries upon successful estilo.json loading in tests/test_style_node.py
- [X] T020 [P] [US3] Unit test verifying WARNING log entries for absent estilo.json, corrupted JSON syntax, and fallback keys in tests/test_style_node.py

### Implementation for User Story 3

- [X] T021 [US3] Add structured INFO and WARNING log formatting with style_node prefix for loaded styles and missing keys in src/clipper/core/style_loader.py

**Checkpoint**: All user stories (US1, US2, US3) are implemented, tested, and observable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verify non-regression across all existing pipeline tests, enforce execution timing budgets, and update project documentation.

- [X] T022 Execute full test suite discover via tests/ to verify zero regressions across the codebase
- [X] T023 [P] Verify wall-clock execution overhead benchmark of style_node remains under 100ms in tests/test_style_node.py
- [X] T024 [P] Update operational documentation, architecture DAG diagram, and configuration reference in AGENTS.md, GEMINI.md, and README.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 completion - BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Phase 2 completion. Delivers core brand style MVP.
- **User Story 2 (Phase 4)**: Depends on Phase 3 (needs `VideoState.visual_identity` and `style_node`).
- **User Story 3 (Phase 5)**: Can proceed alongside Phase 3/4 or immediately after, polishing log observability.
- **Polish (Phase 6)**: Depends on all user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Foundational prerequisites (T003–T005) must complete first.
- **User Story 2 (P2)**: Requires US1 state definition (T010) and `style_node` implementation (T011).
- **User Story 3 (P3)**: Requires `load_visual_identity` (T004) and `style_node` (T011).

### Within Each User Story

- Test tasks marked `[P]` should be written and verified before or concurrently with implementation.
- Model and loader logic (`style_loader.py`) precedes DAG orchestration (`orchestrator.py`).
- Orchestrator state passing precedes editor consumption (`editor.py`).
- Checkpoints validate each story independently before moving to next.

---

## Parallel Opportunities

- **Phase 1**: T001 and T002 can run in parallel.
- **Phase 2**: T005 can run in parallel with T003/T004; T004 runs sequentially after T003.
- **Phase 3 (US1)**: Test scenarios T006, T007, T008, T009 can be drafted in parallel before implementation.
- **Phase 4 (US2)**: Integration test scenarios T016 and T017 can be developed in parallel.
- **Phase 5 (US3)**: Logging test scenarios T019 and T020 can be developed in parallel.
- **Phase 6**: T023 and T024 can run in parallel after T022 completes.

---

## Parallel Example: User Story 1

```bash
# Launch test creation for User Story 1 in parallel:
Task T006: "Unit test VisualIdentityConfig validation, flattening, and defaults in tests/test_style_node.py"
Task T007: "Unit test style_node execution, return dictionary update, and timing (<100ms) in tests/test_style_node.py"
Task T008: "Contract test verifying create_graph DAG edges and synchronous node compliance in tests/test_style_node.py"
Task T009: "Unit test create_caption_clip, position_caption_clip, and group_caption_words with custom visual_identity in tests/test_style_node.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T002)
2. Complete Phase 2: Foundational (T003–T005)
3. Complete Phase 3: User Story 1 (T006–T015)
4. **STOP and VALIDATE**: Test User Story 1 independently with `PYTHONPATH=src venv/bin/python -m unittest tests/test_style_node.py`
5. Verify custom caption styling renders into video clips with `estilo.json` present and falls back gracefully when absent.

### Incremental Delivery

1. Setup + Foundation: `VisualIdentityConfig` Pydantic model + `load_visual_identity()`
2. Add US1 (MVP): `style_node` + `VideoState` + `editor.py` parameterization → Test independently
3. Add US2: Checkpoint resilience + `--restart` recovery → Test independently
4. Add US3: Structured logging and observability → Test independently
5. Polish: Cross-suite regression testing + wall-clock benchmark (<100ms) + docs update

---

## Notes

- All state stored in `VideoState.visual_identity` must be flat dictionaries of primitive types (`str`, `int`, `float`, `bool`) for clean SQLite serialization.
- `style_node` is strictly synchronous (`def`) to satisfy the architectural contract enforced by `create_graph()`.
- Existing `CAPTION_*` constants in `config.py` remain untouched as the final fallback mechanism.
