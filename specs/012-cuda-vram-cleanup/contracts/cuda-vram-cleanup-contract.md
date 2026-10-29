# Interface Contract: Deep CUDA VRAM Cleanup

**Branch**: `012-cuda-vram-cleanup` | **Date**: 2026-10-29 | **Spec**: [spec.md](../spec.md)

---

## 1. Module: `clipper.runtime.cuda_runtime`

### Contract: `get_gpu_memory_info(device_index: int = 0) -> tuple[float, float, float] | None`

#### Description
Queries current GPU device memory via NVML (`libnvidia-ml.so.1`). Returns memory stats in megabytes (MB) if available, or `None` if NVML is not available, uninitialized, or running in an unprivileged container.

#### Parameters
- `device_index` (`int`, default `0`): The physical GPU device index to inspect.

#### Returns
- `tuple[float, float, float] | None`: `(used_mb, free_mb, total_mb)` if query succeeds; `None` on any failure or error.

#### Preconditions
- None (safe to call in any environment).

#### Postconditions
- NVML resources (if initialized) are cleanly shut down or safely released without side effects.
- Never raises an exception (all errors swallowed internally returning `None`).

---

### Contract: `release_cuda_memory(before_mb: float | None = None) -> None`

#### Description
Executes deep GPU VRAM cleanup and cache eviction following chunk transcription in the Gemini (CUDA) profile.

#### Parameters
- `before_mb` (`float | None`, default `None`): Optional baseline VRAM in MB sampled before model teardown. If `None`, sampled immediately before cache purge.

#### Returns
- `None`.

#### Preconditions
- Should be invoked when `WHISPER_DEVICE == "cuda"` (Gemini profile).
- Must be a no-op if `WHISPER_DEVICE != "cuda"`.

#### Postconditions
1. If `WHISPER_DEVICE != "cuda"`, returns immediately without loading any CUDA libraries.
2. If PyTorch is imported or available, calls `torch.cuda.empty_cache()` and `torch.cuda.ipc_collect()`.
3. Samples VRAM before (using `before_mb` if provided, or querying NVML) and after flushing when NVML is accessible.
4. Emits exactly one `INFO` level log entry to the active logger:
   - When NVML metrics available:
     `"GPU memory flushed successfully: before=%.1f MB, after=%.1f MB (freed=%.1f MB)"`
   - When NVML metrics unavailable:
     `"GPU memory flushed successfully."`
5. Never propagates exceptions. If any step fails, catches the exception and logs:
   `logger.warning("GPU memory cleanup failed: %s", error)`

---

## 2. Module: `clipper.core.ingestion`

### Contract: `transcribe_audio_chunk(audio_path: str) -> dict`

#### Changes in Ingestion Lifecycle
The `finally` block of `transcribe_audio_chunk` guarantees deterministic cleanup according to the following order:

```python
    finally:
        # Step 0: Sample baseline VRAM before model teardown in CUDA profile
        before_mb = None
        if WHISPER_DEVICE == "cuda":
            try:
                gpu_info = get_gpu_memory_info()
                if gpu_info is not None:
                    before_mb = gpu_info[0]
            except Exception:
                pass

        # Step 1: Safely close lazy segment iterator to release model generator references
        if segments is not None:
            try:
                if hasattr(segments, "close"):
                    segments.close()
            except Exception as close_err:
                logger.debug("Iterator close failed: %s", close_err)

        # Step 2: Explicitly unload CTranslate2 model weights if supported
        if model is not None:
            try:
                ct2_model = getattr(model, "model", None)
                if ct2_model is not None and hasattr(ct2_model, "unload_model"):
                    ct2_model.unload_model()
            except Exception as unload_err:
                logger.warning("Failed to unload CTranslate2 model: %s", unload_err)

        # Step 3: Delete references & invoke Python garbage collection
        del segments
        del model
        gc.collect()

        # Step 4: Execute deep CUDA VRAM release only in CUDA/Gemini profile
        if WHISPER_DEVICE == "cuda":
            try:
                release_cuda_memory(before_mb=before_mb)
            except Exception as cleanup_err:
                logger.warning("GPU memory cleanup encountered an error: %s", cleanup_err)
```

---

## 3. Log Output Format Contract

### Success Case (Gemini Profile with NVML available)
```text
2026-10-29 18:30:00,123 - clipper.runtime.cuda_runtime - INFO - GPU memory flushed successfully: before=1366.5 MB, after=1270.5 MB (freed=96.0 MB)
```

### Success Case (Gemini Profile with NVML unavailable)
```text
2026-10-29 18:30:00,123 - clipper.runtime.cuda_runtime - INFO - GPU memory flushed successfully.
```

### Warning Case (Error in cleanup execution)
```text
2026-10-29 18:30:00,123 - clipper.runtime.cuda_runtime - WARNING - GPU memory cleanup failed: <error_details>
```

### Ollama Profile (`LLM_PROVIDER=ollama`)
- Zero log entries relating to CUDA flush, GPU memory, or NVML.
