# Phase 0 Research: Deep CUDA VRAM Cleanup in Gemini Profile

**Branch**: `012-cuda-vram-cleanup` | **Date**: 2026-10-29 | **Spec**: [spec.md](spec.md)

---

## 1. Context & Problem Statement

In the Gemini API profile (`LLM_PROVIDER=gemini`), Whisper transcription runs locally on GPU (`WHISPER_DEVICE=cuda`, `WHISPER_COMPUTE_TYPE=float16`) on an NVIDIA GeForce RTX 3060 (12 GB VRAM) within a WSL2 / Docker environment constrained to 8 GB system RAM.

During long video processing (≥15 minutes up to 90+ minutes), videos are split into consecutive audio chunks (via FFmpeg silence detection in `node_0.py`). Each chunk is sequentially transcribed by `transcribe_audio_chunk` in `src/clipper/core/ingestion.py`.

Without explicit GPU memory unloading, dangling references or caching allocators can lead to cumulative VRAM retention, ultimately triggering CUDA Out-Of-Memory (`CUDA error: out of memory`) during extended multi-chunk runs.

This research establishes the architecture and primitives to guarantee deterministic VRAM cleanup between chunks while satisfying all constraints of `AGENTS.md`.

---

## 2. Research Decisions & Analysis

### Topic 1: Primary GPU Memory Release Mechanism

- **Question**: How should GPU memory allocated during transcription be completely released back to the device between chunks?
- **Decision**: Multi-tiered deterministic cleanup:
  1. Explicitly unload the underlying CTranslate2 model via `ct2_model.unload_model()` before deleting references.
  2. Explicitly close and dereference the lazy `segments` generator.
  3. Delete references (`del segments`, `del model`) and force synchronous Python garbage collection (`gc.collect()`).
  4. If PyTorch is installed and CUDA is available, invoke `torch.cuda.empty_cache()` and `torch.cuda.ipc_collect()` to reclaim cached allocator blocks.
- **Rationale**:
  - `faster_whisper.WhisperModel` wraps a C++ `ctranslate2.models.Whisper` instance. CTranslate2 exposes an explicit `unload_model(to_cpu=False)` method that immediately releases device-allocated model weights.
  - Python's `del` only removes the local variable binding; if any cyclic reference or internal handle exists, memory remains pinned until cyclic GC. Calling `unload_model()` + `gc.collect()` eliminates both C++ device allocations and Python wrapper references.
  - While `torch` is not currently in `requirements-cuda.txt`, some runtime environments or extensions may load PyTorch. Probing `sys.modules` or attempting a lazy import of `torch` ensures any CUDA caching allocator is flushed without adding a hard dependency.
- **Alternatives Considered**:
  - *Calling `ctypes.CDLL('libcuda.so.1').cuDevicePrimaryCtxReset()`*: Destroys the primary CUDA context. However, re-initializing the CUDA context on every chunk takes ~300-500ms and breaks shared driver states or subsequent inference libraries.
  - *Relying solely on `del model; gc.collect()`*: Proven insufficient on some PyTorch / CTranslate2 builds where memory pooling retains blocks in GPU memory across iterations.
  - *Running each chunk transcription in a separate OS subprocess*: Guarantees total OS-level VRAM reclamation upon process exit, but adds process spawning overhead, requires IPC serialization for word timestamps, and contradicts the existing clean DAG architecture.

---

### Topic 2: Lazy Generator Lifecycle & Reference Leak Prevention

- **Question**: Does the `segments` iterator returned by `model.transcribe()` hold a reference to `WhisperModel` that prevents GPU memory release if interrupted or partially consumed?
- **Decision**:
  - Wrap generator consumption defensively.
  - In `finally`: explicitly check `if hasattr(segments, "close"): segments.close()` before deleting `segments`.
  - Guard against non-generator iterables (such as lists or mocks in unit tests) so `AttributeError` is never raised.
- **Rationale**:
  - `model.transcribe()` returns a Python generator (`generate_segments`). A generator frame retains references to `self` (the `WhisperModel` instance) and all local evaluation buffers until the generator is either exhausted (`StopIteration`) or explicitly closed (`generator.close()`).
  - If decoding fails midway (e.g. invalid audio packet, corrupt frame, or decoding timeout), the generator is left open. Calling `segments.close()` forces the generator frame to exit immediately and release all bound references.
- **Alternatives Considered**:
  - *Consuming all remaining items into a dummy list (`list(segments)`) on failure*: Bad approach because if decoding failed due to corrupt frames, attempting further iteration raises repeated exceptions and wastes CPU/GPU cycles.
  - *No explicit close*: Leads to dangling references until arbitrary future GC cycles.

---

### Topic 3: Strict Provider Profile Isolation

- **Question**: How to ensure that when `LLM_PROVIDER=ollama` (CPU profile), zero CUDA libraries or cleanup calls are executed?
- **Decision**:
  - Guard the GPU cleanup routine execution strictly with `if WHISPER_DEVICE == "cuda":` (which is derived from `LLM_PROVIDER == "gemini"` in `config.py`).
  - Keep `release_cuda_memory()` in `src/clipper/runtime/cuda_runtime.py`, with top-level guards returning immediately if `WHISPER_DEVICE != "cuda"`.
  - Do not import `ctranslate2`, `torch`, or CUDA shared libraries when running in CPU mode.
- **Rationale**:
  - Rule 1 of `AGENTS.md` strictly mandates: "No modo local, não inicialize nem valide CUDA. No modo API, use o bootstrap de `src/clipper/runtime/cuda_runtime.py`".
  - FR-002 and US-3 explicitly require that running with `LLM_PROVIDER=ollama` on a CPU-only machine produces zero CUDA-related warnings or exceptions.
- **Alternatives Considered**:
  - *Always running cleanup and catching CUDA errors*: Violates Rule 1 and would trigger warnings or errors on machines without CUDA drivers.

---

### Topic 4: Observability & VRAM Tracking Without Heavy Telemetry

- **Question**: How can the operator confirm VRAM release in `pipeline.log` without introducing external profilers or heavy dependencies?
- **Decision**:
  - Implement a lightweight VRAM query function using direct `ctypes` bindings to standard NVIDIA NVML (`libnvidia-ml.so.1`).
  - If NVML is available and returns valid metrics: log before/after VRAM values and delta at `INFO` level:
    `"GPU memory flushed successfully: before=%.1f MB, after=%.1f MB (freed=%.1f MB)"`.
  - If NVML is unavailable (e.g. CPU environment, mock test, or unprivileged container): log confirmation at `INFO` level:
    `"GPU memory flushed successfully."`.
  - Strict zero external telemetry: no Langfuse, Arize Phoenix, or external collectors per Rule 9.
- **Rationale**:
  - `libnvidia-ml.so.1` is part of the standard NVIDIA display driver installation on Linux/WSL2. Calling `nvmlDeviceGetMemoryInfo` via `ctypes` takes <0.1ms and incurs zero heap or daemon overhead.
  - Fully fulfills FR-004 and US-2.
- **Alternatives Considered**:
  - *Calling `nvidia-smi` via `subprocess.run`*: Spawns a shell process, parsing stdout string is brittle, adds ~50ms latency per chunk.
  - *Installing `pynvml` or `gputil`*: Introduces new package dependencies, which is discouraged by FR-006.

---

### Topic 5: Error Isolation and Resilience

- **Question**: What happens if the GPU cleanup routine itself raises an unexpected exception?
- **Decision**:
  - The cleanup routine must be wrapped in a comprehensive `try...except Exception as err:` block.
  - Any error must be logged at `WARNING` level (`logger.warning("GPU cleanup failed: %s", err)`).
  - The exception MUST NOT be re-raised or propagate into the caller. The pipeline MUST continue to the next chunk without interruption (FR-005).
- **Rationale**:
  - Memory cleanup is a preventive optimization; failure to flush cache should never crash an otherwise successful transcription pipeline.
- **Alternatives Considered**:
  - *Re-raising exceptions*: Causes unnecessary job failure for non-fatal runtime warnings.

---

## 3. Technology Stack Summary

| Component | Choice | Reason |
|---|---|---|
| **Model Unloader** | `ctranslate2.models.Whisper.unload_model` | Directly unloads model weights from CUDA memory |
| **Iterator Guard** | `hasattr(segments, "close") and segments.close()` | Frees generator frame and references immediately |
| **Cache Purger** | `torch.cuda.empty_cache()` (lazy / optional) | Purges PyTorch caching allocator if torch is active |
| **VRAM Query** | `libnvidia-ml.so.1` via `ctypes` | Ultra-fast (<0.1ms), native, zero third-party packages |
| **Observability** | Standard Python `logging` to `pipeline.log` | Rule 9 compliance (no external telemetry) |
