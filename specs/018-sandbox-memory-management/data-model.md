# Data Model: Sandbox Memory Management (018)

**Branch**: `018-sandbox-memory-management` | **Date**: 2026-11-02

---

## 1. Constants & Prompts (`clipper.core.prompts`)

### 1.1 `CODER_SYSTEM_PROMPT` (Updated String Constant)

The prompt supplied as the system prompt to the LLM in `coder_node`. Extended with explicit instructions for intermediate-buffer cleanup and memory limits.

| Field / Directive | Type | Purpose |
|---|---|---|
| Rule 6: Gerenciamento Estrito de Memória | String directive | Mandates `import gc`, per-frame intermediate buffer deallocation (`del frame_arr`), periodic `gc.collect()`, clip closing (`clip.close()`), and a strict peak RAM ceiling of 2 GB. |

### 1.2 `CODER_RETRY_PROMPT_TEMPLATE` (Updated String Constant)

Template formatted when `render_attempts > 0` and `render_error` contains traceback diagnostics. Extended with memory management persistence instructions.

| Parameter | Type | Description |
|---|---|---|
| `attempt` | `int` | Current retry attempt index |
| `error_diagnostic` | `str` | Truncated stderr (last 2000 chars) |
| `previous_script` | `str` | Previous script code |
| `cut_metadata` | `str` | Formatted metadata for the cut |
| *Rule reinforcement* | Static text | Instructs the LLM to retain intermediate buffer cleanup, `import gc`, `gc.collect()`, and clip closures during error correction. |

---

## 2. Runtime Functions (`clipper.runtime.cuda_runtime`)

### 2.1 `release_cuda_memory` (Extended Function Signature)

Reclaims CUDA VRAM and records audit metrics in `pipeline.log`.

```python
def release_cuda_memory(
    before_mb: float | None = None,
    cut_id: int | str | None = None,
) -> None:
    ...
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `before_mb` | `float \| None` | `None` | Initial VRAM usage in MB before reclamation. If `None`, queried via `get_gpu_memory_info()`. |
| `cut_id` | `int \| str \| None` | `None` | Optional identifier of the video cut being processed by the render subprocess. |

**Output Log Line Contract (`pipeline.log`)**:
- With `cut_id` and NVML available:
  `"%(asctime)s - clipper.runtime.cuda_runtime - INFO - GPU memory flushed successfully [cut={cut_id}]: before={before_mb:.1f} MB, after={after_mb:.1f} MB (freed={freed_mb:.1f} MB)"`
- Without `cut_id` (backward compatibility):
  `"%(asctime)s - clipper.runtime.cuda_runtime - INFO - GPU memory flushed successfully: before={before_mb:.1f} MB, after={after_mb:.1f} MB (freed={freed_mb:.1f} MB)"`
- With CPU profile (`WHISPER_DEVICE != "cuda"`):
  Immediate silent return (`None`), no CUDA or NVML calls.

---

## 3. Orchestration Nodes (`clipper.core.orchestrator`)

### 3.1 `execution_node` (Lifecycle & Cleanup Invariant)

```python
def execution_node(state: VideoState) -> dict:
    ...
```

| Lifecycle Stage | Event | Action |
|---|---|---|
| **Pre-execution** | Setup | Increment `render_attempts`, identify `cut_id` from `approved_cut_ids[current_cut_index]`. |
| **Execution** | Subprocess invocation | Run `render_script.py` with `RENDER_TIMEOUT_SECONDS` timeout. |
| **Outcomes** | Returncode 0 | Set `render_exit_code = 0`, clear `render_error`. |
| | Returncode != 0 | Set `render_exit_code = code`, set `render_error = stderr`. |
| | TimeoutExpired | Set `render_exit_code = -1`, record timeout message in `render_error`. |
| | Unexpected exception | Set `render_exit_code = -1`, record exception in `render_error`. |
| **Post-execution (guaranteed)** | `finally:` block | Unconditionally execute `release_cuda_memory(cut_id=cut_id)`. |

---

## 4. Subprocess Memory Boundary (Testing & Metrics)

| Metric | Source | Unit | Constraint |
|---|---|---|---|
| Peak Subprocess RAM (`ru_maxrss`) | `resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss` | Kilobytes | `< 2,097,152 KB` (2 GB) |
| Process VmHWM / VmRSS | `/proc/{pid}/status` | Kilobytes | `< 2,097,152 KB` (2 GB) |
