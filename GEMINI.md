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
- 015-visual-identity-state: Implemented Phase 4 (User Story 2 - Visual Style Survives Checkpoint Recovery). Added `validate_visual_identity_primitives` in `src/clipper/core/style_loader.py` enforcing JSON-primitive serializability (`str`, `int`, `float`, `bool`) and fallback to defaults with WARNING logging. Declared `style_path` in `VideoState` TypedDict and initialized in `initial_state`, allowing runtime/test path injection across LangGraph state channels. Added integration test suite `TestStyleCheckpointRecovery` and unit tests in `tests/test_style_node.py` asserting `SqliteSaver` checkpoint persistence, state recovery across crashes without disk re-reads, and `--restart` thread purge re-execution (27 passing tests in `test_style_node.py`, 166 total in suite).
- 015-visual-identity-state: Implemented Phase 3 (User Story 1 - Custom Brand Style MVP). Added `visual_identity` field to `VideoState` and `initial_state`, created synchronous `style_node` loading `estilo.json` with per-field fallbacks, wired `style_node` into LangGraph DAG between `fatiamento` and `transcricao`, updated `create_caption_clip`, `position_caption_clip`, `group_caption_words`, and `cut_and_format_video` in `editor.py` to parameterize typography, palette, layout, and motion rules through `visual_identity`, and wired `editor_node` to pass state to video rendering. Added test suite in `tests/test_style_node.py` (24 passing unit/contract/render tests, 163 total in suite).
- 014-align-instructor-nodes: Aligned LangGraph orchestration nodes with synchronous execution and Instructor client. Enforced 100% synchronous signatures (`def`) on all StateGraph registered nodes with fail-fast validation in `create_graph()`, added runtime type guard in `create_llm_client()` asserting `openai.OpenAI` and rejecting `AsyncOpenAI`, wrapped extractor node via synchronous `instructor.from_openai(..., mode=instructor.Mode.JSON_SCHEMA)`, and hardened deterministic connection teardown via `finally: raw_client.close()` in both `thinker_node` and `extractor_node`. Created comprehensive architectural contract test suite in `tests/test_instructor_sync_contract.py`.
- 013-chunk-timestamp-sync: Implemented absolute timeline timestamp synchronization for multi-chunk video transcription. Extracted pure function `apply_chunk_offset()` in `src/clipper/core/ingestion.py` with 2-decimal rounding, immutability, and structured INFO logging. Refactored `transcription_node` in `src/clipper/core/orchestrator.py` with fail-fast validation (`ValueError` on non-dict, missing/negative offset, or missing `chunk_path`). Validated downstream integration with `speech_intervals`, `build_pause_plan`, `.pauses.json` persistence, and caption grouping continuity across chunk transitions with drift <= 0.1s. Added comprehensive test suite in `tests/test_chunk_timestamp_sync.py`.


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
