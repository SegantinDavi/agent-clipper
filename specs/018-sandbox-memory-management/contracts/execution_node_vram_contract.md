# Interface Contract: Execution Node VRAM Release & Audit Logging

**Branch**: `018-sandbox-memory-management` | **Date**: 2026-11-02 | **Spec**: [spec.md](../spec.md)

---

## 1. Runtime Contract: `release_cuda_memory`

### Signature
```python
def release_cuda_memory(
    before_mb: float | None = None,
    cut_id: int | str | None = None,
) -> None: ...
```

### Preconditions
1. `before_mb` is either a non-negative float (megabytes) or `None`.
2. `cut_id` is an integer, string, or `None`.

### Postconditions
1. If `WHISPER_DEVICE != "cuda"`:
   - Returns immediately (`None`).
   - Does NOT initialize or access `torch.cuda` or NVML libraries.
   - Raises zero exceptions.
2. If `WHISPER_DEVICE == "cuda"`:
   - If `torch` is loaded, executes `torch.cuda.empty_cache()` and `torch.cuda.ipc_collect()` if available.
   - Emits an `INFO` level log entry to the root logger (writing to `pipeline.log`).
   - If `cut_id` is provided, includes `[cut={cut_id}]` in the log message.
   - If NVML metrics are available, reports `before=... MB`, `after=... MB`, and `freed=... MB`.

---

## 2. Orchestration Contract: `execution_node`

### Preconditions
1. `state` conforms to `VideoState`.
2. `state["current_cut_index"]` points to the active index in `state["approved_cut_ids"]`.

### Postconditions
1. The invocation of `release_cuda_memory(cut_id=cut_id)` MUST occur inside a `finally:` block wrapping the subprocess execution.
2. The VRAM cleanup MUST trigger regardless of whether:
   - Subprocess completes with exit code 0.
   - Subprocess exits with a non-zero exit code.
   - Subprocess exceeds `RENDER_TIMEOUT_SECONDS` (raising `subprocess.TimeoutExpired`).
   - An unexpected `Exception` occurs before or during execution.
3. If `release_cuda_memory` itself raises an exception, it is caught safely and logged as a warning; it does NOT prevent `execution_node` from returning the state update dictionary.
