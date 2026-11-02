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
- Python 3.12+ (tested on Python 3.12 – 3.14) + `pydantic` (already in stack), `instructor` (already in stack), `openai` (already in stack), `langgraph` (already in stack), `moviepy==1.0.3` (already in stack) (017-self-healing-coder-dag)
- SQLite via `SqliteSaver` (`/app/output/estado.db`), script files in `/app/output/<cut_id>/render_script.py` (017-self-healing-coder-dag)
- Python 3.12+ (tested on Python 3.12 – 3.14) + `moviepy==1.0.3` (already in stack), `pydantic` (already in stack), `instructor` (already in stack), `langgraph` (already in stack), Python standard library (`gc`, `resource`, `ast`, `subprocess`) (018-sandbox-memory-management)
- SQLite via `SqliteSaver` (`/app/output/estado.db`), log entries in `/app/output/pipeline.log` (018-sandbox-memory-management)

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

# Run sandbox memory management tests
PYTHONPATH=src venv/bin/python -m unittest tests/test_sandbox_memory.py

# Run dynamic scene scripting tests
PYTHONPATH=src venv/bin/python -m unittest tests/test_scene_scripting.py

# Run pipeline execution
bash run_pipeline.sh
```

## Code Style

Python 3.12+ (tested on Python 3.12 - 3.14): Follow standard conventions

## Recent Changes
- 018-sandbox-memory-management: Completed all phases (Phases 1-5). Implemented sandboxing memory management ensuring generated render scripts include explicit intermediate-buffer cleanup (del, gc.collect(), clip.close()) maintaining peak subprocess RSS < 2 GB (SC-002), and guaranteed post-subprocess VRAM reclamation in execution_node finally block calling release_cuda_memory(cut_id=cut_id) across success, failure, timeout, and exceptions with structured pipeline.log metrics (SC-003, SC-005) and silent CPU profile no-op. Full test suite passing with 0 regressions across 256 tests (SC-004), and synchronized documentation across README.md, AGENTS.md, and GEMINI.md.
- 018-sandbox-memory-management: Added Python 3.12+ (tested on Python 3.12 – 3.14) + `moviepy==1.0.3` (already in stack), `pydantic` (already in stack), `instructor` (already in stack), `langgraph` (already in stack), Python standard library (`gc`, `resource`, `ast`, `subprocess`)
- 017-self-healing-coder-dag: Completed all phases (Phases 1-6). Implemented `coder_node` with Constrained Decoding via Instructor and `RenderScriptPayload` for MoviePy 1.0.3, `execution_node` with isolated subprocess execution and timeout protection, conditional self-healing retry loop (up to 3 attempts with truncated `stderr`), `abort_node` graceful failure handling, and `advance_cut_node` sequential cut iteration. Added AST static analysis scan verifying zero regex/manual json.loads in coder layer (SC-002), benchmark verifying wrapper overhead < 500ms (SC-003), verified 100% test pass rate with 0 regressions across 234 discovery tests (SC-004), and synchronized documentation across `README.md`, `AGENTS.md`, and `GEMINI.md`.
- 017-self-healing-coder-dag: Added Python 3.12+ (tested on Python 3.12 – 3.14) + `pydantic` (already in stack), `instructor` (already in stack), `openai` (already in stack), `langgraph` (already in stack), `moviepy==1.0.3` (already in stack)


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
