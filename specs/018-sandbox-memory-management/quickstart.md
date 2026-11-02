# Quickstart: Feature 018 — Sandbox Memory Management

**Branch**: `018-sandbox-memory-management`

---

## Overview

Feature 018 implements **Phase 4: Sandboxing and Strict Memory Management**. It protects host hardware (WSL2 8 GB RAM / RTX 3060 12 GB VRAM) during code generation and render execution by:
1. **Intermediate-Buffer Release & Peak RAM Ceiling (< 2 GB)**: Injects strict directives into `CODER_SYSTEM_PROMPT` and `CODER_RETRY_PROMPT_TEMPLATE` requiring generated render scripts to import `gc`, delete loop-local frame buffers (`del`), run periodic garbage collection (`gc.collect()`), and close MoviePy clips (`.close()`).
2. **Guaranteed Post-Subprocess VRAM Flush**: Injects a guaranteed `finally:` block in `execution_node` calling `release_cuda_memory(cut_id=cut_id)` after every render subprocess execution (success, failure, or timeout).
3. **Structured Audit Logging**: Emits detailed VRAM flush entries to `pipeline.log` capturing timestamp, cut identifier, and before/after/freed megabytes.

---

## Modified Files

| File | Changes |
|---|---|
| `src/clipper/core/prompts.py` | Add Rule 6 (buffer cleanup, `gc.collect()`, 2 GB limit) to `CODER_SYSTEM_PROMPT` and reinforce in `CODER_RETRY_PROMPT_TEMPLATE` |
| `src/clipper/runtime/cuda_runtime.py` | Update `release_cuda_memory` to accept optional `cut_id` and format log output with cut identifier |
| `src/clipper/core/orchestrator.py` | Call `release_cuda_memory(cut_id=cut_id)` in a guaranteed `finally:` block in `execution_node` |
| `tests/test_sandbox_memory.py` | **New file**: Tests for prompt memory rules, static AST inspection of scripts, VRAM flush invocation across all execution outcomes, CPU mode safety, and peak RAM ceiling (< 2 GB) |

---

## Verification & Testing

### 1. Run Feature-Specific Test Suite

Execute the dedicated sandbox memory management tests:

```bash
PYTHONPATH=src venv/bin/python -m unittest tests/test_sandbox_memory.py
```

### 2. Run Related Coder DAG & CUDA Cleanup Tests

Verify integration with coder DAG and CUDA cleanup modules:

```bash
PYTHONPATH=src venv/bin/python -m unittest tests/test_coder_dag.py tests/test_cuda_cleanup.py
```

### 3. Run Full Discovery Regression Suite

Verify 100% passing status across all existing unit and integration tests (234+ tests, 0 regressions):

```bash
PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"
```

---

## Inspecting Logs & Memory Reclamation

### 1. In `pipeline.log`

Inspect the VRAM flush log entries after a render subprocess completes:

```bash
grep -E "GPU memory flushed successfully" output/pipeline.log
```

Expected format:
```text
2026-11-02 12:00:00,123 - clipper.runtime.cuda_runtime - INFO - GPU memory flushed successfully [cut=1]: before=1240.5 MB, after=890.3 MB (freed=350.2 MB)
```
