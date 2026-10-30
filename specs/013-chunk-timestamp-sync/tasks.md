---
description: "Task list for feature Chunk Timestamp Absolute Sync implementation"
---

# Tasks: Chunk Timestamp Absolute Sync

**Input**: Design documents from `/specs/013-chunk-timestamp-sync/`  
**Prerequisites**: [plan.md](plan.md) (required), [spec.md](spec.md) (required for user stories), [data-model.md](data-model.md), [contracts/apply_chunk_offset.md](contracts/apply_chunk_offset.md)

**Tests**: Unit, regression, and integration tests are explicitly required by `spec.md` (FR-001–FR-010, SC-001–SC-005) and `plan.md`.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Single Python project: `src/clipper/`, `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify virtual environment, existing transcription and pause editing tests before making modifications

- [x] T001 Verify Python virtual environment, dependencies (`faster-whisper`, `moviepy`, `langgraph`), and test runner via tests/test_transcription.py and tests/test_pause_editing.py
- [x] T002 [P] Inspect `node_0_preventive_slicing()` output dictionary schema (`{"chunk_path": ..., "offset": ...}`) in src/clipper/core/node_0.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core function signature and shared test fixtures required before user story wiring

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Define `apply_chunk_offset()` function signature, docstring, and type hints in src/clipper/core/ingestion.py per contracts/apply_chunk_offset.md
- [x] T004 [P] Scaffold test module structure with test fixtures and mocks in tests/test_chunk_timestamp_sync.py

**Checkpoint**: Foundation ready - function scaffolded and test suite structure initialized. User story implementation can now begin.

---

## Phase 3: User Story 1 - Legendas Alinhadas ao Vídeo Original (Priority: P1) 🎯 MVP

**Goal**: Ensure that transcription of multi-chunk videos converts relative word timestamps to absolute video timestamps using chunk offsets, guaranteeing that captions in preview and exported videos align accurately with spoken audio without timing drift (FR-001, FR-002, FR-003, FR-008, FR-009, FR-010, SC-001, SC-002, SC-003).

**Independent Test**: Transcribe a simulated two-chunk video (e.g., Chunk 0 with offset 0.0s, Chunk 1 with offset 720.0s) and verify that all words in Chunk 1 have `start` and `end` shifted by exactly 720.0s with 2-decimal precision, single-chunk videos retain offset 0.0s, INFO logging emits chunk offset stats, and missing offset triggers explicit `ValueError`.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they fail before full implementation**

- [x] T005 [P] [US1] Unit test `apply_chunk_offset` contract (pure function immutability, zero offset, positive offset rounding, empty list) in tests/test_chunk_timestamp_sync.py
- [x] T006 [P] [US1] Unit test `apply_chunk_offset` structured INFO logging formatting ("Chunk %d offset applied: +%.2fs → %d words remapped") in tests/test_chunk_timestamp_sync.py
- [x] T007 [P] [US1] Unit test `transcription_node` single-chunk retrocompatibility and multi-chunk word timestamp offset aggregation in tests/test_chunk_timestamp_sync.py
- [x] T008 [P] [US1] Unit test `transcription_node` fail-fast validation raising `ValueError` when chunk is non-dict, missing `offset`, or negative (FR-010) in tests/test_chunk_timestamp_sync.py

### Implementation for User Story 1

- [x] T009 [US1] Implement `apply_chunk_offset(words: list[dict], offset: float, chunk_index: int) -> list[dict]` with rounding and INFO logging in src/clipper/core/ingestion.py per contracts/apply_chunk_offset.md
- [x] T010 [US1] Refactor `transcription_node` in src/clipper/core/orchestrator.py to validate chunk dict and offset presence (raising `ValueError` on invalid chunk per FR-010) and delegate word timestamp offset shifting to `apply_chunk_offset()`

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently (MVP delivered!).

---

## Phase 4: User Story 2 - Planos de Pausa Corretos nos Cortes Aprovados (Priority: P2)

**Goal**: Ensure that pause shortening and silence detection in `pause_editing.py` and review preview generation operate cleanly on absolute timestamps from multi-chunk transcripts without erroneous pause removals in cuts starting after chunk 0 (FR-007, SC-004).

**Independent Test**: Run `speech_intervals()` and `build_pause_plan()` using word timestamps from a cut located in chunk 2 (e.g. 720s–840s) and verify silence intervals and `.pauses.json` entries map strictly to absolute timeline coordinates `[start_time, end_time]`, and that session restart reloads identical intervals.

### Tests for User Story 2

- [x] T011 [P] [US2] Integration test `speech_intervals` and `build_pause_plan` with multi-chunk absolute timestamps asserting silence intervals map to absolute video coordinates in tests/test_chunk_timestamp_sync.py
- [x] T012 [P] [US2] Integration test verifying `.pauses.json` serialization and restart persistence using multi-chunk absolute cut timestamps in tests/test_chunk_timestamp_sync.py

### Implementation for User Story 2

- [x] T013 [US2] Audit and verify (read-only) pause editing integration with multi-chunk absolute timestamps in src/clipper/video/pause_editing.py and src/clipper/review/review.py without modifying production logic

**Checkpoint**: At this point, User Stories 1 AND 2 should both work together: multi-chunk transcripts have absolute timestamps and downstream pause cutting operates accurately on any cut position.

---

## Phase 5: User Story 3 - Remapeamento de Grupos de Palavras Preservado (Priority: P3)

**Goal**: Ensure that caption word grouping (`remap_word_groups` and `group_caption_words`) correctly handles words crossing chunk boundaries without negative gaps, overlap jumps, or caption drift > 0.1s (FR-005, SC-002).

**Independent Test**: Feed synthetic word sequences spanning a chunk boundary (e.g., last word of chunk 0 at 718.5s–719.8s and first word of chunk 1 at 720.2s–721.0s) through `remap_word_groups` and `group_caption_words` and assert chronological ordering, continuity, and max drift ≤ 0.1s.

### Tests for User Story 3

- [x] T014 [P] [US3] Unit test `remap_word_groups` and `group_caption_words` with cross-chunk boundary word sequences asserting contiguous intervals without negative gaps in tests/test_chunk_timestamp_sync.py
- [x] T015 [P] [US3] Unit test caption sync drift measurement asserting max drift <= 0.1s across chunk transitions in tests/test_chunk_timestamp_sync.py

### Implementation for User Story 3

- [x] T016 [US3] Audit and document (read-only / docstring only) caption grouping continuity across chunk boundaries in src/clipper/video/pause_editing.py and src/clipper/video/editor.py

**Checkpoint**: All three user stories are functional and verified with end-to-end alignment from chunking through transcription, pause editing, and caption grouping.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories, test suite completion, and repository documentation synchronization

- [x] T017 Execute full test suite across the repository via tests/test_*.py
- [x] T018 [P] Synchronize documentation and feature guidelines in GEMINI.md and AGENTS.md
- [x] T019 Review code formatting, type annotations, and Clean Code compliance in src/clipper/core/ingestion.py and src/clipper/core/orchestrator.py

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
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Consumes absolute timestamps guaranteed by US1
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Consumes absolute timestamps guaranteed by US1

### Within Each User Story

- Tests MUST be written and fail before implementation
- Function definition before caller refactoring
- Core logic before integration assertions
- Story verified complete before proceeding to subsequent priorities

### Parallel Opportunities

- T001 and T002 can run in parallel during Setup
- T003 and T004 can run in parallel during Foundation
- Tests within each User Story (T005, T006, T007, T008 in US1; T011, T012 in US2; T014, T015 in US3) can be written in parallel
- Documentation update (T018) can run in parallel with final code review (T019)

---

## Parallel Example: User Story 1

```bash
# Launch test authoring for User Story 1 together:
Task: "Unit test apply_chunk_offset contract (immutability, zero offset, positive offset rounding, empty list) in tests/test_chunk_timestamp_sync.py"
Task: "Unit test apply_chunk_offset structured INFO logging formatting in tests/test_chunk_timestamp_sync.py"
Task: "Unit test transcription_node single-chunk retrocompatibility and multi-chunk word timestamp offset aggregation in tests/test_chunk_timestamp_sync.py"
Task: "Unit test transcription_node fail-fast validation raising ValueError when chunk is non-dict or missing offset in tests/test_chunk_timestamp_sync.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001, T002)
2. Complete Phase 2: Foundational (T003, T004)
3. Complete Phase 3: User Story 1 (T005–T010)
4. **STOP and VALIDATE**: Run `PYTHONPATH=src venv/bin/python -m unittest tests/test_chunk_timestamp_sync.py` to confirm US1 is fully operational
5. Deliver MVP!

### Incremental Delivery

1. Complete Setup + Foundational → Core baseline ready
2. Deliver US1 (T005–T010) → Transcription timestamps are absolute with full logging and error validation (MVP)
3. Deliver US2 (T011–T013) → Pause editing and preview/restart pipelines validated for multi-chunk cuts
4. Deliver US3 (T014–T016) → Caption group continuity and drift verified at chunk boundaries
5. Deliver Polish (T017–T019) → Full test pass and documentation synchronized

### Parallel Team Strategy

With multiple developers:
1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: Implements and tests User Story 1 (`apply_chunk_offset` and `transcription_node`)
   - Developer B: Tests User Story 2 (`speech_intervals` and `build_pause_plan` validation)
   - Developer C: Tests User Story 3 (`remap_word_groups` boundary drift validation)
3. Stories integrate cleanly through `tests/test_chunk_timestamp_sync.py`

---

## Notes

- [P] tasks = different files or decoupled tests, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability ([US1], [US2], [US3])
- Every task strictly adheres to `- [ ] [TaskID] [P?] [Story?] Description with file path`
- Clean Code rules from AGENTS.md §8 apply: English nomenclature, minimal comments focusing on "why"
