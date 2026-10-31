---
description: "Task list for feature Dynamic Scene Scripting via Constrained Decoding implementation"
---

# Tasks: Dynamic Scene Scripting via Constrained Decoding

**Input**: Design documents from `/specs/016-dynamic-scene-scripting/`  
**Prerequisites**: [plan.md](plan.md) (required), [spec.md](spec.md) (required for user stories), [data-model.md](data-model.md), [research.md](research.md), [contracts/corte_video_schema.json](contracts/corte_video_schema.json), [quickstart.md](quickstart.md)

**Tests**: Unit, regression, contract, and persistence tests are explicitly required by `spec.md` (FR-003, FR-009, SC-001–SC-005) and `plan.md`.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files or independent test scenarios)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Single Python project: `src/clipper/`, `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify virtual environment, core dependencies (`pydantic`, `instructor`, `openai`, `langgraph`), and test runner baseline before modifying core schemas.

- [ ] T001 Verify virtual environment, core dependencies (pydantic, instructor, openai, langgraph), and test runner baseline via tests/test_instructor_sync_contract.py
- [ ] T002 [P] Inspect specs/016-dynamic-scene-scripting/contracts/corte_video_schema.json against target CorteVideo model definition in src/clipper/core/schemas.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models and schema contracts that MUST be complete before any user story or prompt refactoring can proceed.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 [P] Implement contract test verifying openai.pydantic_function_tool schema generation for CortesResponse matches specs/016-dynamic-scene-scripting/contracts/corte_video_schema.json in tests/test_scene_scripting.py
- [ ] T004 [P] Implement unit tests for Scene validation constraints (non-empty strings) and CorteVideo backward compatibility with scenes default_factory in tests/test_scene_scripting.py
- [ ] T005 Implement Scene Pydantic model and extend CorteVideo with scenes: list[Scene] in src/clipper/core/schemas.py

**Checkpoint**: Foundation ready - `Scene` and `CorteVideo.scenes` defined and validated against JSON schema contract. User story implementation can now begin.

---

## Phase 3: User Story 1 - Cortes com cenas segmentadas e enriquecidas (Priority: P1) 🎯 MVP

**Goal**: Extractor node processes strategic reasoning and returns cuts subdivided into 2–4 second sequential `Scene` segments enriched with visual metaphors and animation triggers via Constrained Decoding (`instructor` + Pydantic JSON schema), enforcing fail-fast validation on empty scenes and logging editorial duration warnings for scenes > 4s (FR-001, FR-002, FR-003, FR-006, FR-009, SC-001, SC-003).

**Independent Test**: Execute `extractor_node` with a mocked LLM client returning cuts with scenes, verifying that `cortes_finais` contains valid scenes with all four non-empty fields, that an empty `scenes: []` list triggers a fail-fast `ValueError`, and that scene duration > 4s issues a warning log without rejecting the cut.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they fail before full implementation**

- [ ] T006 [P] [US1] Unit test extractor_node scene extraction and cortes_finais dictionary mapping with mocked instructor client in tests/test_scene_scripting.py
- [ ] T007 [P] [US1] Unit test extractor_node fail-fast behavior when LLM returns cuts with empty scenes in tests/test_scene_scripting.py
- [ ] T008 [P] [US1] Unit test extractor_node editorial duration warning for scenes exceeding 4 seconds and graceful fallback when word_timestamps is empty in tests/test_scene_scripting.py
- [ ] T009 [P] [US1] Update SAMPLE_CORTES_JSON with valid scenes fixture and add contract test for instructor synchronous client call with Scene schema and response_format strictness in tests/test_instructor_sync_contract.py

### Implementation for User Story 1

- [ ] T010 [US1] Harden extractor_node with fail-fast validation on empty scenes and word_timestamps-based editorial duration logging (> 4s) with graceful fallback in src/clipper/core/orchestrator.py
- [ ] T011 [US1] Add structured cut and scene count logging to extractor_node execution summary in src/clipper/core/orchestrator.py

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently (MVP delivered!).

---

## Phase 4: User Story 2 - LLM recebe instruções claras para mapear falas em gatilhos visuais (Priority: P2)

**Goal**: Refactor Extractor system prompt template and few-shot examples so the LLM autonomously partitions speech into 2–4 second logical scenes with contextual visual metaphors and dynamic animation triggers across both Ollama (local) and Gemini (API) profiles (FR-004, FR-005, FR-007).

**Independent Test**: Validate that `EXTRACTOR_SYSTEM_PROMPT_TEMPLATE` contains explicit scene segmentation rules (2–4s duration, visual metaphors, animation triggers), that all few-shot assistant messages parse strictly into `CortesResponse` with valid `scenes`, and that both simulated Ollama and Gemini client profiles produce valid Pydantic structures.

### Tests for User Story 2

- [ ] T012 [P] [US2] Unit test verifying EXTRACTOR_SYSTEM_PROMPT_TEMPLATE instructions and validating that all EXTRACTOR_FEW_SHOT_EXAMPLES assistant payloads parse strictly into CortesResponse in tests/test_scene_scripting.py
- [ ] T013 [P] [US2] Unit test verifying LLM provider neutrality for scene extraction across Ollama and Gemini response mock fixtures in tests/test_scene_scripting.py

### Implementation for User Story 2

- [ ] T014 [US2] Refactor EXTRACTOR_SYSTEM_PROMPT_TEMPLATE with 2-4s scene segmentation rules, visual metaphors, and animation triggers in src/clipper/core/prompts.py
- [ ] T015 [US2] Update EXTRACTOR_FEW_SHOT_EXAMPLES with complete multi-scene assistant examples featuring diverse metaphors and animation triggers in src/clipper/core/prompts.py

**Checkpoint**: At this point, User Stories 1 AND 2 work together: Extractor prompts clearly direct LLMs to script scenes with high-variety metaphors and triggers.

---

## Phase 5: User Story 3 - Cenas persistidas e visíveis na revisão humana (Priority: P3)

**Goal**: Persist scenes transparently across SQLite checkpoints via `SqliteSaver`, serialize them into `review.json` manifests, and render structured scene breakdowns in the human review web interface (`http://localhost:8765`) without crashing or breaking layout (FR-008, SC-005).

**Independent Test**: Serialize cuts with scenes into `ReviewManifest`, write to `review.json`, load the file, and verify `scenes` are preserved; verify `render_review_page` includes `<div class="scenes">` markup with word bounds, metaphors, and triggers, and test that SQLite checkpointer restores `cortes_finais` with intact scenes after simulated interruption.

### Tests for User Story 3

- [ ] T016 [P] [US3] Unit test ReviewManifest serialization and deserialization of cuts with scenes into review.json in tests/test_review.py
- [ ] T017 [P] [US3] Unit test render_review_page HTML generation asserting scene breakdown details are displayed when scenes are present and omitted when empty in tests/test_review.py
- [ ] T018 [P] [US3] Integration test verifying SqliteSaver checkpoint persistence and crash recovery of cortes_finais with scenes in tests/test_scene_scripting.py

### Implementation for User Story 3

- [ ] T019 [US3] Update render_review_page to format and render scene breakdowns within each cut card in src/clipper/review/review.py
- [ ] T020 [US3] Verify end-to-end review lifecycle with prepare_review and create_review_server serving scene cards in tests/test_review.py

**Checkpoint**: All user stories (US1, US2, US3) are implemented, tested, and integrated with the review dashboard and state persistence.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verify non-regression across all existing tests (SC-004), verify static analysis compliance (zero regex/manual json.loads, SC-002), benchmark execution overhead (SC-003), validate quickstart workflow, and synchronize project documentation.

- [ ] T021 [P] Static analysis scan asserting zero occurrences of regex or manual json.loads in LLM extraction layer (SC-002) in tests/test_scene_scripting.py
- [ ] T022 [P] Benchmark execution overhead of extractor_node with scenes asserting mock execution completes strictly under 50ms wall-clock (SC-003) in tests/test_scene_scripting.py
- [ ] T023 Execute full discovery test suite across tests/ to verify zero regressions across existing 172 tests (SC-004)
- [ ] T024 Validate operational quickstart workflow per specs/016-dynamic-scene-scripting/quickstart.md
- [ ] T025 Synchronize project documentation, architecture details, and schema updates across README.md, AGENTS.md, and GEMINI.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 completion - BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Phase 2 completion. Delivers core scene scripting MVP.
- **User Story 2 (Phase 4)**: Depends on Phase 2 (schemas) and Phase 3 (extractor node). Enriches prompts and few-shot examples.
- **User Story 3 (Phase 5)**: Depends on Phase 2 (schemas) and Phase 3 (extractor output). Enhances HITL review and checkpoint verification.
- **Polish (Phase 6)**: Depends on all user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Foundational prerequisites (T003–T005) must complete first.
- **User Story 2 (P2)**: Requires US1 schema and extractor node handling (T005, T010).
- **User Story 3 (P3)**: Requires US1 schema (T005) and `ReviewManifest` model integration. Can proceed concurrently with US2.

### Within Each User Story

- Test tasks marked `[P]` should be written and verified before or concurrently with implementation.
- Core schema and validation precede DAG orchestration (`orchestrator.py`).
- Extractor node formatting precedes HITL presentation (`review.py`).
- Checkpoints validate each story independently before moving to next.

---

## Parallel Opportunities

- **Phase 1**: T001 and T002 can run in parallel.
- **Phase 2**: T003 and T004 test development can run in parallel.
- **Phase 3 (US1)**: Test scenarios T006, T007, T008, T009 can be written in parallel before orchestrator modification.
- **Phase 4 (US2)**: Test scenarios T012 and T013 can be drafted in parallel before prompt refactoring.
- **Phase 5 (US3)**: Test scenarios T016, T017, and T018 can be developed in parallel.
- **Phase 6**: T021 and T022 can run in parallel; T024 and T025 can run in parallel after T023 passes.

---

## Parallel Example: User Story 1

```bash
# Launch test creation for User Story 1 in parallel:
Task T006: "Unit test extractor_node scene extraction and cortes_finais dictionary mapping with mocked instructor client in tests/test_scene_scripting.py"
Task T007: "Unit test extractor_node fail-fast behavior when LLM returns cuts with empty scenes in tests/test_scene_scripting.py"
Task T008: "Unit test extractor_node editorial duration warning for scenes exceeding 4 seconds in tests/test_scene_scripting.py"
Task T009: "Contract test for instructor synchronous client call with Scene schema and response_format strictness in tests/test_instructor_sync_contract.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T002)
2. Complete Phase 2: Foundational (T003–T005)
3. Complete Phase 3: User Story 1 (T006–T011)
4. **STOP and VALIDATE**: Test User Story 1 independently with `PYTHONPATH=src venv/bin/python -m unittest tests/test_scene_scripting.py tests/test_instructor_sync_contract.py`
5. Verify `cortes_finais` produces cuts with segmented scenes without regex or manual JSON parsing.

### Incremental Delivery

1. Setup + Foundation: `Scene` Pydantic model + `CorteVideo.scenes` field contract
2. Add US1 (MVP): `extractor_node` scene extraction + fail-fast guard + duration warning → Test independently
3. Add US2: `prompts.py` updated with 2–4s scene rules and multi-scene few-shot demonstrations → Test independently
4. Add US3: `review.py` HTML breakdown card presentation + SQLite checkpoint persistence → Test independently
5. Polish: Cross-suite regression testing (172+ tests) + static analysis (zero regex) + benchmark (overhead <= 20%) + docs update

---

## Notes

- All state stored in `VideoState.cortes_finais` must be standard JSON-serializable dictionaries (`[cut.model_dump() for cut in cortes]`) for transparent `SqliteSaver` SQLite checkpointing.
- `extractor_node` remains strictly synchronous (`def`) using `instructor.from_openai` and deterministically closing connections in `finally: raw_client.close()`.
- Single-model cognitive routing is strictly maintained: no third LLM node is introduced; the same model handles Thinker and Extractor.
