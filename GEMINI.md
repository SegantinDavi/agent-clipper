# agent-clipper Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-10-28

## Active Technologies
- SQLite (`SqliteSaver` checkpointer in `/app/output/estado.db`), `pipeline.log` in `/app/output/` (011-checkpoint-thread-id-hardening)
- Python 3.12+ (tested on Python 3.12 - 3.14) + `ctranslate2==4.8.3`, `faster-whisper==1.2.1`, `nvidia-cublas-cu12`, `nvidia-cudnn-cu12` (from `requirements-cuda.txt`), `torch` (optional fallback if present) (012-cuda-vram-cleanup)
- File logging in `/app/output/pipeline.log` (012-cuda-vram-cleanup)

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

# Run checkpoint thread ID isolation tests
PYTHONPATH=src venv/bin/python -m unittest tests/test_checkpoint_thread_id.py

# Run review & HITL crash recovery tests
PYTHONPATH=src venv/bin/python -m unittest tests/test_review.py

# Run pipeline execution
bash run_pipeline.sh
```

## Code Style

Python 3.12+ (tested on Python 3.12 - 3.14): Follow standard conventions

## Recent Changes
- 012-cuda-vram-cleanup: Added Python 3.12+ (tested on Python 3.12 - 3.14) + `ctranslate2==4.8.3`, `faster-whisper==1.2.1`, `nvidia-cublas-cu12`, `nvidia-cudnn-cu12` (from `requirements-cuda.txt`), `torch` (optional fallback if present)
- 011-checkpoint-thread-id-hardening: Hardened checkpointer thread_id derivation to deterministic 16-character hexadecimal SHA-256 hash (`video_id|provider|model|endpoint|silence_enabled|silence_min_pause`) ensuring clean context isolation across provider/model/endpoint/silence changes, added `extract_video_id` helper in `src/clipper/core/ingestion.py`, and integrated structured INFO startup logging in `orchestrator.py:main`. Added dedicated test suite in `tests/test_checkpoint_thread_id.py`.

- 010-manual-review-langgraph-integration: Added Python 3.12+ (tested on Python 3.12 - 3.14) + `langgraph>=0.2.0`, `instructor`, `pydantic`, `moviepy==1.0.3`, `faster-whisper`, `yt-dlp`, `ctranslate2`, `onnxruntime`, `av<19`

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
