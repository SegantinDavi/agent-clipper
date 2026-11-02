# Implementation Plan: Sandbox Memory Management

**Branch**: `018-sandbox-memory-management` | **Date**: 2026-11-02 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/018-sandbox-memory-management/spec.md`

## Summary

Implement **Phase 4: Sandboxing and Strict Memory Management** for the agent-clipper pipeline.

This feature establishes dual memory protection for rendering and execution on resource-constrained hardware (WSL2 8 GB RAM / RTX 3060 12 GB VRAM):
1. **Host RAM Protection (< 2 GB Peak RSS)**: Updates `CODER_SYSTEM_PROMPT` and `CODER_RETRY_PROMPT_TEMPLATE` in `src/clipper/core/prompts.py` with mandatory architectural directives instructing the LLM to insert explicit intermediate-buffer cleanup constructs (`del` of numpy arrays, frame objects, temporary Pillow buffers; importing `gc` and calling `gc.collect()` periodically; closing all MoviePy clips via `.close()`) into every frame-processing loop of generated render scripts, keeping peak RAM below 2 GB.
2. **Guaranteed Post-Subprocess VRAM Flush**: Wraps subprocess execution in `execution_node` (`src/clipper/core/orchestrator.py`) with a guaranteed `finally:` block that unconditionally calls `release_cuda_memory(cut_id=cut_id)` (`src/clipper/runtime/cuda_runtime.py`) after every subprocess run (success, non-zero exit code, or timeout).
3. **Structured Audit Logging**: Enhances `release_cuda_memory()` to record the cut identifier alongside before/after/freed megabytes in `pipeline.log`, maintaining zero-error silent execution when running in CPU-only (Ollama local) profile.

## Technical Context

**Language/Version**: Python 3.12+ (tested on Python 3.12 – 3.14)  
**Primary Dependencies**: `moviepy==1.0.3` (already in stack), `pydantic` (already in stack), `instructor` (already in stack), `langgraph` (already in stack), Python standard library (`gc`, `resource`, `ast`, `subprocess`)  
**Storage**: SQLite via `SqliteSaver` (`/app/output/estado.db`), log entries in `/app/output/pipeline.log`  
**Testing**: `unittest` (standard project test harness, `PYTHONPATH=src`)  
**Target Platform**: Linux (Debian-slim Docker on WSL2 Ubuntu, 8 GB RAM / 8 GB Swap)  
**Project Type**: Single project (`src/clipper/`)  
**Performance Goals**: Peak subprocess RAM usage strictly below 2 GB throughout render execution (SC-002); post-execution VRAM flush overhead strictly under 50ms wall-clock  
**Constraints**: 8 GB RAM / WSL2; zero new dependencies; strict synchronous node contracts (`def`); no regex / manual json.loads for LLM output (AGENTS.md Rule 5); unconditional VRAM reclamation in `finally:` block; safe silent execution in CPU mode; backward compatibility with existing callers  
**Scale/Scope**: Typically 1–10 approved cuts per podcast episode, each rendered via an isolated Python subprocess

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
|---|---|---|
| No new heavy dependencies | ✅ PASS | Zero new dependencies. Uses Python standard library (`gc`, `resource`, `ast`) and existing project stack. |
| Memory budget respected | ✅ PASS | Peak subprocess RAM capped strictly under 2 GB; frame arrays dereferenced; `release_cuda_memory` flushes VRAM after every subprocess. |
| Constrained Decoding only | ✅ PASS | Prompt enhancements guide code generation via existing Instructor + Pydantic `RenderScriptPayload` schema. No regex or manual `json.loads`. |
| Single-Model cognitive routing | ✅ PASS | Same model reused via `create_llm_client()`; no second LLM loaded. |
| Strict synchronous node contract | ✅ PASS | `execution_node` remains a synchronous function (`def`); connections and resources deterministically closed. |
| State serialization in SQLite | ✅ PASS | No state schema changes needed; existing `VideoState` fields serialize transparently in `SqliteSaver`. |
| Subprocess isolation & Timeout | ✅ PASS | Isolated subprocess with timeout preserved; guaranteed `finally:` block ensures VRAM is flushed even on timeout or error. |
| Safe CPU/Ollama fallback | ✅ PASS | In Ollama CPU profile (`WHISPER_DEVICE != "cuda"`), `release_cuda_memory()` returns immediately with zero operations and no errors. |
| No external telemetry | ✅ PASS | Observability via standard logging in `pipeline.log`. |
| Zero regressions | ✅ PASS | 100% backward-compatible function signatures preserving all 234 existing tests. |

**Post-design re-check**: No violations. The design adheres strictly to all AGENTS.md rules and architectural constraints.

## Project Structure

### Documentation (this feature)

```text
specs/018-sandbox-memory-management/
├── plan.md              ← this file (/speckit.plan command output)
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── checklists/
│   └── requirements.md  ← specification checklist
├── contracts/
│   ├── coder_prompt_memory_contract.md   ← Phase 1 output (Prompt directives and AST validation)
│   └── execution_node_vram_contract.md   ← Phase 1 output (Guaranteed VRAM release & audit log format)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (affected files)

```text
src/clipper/
├── core/
│   ├── prompts.py       ← add Rule 6 (buffer cleanup, gc.collect(), 2 GB RAM limit) to CODER_SYSTEM_PROMPT & CODER_RETRY_PROMPT_TEMPLATE
│   └── orchestrator.py  ← add guaranteed finally: block in execution_node invoking release_cuda_memory(cut_id=cut_id)
└── runtime/
    └── cuda_runtime.py  ← extend release_cuda_memory() with optional cut_id and enhanced log message

tests/
├── test_sandbox_memory.py  ← NEW: unit and integration tests for prompt rules, AST verification, guaranteed VRAM flush, CPU safety, and peak RAM ceiling
├── test_coder_dag.py       ← verify compatibility with existing coder DAG tests
└── test_cuda_cleanup.py    ← verify compatibility with existing CUDA cleanup tests
```

**Structure Decision**: Single project layout (`src/clipper/`). No new packages or external services required. Changes integrate directly into `src/clipper/core/prompts.py`, `src/clipper/core/orchestrator.py`, and `src/clipper/runtime/cuda_runtime.py`, with dedicated tests in `tests/test_sandbox_memory.py`.

## Complexity Tracking

> No Constitution Check violations.
