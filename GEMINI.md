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
- Python 3.12+ (tested on Python 3.12 – 3.14) + `pydantic` (already in stack), `langgraph` (already in stack), `moviepy==1.0.3` (already in stack), Python standard library (`html`, `logging`, `pathlib`, `json`) (019-hitl-review-delivery)
- SQLite via `SqliteSaver` (`/app/output/estado.db`), `decision.json` in `/app/output/reviews/<id>/`, logs in `/app/output/pipeline.log` (019-hitl-review-delivery)

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

# Run review delivery and selective gating tests
PYTHONPATH=src venv/bin/python -m unittest tests/test_review_delivery.py

# Run dynamic scene scripting tests
PYTHONPATH=src venv/bin/python -m unittest tests/test_scene_scripting.py

# Run pipeline execution
bash run_pipeline.sh
```

## Code Style

Python 3.12+ (tested on Python 3.12 - 3.14): Follow standard conventions

## Recent Changes
- 019-hitl-review-delivery: Completed all phases (Phases 1-5). Implemented HITL review delivery showing planned scene scripts (`Scene`), metaphors, triggers, with explicit fallbacks ("No scene script available") and em-dash placeholders ("—") alongside responsive mobile layout down to 320px in `render_review_page`. Implemented bidirectional schema synchronization for `approved_ids` and `approved_cut_ids`, fail-fast `decision.json` gating in `coder_node`, selective cut rendering ensuring 0% subprocesses for unapproved cuts with INFO audit logs, and conditional edge routing `route_approval_outcome` terminating empty selections directly at `END` in < 5 seconds. Full regression suite passing with 0 regressions across 285 tests (SC-004), quickstart scenarios verified, and documentation synchronized across README.md, AGENTS.md, and GEMINI.md.
- 018-sandbox-memory-management: Completed all phases (Phases 1-5). Implemented sandboxing memory management ensuring generated render scripts include explicit intermediate-buffer cleanup (del, gc.collect(), clip.close()) maintaining peak subprocess RSS < 2 GB (SC-002), and guaranteed post-subprocess VRAM reclamation in execution_node finally block calling release_cuda_memory(cut_id=cut_id) across success, failure, timeout, and exceptions with structured pipeline.log metrics (SC-003, SC-005) and silent CPU profile no-op. Full test suite passing with 0 regressions across 256 tests (SC-004), and synchronized documentation across README.md, AGENTS.md, and GEMINI.md.


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
