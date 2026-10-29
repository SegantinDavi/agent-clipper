---
description: "Task list for feature Checkpoint Thread ID Hardening implementation"
---

# Tasks: Checkpoint Thread ID Hardening

**Input**: Design documents from `/specs/011-checkpoint-thread-id-hardening/`
**Prerequisites**: [plan.md](plan.md) (required), [spec.md](spec.md) (required for user stories), [research.md](research.md), [data-model.md](data-model.md), [contracts/checkpoint-thread-id-contract.md](contracts/checkpoint-thread-id-contract.md), [quickstart.md](quickstart.md)

**Tests**: Unit tests are explicitly required by FR-007 and success criteria SC-001/SC-002 in `spec.md`.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Single Python project: `src/clipper/`, `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify test environment, runner dependencies, and runtime configuration constants

- [x] T001 Verify test environment and runner dependencies via tests/test_llm_api.py
- [x] T002 [P] Inspect runtime configuration variables in src/clipper/runtime/config.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure and extraction helper that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Implement extract_video_id helper function for FR-008 in src/clipper/core/ingestion.py
- [x] T004 [P] Re-export or integrate extract_video_id in src/clipper/core/orchestrator.py
- [x] T005 Implement core checkpoint_thread_id function with SHA-256 16-hex digest, canonical delimiter format including LLM_BASE_URL (FR-001, FR-002), and inline invalidation warning (FR-005) in src/clipper/core/orchestrator.py

**Checkpoint**: Foundation ready - video ID extraction and baseline hash calculation in place. User story implementation can now begin.

---

## Phase 3: User Story 1 - Retomada Segura em Perfil Diferente (Priority: P1) 🎯 MVP

**Goal**: Isolate checkpointer thread ID across different LLM providers (`ollama` vs `gemini`), models, and endpoints for the same video so runs start from scratch without context pollution or VRAM conflicts.

**Independent Test**: Call `checkpoint_thread_id` with different `llm_provider`, `model_name`, or `llm_base_url` values and verify that distinct 16-character hexadecimal thread IDs are generated, and that default values fallback safely when parameters are `None`.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they fail before full implementation**

- [x] T006 [P] [US1] Unit test provider isolation and 16-hex length format in tests/test_checkpoint_thread_id.py
- [x] T007 [P] [US1] Unit test model name and endpoint (LLM_BASE_URL) isolation in tests/test_checkpoint_thread_id.py
- [x] T008 [P] [US1] Unit test provider, model, and endpoint default fallbacks when None in tests/test_checkpoint_thread_id.py

### Implementation for User Story 1

- [x] T009 [US1] Implement provider, model, and endpoint normalization with config fallbacks in checkpoint_thread_id in src/clipper/core/orchestrator.py
- [x] T010 [US1] Update orchestrator main() startup log to emit calculated thread_id and video_id at INFO level in src/clipper/core/orchestrator.py
- [x] T011 [US1] Verify provider, model, and endpoint isolation assertions in tests/test_llm_api.py against new 16-hex format without weakening test coverage

**Checkpoint**: User Story 1 is fully functional and testable independently. Provider, model, and endpoint switches cleanly isolate execution state.

---

## Phase 4: User Story 2 - Retomada Segura com Configuração de Silêncio Diferente (Priority: P2)

**Goal**: Isolate checkpointer thread ID when silence cutting configuration changes (`SILENCE_CUT_ENABLED` or `SILENCE_MIN_PAUSE`) so incompatible pause plans and cut approvals (`review.json`) are not reused.

**Independent Test**: Call `checkpoint_thread_id` with differing silence cut toggles and pause durations and assert distinct thread IDs.

### Tests for User Story 2

- [x] T012 [P] [US2] Unit test silence cut toggle (True vs False) isolation in tests/test_checkpoint_thread_id.py
- [x] T013 [P] [US2] Unit test silence minimum pause duration isolation in tests/test_checkpoint_thread_id.py
- [x] T014 [P] [US2] Unit test silence parameters safe fallbacks and boolean/float normalization in tests/test_checkpoint_thread_id.py

### Implementation for User Story 2

- [x] T015 [US2] Implement boolean and float normalization for silence parameters with config defaults in src/clipper/core/orchestrator.py
- [x] T016 [US2] Verify silence configuration isolation test in tests/test_pause_editing.py against new 16-hex format

**Checkpoint**: User Stories 1 and 2 work independently. Silence configuration changes trigger fresh thread IDs.

---

## Phase 5: User Story 3 - Retomada Legítima do Estado (Priority: P3)

**Goal**: Ensure 100% deterministic idempotency across crashes and runs with identical parameters (same video, provider, model, endpoint, and silence settings) so LangGraph checkpointer legitimately resumes from saved checkpoints, while `--restart` continues to purge thread checkpoints.

**Independent Test**: Call `checkpoint_thread_id` repeatedly with identical parameters to verify idempotency, and test thread purging with `SqliteSaver` using the new thread ID format.

### Tests for User Story 3

- [x] T017 [P] [US3] Unit test deterministic idempotency across multiple invocations in tests/test_checkpoint_thread_id.py
- [x] T018 [P] [US3] Unit test raw video ID preservation and URL extraction consistency (FR-008) in tests/test_checkpoint_thread_id.py
- [x] T019 [P] [US3] Integration test checkpointer resumption and thread purge with hardened thread ID in tests/test_checkpoint_thread_id.py

### Implementation for User Story 3

- [x] T020 [US3] Integrate extracted video_id into orchestrator startup and checkpointer invocation in src/clipper/core/orchestrator.py

**Checkpoint**: All three user stories are functional. Idempotency guarantees safe crash recovery while preventing cross-contamination.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verification, end-to-end regression validation, and documentation synchronization

- [x] T021 [P] Run quickstart.md validation scenarios in specs/011-checkpoint-thread-id-hardening/quickstart.md
- [x] T022 Execute full project test suite via tests/
- [x] T023 [P] Synchronize documentation and development guidelines in GEMINI.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational completion. Forms the MVP.
- **User Story 2 (Phase 4)**: Depends on Foundational completion (and builds on Phase 3 thread derivation).
- **User Story 3 (Phase 5)**: Depends on Foundational and User Stories 1 & 2 completion for full idempotency and checkpointer integration.
- **Polish (Phase 6)**: Depends on all user story phases being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories.
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Expands canonical payload with silence configuration.
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Validates end-to-end idempotency, crash recovery, and restart purging across all parameters.

### Within Each User Story

- Unit tests written first and verified to fail or establish the baseline before full implementation.
- Normalization logic before integration into orchestrator.
- Existing regression tests synchronized alongside new behavior.

### Parallel Opportunities

- In Phase 1: `T002` can run in parallel with `T001`.
- In Phase 2: `T004` can run in parallel with `T003`.
- In Phase 3: Tests `T006`, `T007`, and `T008` can be written in parallel.
- In Phase 4: Tests `T012`, `T013`, and `T014` can be written in parallel.
- In Phase 5: Tests `T017` and `T018` can be written in parallel.
- In Phase 6: Quickstart validation `T021` and documentation sync `T023` can run in parallel with review.

---

## Parallel Example: User Story 1

```bash
# Launch unit tests for User Story 1 together:
Task: "Unit test provider isolation and 16-hex length format in tests/test_checkpoint_thread_id.py"
Task: "Unit test model name isolation in tests/test_checkpoint_thread_id.py"
Task: "Unit test provider and model default fallbacks when None in tests/test_checkpoint_thread_id.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (`T001`, `T002`).
2. Complete Phase 2: Foundational (`T003`, `T004`, `T005`).
3. Complete Phase 3: User Story 1 (`T006` - `T011`).
4. **STOP and VALIDATE**: Run `tests/test_checkpoint_thread_id.py` and `tests/test_llm_api.py` to confirm provider/model context isolation.

### Incremental Delivery

1. Setup + Foundational → Core video extraction and canonical SHA-256[:16] function ready.
2. Add User Story 1 → Provider & model isolation active (MVP!).
3. Add User Story 2 → Silence detection & pause duration isolation active.
4. Add User Story 3 → Idempotency, crash resumption, and `--restart` purge verified.
5. Polish → Quickstart validated, full regression test suite passed, docs synced.

### Parallel Team Strategy

With multiple developers:
1. Complete Setup + Foundational together.
2. Developer A implements User Story 1 (`tests/test_llm_api.py` & provider isolation).
3. Developer B implements User Story 2 (`tests/test_pause_editing.py` & silence isolation).
4. Developer C validates User Story 3 (idempotency, SQLite checkpointer resumption, and purge).

---

## Notes

- `[P]` tasks = different files or decoupled test cases, no dependencies.
- `[Story]` label maps each task strictly to `[US1]`, `[US2]`, or `[US3]` for traceability.
- Follows `AGENTS.md` rules strictly: English naming, no external telemetry collectors, standard logging to `pipeline.log`.
- Altering the identity formula or `checkpoint_thread_id` invalidates pre-existing checkpoints in `estado.db`.
