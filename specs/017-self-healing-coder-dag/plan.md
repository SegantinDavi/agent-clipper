# Implementation Plan: Self-Healing Coder DAG

**Branch**: `017-self-healing-coder-dag` | **Date**: 2026-10-31 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/017-self-healing-coder-dag/spec.md`

## Summary

Replace the monolithic deterministic `editor_node` with a modular, self-healing code generation and execution architecture in the LangGraph DAG (`coder_node` + `execution_node` + `abort_node`). 

When cuts are approved by human review, `coder_node` calls the configured LLM using Instructor Constrained Decoding to author a self-contained Python render script (`render_script.py`) adhering to MoviePy 1.0.3, Pillow, and Liberation fonts. `execution_node` runs the script in an isolated child subprocess, capturing exit codes and stderr logs. A LangGraph conditional edge implements self-healing by looping back to `coder_node` with stderr diagnostics upon failure (up to 3 attempts), or routing to `abort_node` when retries are exhausted, persisting all state transparently across SQLite checkpoints.

## Technical Context

**Language/Version**: Python 3.12+ (tested on Python 3.12 – 3.14)  
**Primary Dependencies**: `pydantic` (already in stack), `instructor` (already in stack), `openai` (already in stack), `langgraph` (already in stack), `moviepy==1.0.3` (already in stack)  
**Storage**: SQLite via `SqliteSaver` (`/app/output/estado.db`), script files in `/app/output/<cut_id>/render_script.py`  
**Testing**: `unittest` (project standard, `PYTHONPATH=src`)  
**Target Platform**: Linux (Debian-slim Docker on WSL2 Ubuntu)  
**Project Type**: Single project (`src/clipper/`)  
**Performance Goals**: `coder_node` and `execution_node` overhead strictly under 500ms wall-clock (SC-003, excluding LLM API and subprocess rendering time)  
**Constraints**: 8 GB RAM / WSL2; zero new dependencies; strict synchronous node contracts (`def`); no regex / manual json.loads for LLM output (AGENTS.md Rule 5); subprocess execution isolation with timeout protection; maximum 3 self-healing retry attempts; transparent SQLite serialization  
**Scale/Scope**: Typically 1–10 approved cuts per podcast episode, each rendered via a standalone Python script

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
|---|---|---|
| No new heavy dependencies | ✅ PASS | Only existing `pydantic`, `instructor`, `openai`, `langgraph`, and standard library `subprocess` |
| Memory budget respected | ✅ PASS | Isolated child subprocess releases all RAM on completion; zero accumulation in orchestrator |
| Constrained Decoding only | ✅ PASS | Strictly `instructor` + Pydantic `RenderScriptPayload`; no regex or `json.loads` manual stripping |
| Single-Model cognitive routing | ✅ PASS | Same model (Qwen2.5 or Gemini) reused via `create_llm_client()`; no second LLM loaded |
| Strict synchronous node contract | ✅ PASS | `coder_node`, `execution_node`, `abort_node` are all `def`; connections closed in `finally` |
| State serialization in SQLite | ✅ PASS | New `VideoState` fields (`render_script_path`, `render_attempts`, `render_error`, `render_exit_code`, `render_aborted`) are primitive types; natively JSON-safe in `SqliteSaver` |
| Subprocess isolation & Timeout | ✅ PASS | Subprocess runs isolated with configurable `RENDER_TIMEOUT_SECONDS` (default 300s); errors never crash orchestrator |
| Bounded retry loop | ✅ PASS | Strictly bounded to at most 3 execution attempts per cut; routes to `abort_node` on exhaustion |
| Stderr token budget | ✅ PASS | Captured `stderr` truncated to `RENDER_ERROR_MAX_CHARS` (default 2000 chars tail) for LLM retry prompt |
| No external telemetry | ✅ PASS | Observability via standard logging in `pipeline.log` |
| Zero regressions | ✅ PASS | Backward-compatible DAG architecture preserving all 202 existing unit and integration tests |

**Post-design re-check**: No violations. The design adheres strictly to all AGENTS.md rules and architectural constraints.

## Project Structure

### Documentation (this feature)

```text
specs/017-self-healing-coder-dag/
├── plan.md              ← this file (/speckit.plan command output)
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/
│   ├── render_script_schema.json     ← Phase 1 output (JSON Schema for RenderScriptPayload)
│   └── coder_execution_contract.md   ← Phase 1 output (Node and router contract specifications)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (affected files)

```text
src/clipper/
├── core/
│   ├── schemas.py       ← define RenderScriptPayload(BaseModel)
│   ├── prompts.py       ← add CODER_SYSTEM_PROMPT & CODER_RETRY_PROMPT_TEMPLATE
│   └── orchestrator.py  ← add coder_node, execution_node, abort_node, route_execution_outcome, extend VideoState & update DAG in create_graph()

tests/
├── test_coder_dag.py                  ← NEW: comprehensive unit, execution, retry loop, and crash recovery tests
└── test_instructor_sync_contract.py   ← verify synchronous contract of coder_node and execution_node
```

**Structure Decision**: Single project layout (`src/clipper/`). No new packages or external services required. Changes integrate directly into `src/clipper/core/` and tests into `tests/`.

## Complexity Tracking

> No Constitution Check violations.
