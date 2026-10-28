# agent-clipper Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-10-28

## Active Technologies

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

# Run review & HITL crash recovery tests
PYTHONPATH=src venv/bin/python -m unittest tests/test_review.py

# Run pipeline execution
bash run_pipeline.sh
```

## Code Style

Python 3.12+ (tested on Python 3.12 - 3.14): Follow standard conventions

## Recent Changes

- 010-manual-review-langgraph-integration: Added Python 3.12+ (tested on Python 3.12 - 3.14) + `langgraph>=0.2.0`, `instructor`, `pydantic`, `moviepy==1.0.3`, `faster-whisper`, `yt-dlp`, `ctranslate2`, `onnxruntime`, `av<19`

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
