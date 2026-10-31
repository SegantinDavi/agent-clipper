# agent-clipper Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-10-28

## Active Technologies
- SQLite (`SqliteSaver` checkpointer in `/app/output/estado.db`), `pipeline.log` in `/app/output/` (011-checkpoint-thread-id-hardening)
- Python 3.12+ (tested on Python 3.12 - 3.14) + `ctranslate2==4.8.3`, `faster-whisper==1.2.1`, `nvidia-cublas-cu12`, `nvidia-cudnn-cu12` (from `requirements-cuda.txt`), `torch` (optional fallback if present) (012-cuda-vram-cleanup)
- File logging in `/app/output/pipeline.log` (012-cuda-vram-cleanup)
- Python 3.12+ + faster-whisper, langgraph, moviepy==1.0.3, pydantic, instructor (013-chunk-timestamp-sync)
- SQLite (`/app/output/estado.db` via `SqliteSaver`), arquivos WAV de chunk em `/app/output/` (013-chunk-timestamp-sync)
- Python 3.12+ (tested on Python 3.12 - 3.14) + langgraph, instructor, openai, pydantic, moviepy==1.0.3, faster-whisper (014-align-instructor-nodes)
- Python 3.12+ + `pydantic` (already in stack), `langgraph` (already in stack), `moviepy==1.0.3` (already in stack) (015-visual-identity-state)
- SQLite via `SqliteSaver` (`/app/output/estado.db`) — `visual_identity` is a plain dict, serialized transparently (015-visual-identity-state)
- Python 3.12+ (tested on Python 3.12 – 3.14) + `pydantic` (already in stack), `instructor` (already in stack), `openai` (already in stack), `langgraph` (already in stack) (016-dynamic-scene-scripting)
- SQLite via `SqliteSaver` (`/app/output/estado.db`), `review.json` in `/app/output/reviews/<id>/` (016-dynamic-scene-scripting)

- Python 3.12+ (tested on Python 3.12 - 3.14) + `langgraph>=0.2.0`, `instructor`, `pydantic`, `moviepy==1.0.3`, `faster-whisper`, `yt-dlp`, `ctranslate2`, `onnxruntime`, `av<19` (010-manual-review-langgraph-integration)

## Project Structure

```text
src/
tests/
```

## Commands

```bash
# Run all unit and integration tests
PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"

# Run CUDA VRAM cleanup and transcription tests
PYTHONPATH=src venv/bin/python -m unittest tests/test_cuda_cleanup.py tests/test_transcription.py

# Run checkpoint thread ID isolation tests
PYTHONPATH=src venv/bin/python -m unittest tests/test_checkpoint_thread_id.py

# Run chunk timestamp sync unit and integration tests
PYTHONPATH=src venv/bin/python -m unittest tests/test_chunk_timestamp_sync.py

# Run review & HITL crash recovery tests
PYTHONPATH=src venv/bin/python -m unittest tests/test_review.py

# Run instructor and LangGraph synchronous contract tests
PYTHONPATH=src venv/bin/python -m unittest tests/test_instructor_sync_contract.py

# Run pipeline execution
bash run_pipeline.sh
```

## Code Style

Python 3.12+ (tested on Python 3.12 - 3.14): Follow standard conventions

## Recent Changes
- 016-dynamic-scene-scripting: Implemented Phase 4 (User Story 2 - LLM receives clear instructions to script scenes). Refactored `EXTRACTOR_SYSTEM_PROMPT_TEMPLATE` with 2-4s scene segmentation rules, visual metaphors, and animation triggers (T014, FR-004). Updated `EXTRACTOR_FEW_SHOT_EXAMPLES` assistant messages with multi-scene structures featuring diverse metaphors and camera triggers (T015, FR-005). Added unit tests in `tests/test_scene_scripting.py` for prompt rule enforcement, few-shot schema validation, and provider neutrality across Ollama and Gemini (T012, T013, FR-007). 100% tests passing (194 tests, 0 regressions).
- 016-dynamic-scene-scripting: Implemented Phase 3 (User Story 1 - MVP). Hardened extractor_node with fail-fast validation on empty scenes (FR-009) and word_timestamps-based pacing duration logging (> 4s guideline) with graceful fallback (T010, T011). Updated SAMPLE_CORTES_JSON and added contract tests for instructor synchronous execution with Scene schema and strict response_format (T009). Added comprehensive unit tests in tests/test_scene_scripting.py (T006-T008). 100% tests passing (190 tests, 0 regressions).
- 016-dynamic-scene-scripting: Added Python 3.12+ (tested on Python 3.12 – 3.14) + `pydantic` (already in stack), `instructor` (already in stack), `openai` (already in stack), `langgraph` (already in stack)
- 015-visual-identity-state: Completed Phase 6 (Polish & Cross-Cutting Concerns). Added wall-clock execution overhead benchmark asserting `style_node` executes in under 100ms (T023, SC-005) in `tests/test_style_node.py`. Updated operational documentation, architecture 9-node DAG diagram, project structure, and `estilo.json` configuration guide across `README.md`, `AGENTS.md`, and `GEMINI.md` (T024). Validated 100% test passing (172 tests, 0 regressions) across entire unittest discovery suite (T022, SC-004).
- 015-visual-identity-state: Implemented Phase 5 (User Story 3 - Operator Inspects Loaded Style at Runtime). Standardized logger identity (`clipper.core.style_loader`) and module imports (`clipper.runtime.config`). Ensured structured INFO logs listing all loaded keys and values upon successful `estilo.json` ingestion, and WARNING logs with `style_node:` prefix for absent files, syntax parse failures, non-dict root formats, per-field missing defaults fallback, invalid HEX colors, numeric constraint fallbacks, and non-primitive value reversions. Added dedicated test suite `TestStyleObservabilityLogging` covering T019 and T020 (32 passing tests in `tests/test_style_node.py`, 171 total in discovery suite).


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
