# Research: Sandbox Memory Management (018)

**Branch**: `018-sandbox-memory-management` | **Date**: 2026-11-02

---

## 1. How should `CODER_SYSTEM_PROMPT` and `CODER_RETRY_PROMPT_TEMPLATE` enforce intermediate-buffer cleanup and keep peak RAM under 2 GB?

**Decision**:
Add a dedicated, non-negotiable architectural rule "6. GERENCIAMENTO ESTREITO DE MEMÓRIA (MÁXIMO 2 GB RAM)" to `CODER_SYSTEM_PROMPT` and a corresponding reinforcement in `CODER_RETRY_PROMPT_TEMPLATE` in `src/clipper/core/prompts.py`.

The prompt instruct the LLM to:
1. Always import the standard `gc` module (`import gc`).
2. Inside every frame-processing loop, iterator, or image filter function (e.g., custom animation overlays, Pillow drawings, or numpy array transformations), explicitly delete intermediate allocations (`del frame_arr`, `del temp_image`) and invoke `gc.collect()` periodically or at loop boundaries.
3. Explicitly close all clips and subclips (`clip.close()`, `subclip.close()`, `final_clip.close()`) immediately after rendering completes, preferably inside a `finally:` block.
4. Keep the subprocess memory footprint strictly under 2 GB at all times regardless of cut length.

In `CODER_RETRY_PROMPT_TEMPLATE`, reiterate the rule so that self-healing regenerations do not discard the buffer cleanup and `gc.collect()` calls.

**Rationale**:
- **MoviePy & NumPy Memory Retention**: In MoviePy 1.0.3, processing long cuts (e.g. 60–80 seconds or preview chains) with per-frame transformations easily leaks memory if frame arrays or PIL images remain referenced in closures or local scope. Explicit dereferencing (`del`) and `gc.collect()` ensures the C-level memory allocations in NumPy and Pillow are promptly reclaimed.
- **Compliance with FR-001, FR-002, FR-007**: Direct instruction in both initial and retry prompts ensures compliance across the entire lifecycle of script generation.
- **AST Testability**: Static inspection (via Python's `ast` module or regex code analysis in tests) can readily verify the presence of `gc.collect()`, `del`, and `.close()` in generated scripts (SC-001).

**Alternatives considered**:
- *Monkey-patching MoviePy internals*: Rejected — fragile, risks regressions across MoviePy 1.0.3, and does not address LLM-generated code structure.
- *Relying only on OS subprocess termination*: Rejected — while child process termination frees memory at the end, during a 10-minute or heavy-effect render the process would exceed 2 GB and be killed by the Linux OOM killer before finishing.

---

## 2. How should `execution_node` guarantee `release_cuda_memory()` execution across all execution paths?

**Decision**:
Wrap the subprocess execution and result formatting inside a `try...finally` block within `execution_node` in `src/clipper/core/orchestrator.py`:

```python
cut_id = approved_ids[current_cut_index] if approved_ids and current_cut_index < len(approved_ids) else None

try:
    # Run subprocess with timeout protection
    ...
finally:
    try:
        release_cuda_memory(cut_id=cut_id)
    except Exception as cleanup_err:
        logger.warning("VRAM release failed in execution_node for cut %s: %s", cut_id, cleanup_err)
```

**Rationale**:
- **Guaranteed Execution (FR-003, FR-004)**: In Python, the `finally:` block is guaranteed to execute whether the `try:` block completes normally (return code 0), completes with a non-zero exit code, raises `subprocess.TimeoutExpired`, or raises any unexpected system error.
- **Fail-Safe Logging**: Wrapping the call itself with `try/except` ensures that even if NVML or CUDA encounters an unexpected error, `execution_node` still returns its state dictionary without disrupting orchestrator execution.

**Alternatives considered**:
- *Placing cleanup calls separately in each error branch*: Rejected — violates DRY and risks future omissions when new branches or error types are added.
- *Handling VRAM cleanup in a separate LangGraph node*: Rejected — adds unnecessary graph overhead and state transitions; the flush belongs to the post-execution lifecycle of `execution_node`.

---

## 3. How should `release_cuda_memory()` record the cut identifier and memory readings in `pipeline.log`?

**Decision**:
Extend `release_cuda_memory` in `src/clipper/runtime/cuda_runtime.py` to accept an optional `cut_id: int | str | None = None` keyword argument:

```python
def release_cuda_memory(before_mb: float | None = None, cut_id: int | str | None = None) -> None:
    if WHISPER_DEVICE != "cuda":
        return
    ...
    cut_label = f" [cut={cut_id}]" if cut_id is not None else ""
    if before_mb is not None and after_info is not None:
        after_mb = after_info[0]
        freed_mb = max(0.0, before_mb - after_mb)
        logger.info(
            "GPU memory flushed successfully%s: before=%.1f MB, after=%.1f MB (freed=%.1f MB)",
            cut_label,
            before_mb,
            after_mb,
            freed_mb,
        )
    else:
        logger.info("GPU memory flushed successfully%s.", cut_label)
```

**Rationale**:
- **Full Compliance with FR-005 & SC-003**: The root logger in `orchestrator.py` formats logs as `%(asctime)s - %(name)s - %(levelname)s - %(message)s` to `LOG_FILE` (`pipeline.log`). Including `cut_id` produces log lines containing timestamp, cut ID, before MB, after MB, and freed MB.
- **Zero Regressions & Backward Compatibility**: Existing callers (`ingestion.py` for Whisper chunking and tests) pass `before_mb` or no arguments. Adding `cut_id` as an optional keyword argument preserves 100% compatibility with all 234 existing tests.

**Alternatives considered**:
- *Logging cut ID separately in `execution_node`*: Rejected — produces decoupled log entries instead of a single cohesive audit log line.
- *Changing positional arguments*: Rejected — breaks existing code that passes `before_mb` as a positional argument.

---

## 4. How does the CPU-only profile (Ollama local) behave?

**Decision**:
`release_cuda_memory()` starts with `if WHISPER_DEVICE != "cuda": return`. In the Ollama local profile, `WHISPER_DEVICE` is `"cpu"`. The function returns immediately with zero operations, zero CUDA calls, and no exceptions.

**Rationale**:
- **Strict Compliance with FR-006 & AGENTS.md Rule 1**: "em modo local, não inicialize nem valide CUDA". Returning immediately guarantees that CUDA libraries and NVML are never accessed in local CPU mode.
- **Safe Execution**: `execution_node` can call `release_cuda_memory(cut_id=cut_id)` unconditionally without needing provider conditionals in the orchestrator.

**Alternatives considered**:
- *Checking provider in `execution_node` before calling*: Redundant since `release_cuda_memory` already encapsulates this check. However, calling `release_cuda_memory` directly adheres to encapsulation.

---

## 5. How should peak RAM (< 2 GB) be measured and verified in automated tests?

**Decision**:
Use standard Linux kernel instrumentation via Python standard library:
1. `resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss`: Returns the maximum resident set size (RSS) in kilobytes of all terminated child processes.
2. Direct reading of `/proc/{pid}/status` (`VmHWM` / `VmRSS`) during subprocess execution if live sampling is desired.

For testing:
- Construct a synthetic long cut or simulated rendering loop with MoviePy / Pillow.
- Execute via subprocess and assert that peak RSS stays strictly below 2,097,152 KB (2 GB), satisfying SC-002.

**Rationale**:
- **Zero New Dependencies**: `resource` is built into the Python standard library on Linux, and `/proc` is native to Linux/WSL2.
- **Deterministic**: Provides accurate memory figures without third-party libraries like `psutil`.

**Alternatives considered**:
- *Adding `psutil`*: Rejected — violates Constitution gate of zero new dependencies.
- *Downloading a 10-minute YouTube video during tests*: Rejected — slow, brittle, network-dependent, and inappropriate for CI/unit tests.
