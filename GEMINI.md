# agent-clipper Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-10-28

## Active Technologies
- SQLite (`SqliteSaver` checkpointer in `/app/output/estado.db`), `pipeline.log` in `/app/output/` (011-checkpoint-thread-id-hardening)
- Python 3.12+ (tested on Python 3.12 - 3.14) + `ctranslate2==4.8.3`, `faster-whisper==1.2.1`, `nvidia-cublas-cu12`, `nvidia-cudnn-cu12` (from `requirements-cuda.txt`), `torch` (optional fallback if present) (012-cuda-vram-cleanup)
- File logging in `/app/output/pipeline.log` (012-cuda-vram-cleanup)
- Python 3.12+ + faster-whisper, langgraph, moviepy==1.0.3, pydantic, instructor (013-chunk-timestamp-sync)
- SQLite (`/app/output/estado.db` via `SqliteSaver`), arquivos WAV de chunk em `/app/output/` (013-chunk-timestamp-sync)

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

# Run pipeline execution
bash run_pipeline.sh
```

## Code Style

Python 3.12+ (tested on Python 3.12 - 3.14): Follow standard conventions

## Recent Changes
- 013-chunk-timestamp-sync: Implemented absolute timeline timestamp synchronization for multi-chunk video transcription. Extracted pure function `apply_chunk_offset()` in `src/clipper/core/ingestion.py` with 2-decimal rounding, immutability, and structured INFO logging. Refactored `transcription_node` in `src/clipper/core/orchestrator.py` with fail-fast validation (`ValueError` on non-dict, missing/negative offset, or missing `chunk_path`). Validated downstream integration with `speech_intervals`, `build_pause_plan`, `.pauses.json` persistence, and caption grouping continuity across chunk transitions with drift <= 0.1s. Added comprehensive test suite in `tests/test_chunk_timestamp_sync.py`.
- 012-cuda-vram-cleanup: Implemented deterministic deep CUDA VRAM cleanup and native NVML observability for multi-chunk transcription in the Gemini profile (`WHISPER_DEVICE=cuda`): added `get_gpu_memory_info` and `release_cuda_memory` in `src/clipper/runtime/cuda_runtime.py` with PyTorch cache flushing and structured INFO/WARNING logging, refactored `transcribe_audio_chunk` `finally` block in `src/clipper/core/ingestion.py` to safely close lazy segment generators and unload CTranslate2 model weights, guaranteed complete CPU isolation in Ollama profile (`WHISPER_DEVICE=cpu`), and added comprehensive test suite in `tests/test_cuda_cleanup.py`.
- 011-checkpoint-thread-id-hardening: Hardened checkpointer thread_id derivation to deterministic 16-character hexadecimal SHA-256 hash (`video_id|provider|model|endpoint|silence_enabled|silence_min_pause`) ensuring clean context isolation across provider/model/endpoint/silence changes, added `extract_video_id` helper in `src/clipper/core/ingestion.py`, and integrated structured INFO startup logging in `orchestrator.py:main`. Added dedicated test suite in `tests/test_checkpoint_thread_id.py`.


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
