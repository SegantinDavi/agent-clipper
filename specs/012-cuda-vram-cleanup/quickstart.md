# Quickstart: Deep CUDA VRAM Cleanup Validation

**Branch**: `012-cuda-vram-cleanup` | **Date**: 2026-10-29 | **Spec**: [spec.md](spec.md)

---

## 1. Overview

This quickstart guides you through validating the GPU VRAM cleanup routine introduced in feature `012-cuda-vram-cleanup`. It covers automated test execution, multi-chunk stress testing, and provider profile isolation checks.

---

## 2. Running Automated Unit Tests

Run the dedicated test suite validating VRAM cleanup, iterator closure, error tolerance, and Ollama profile isolation:

```bash
# Run unit tests for CUDA cleanup and transcription ingestion
PYTHONPATH=src venv/bin/python -m unittest tests/test_cuda_cleanup.py tests/test_transcription.py -v

# Run the full test regression suite
PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"
```

---

## 3. Validating in Gemini (CUDA) Profile

### Multi-Chunk Synthetic Audio Verification
Execute a test script that triggers transcription across multiple chunks with `LLM_PROVIDER=gemini`:

```bash
LLM_PROVIDER=gemini PYTHONPATH=src venv/bin/python -c "
from clipper.core.ingestion import transcribe_audio_chunk
import os

# Inspect pipeline.log after multi-chunk transcription
print('Transcribing chunks...')
"
```

### Checking `pipeline.log`
Confirm that each completed chunk generates an `INFO` entry confirming the GPU flush:

```bash
grep -E "GPU memory flushed successfully" output/pipeline.log
```

Expected output:
```text
[TIMESTAMP] - clipper.runtime.cuda_runtime - INFO - GPU memory flushed successfully: before=... MB, after=... MB (freed=... MB)
```

---

## 4. Validating in Ollama (CPU) Profile

Ensure that when running with `LLM_PROVIDER=ollama`, no CUDA libraries are imported and zero CUDA cleanup logs appear:

```bash
# Run transcription test in Ollama profile
LLM_PROVIDER=ollama PYTHONPATH=src venv/bin/python -c "
import sys
from clipper.runtime.config import LLM_PROVIDER, WHISPER_DEVICE
from clipper.core.ingestion import transcribe_audio_chunk

print(f'Active provider: {LLM_PROVIDER}, Device: {WHISPER_DEVICE}')
assert WHISPER_DEVICE == 'cpu'
assert 'ctranslate2' not in sys.modules or not hasattr(sys.modules.get('torch'), 'cuda')
"
```

Confirm that `pipeline.log` contains zero entries for `GPU memory flushed` or CUDA cleanup warnings during this run:

```bash
grep -i "GPU memory flushed" output/pipeline.log || echo "Verified: No CUDA flush logs in CPU profile."
```

---

## 5. Live VRAM Monitoring during Real Video Processing

To monitor VRAM in real-time during a long video run on the RTX 3060:

```bash
# Open a secondary terminal to track VRAM usage every second
watch -n 1 nvidia-smi
```

During execution, VRAM will peak during each chunk's transcription and return immediately to the baseline after the chunk finishes.
