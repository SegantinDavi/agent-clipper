# Implementation Plan: Dynamic Scene Scripting via Constrained Decoding

**Branch**: `016-dynamic-scene-scripting` | **Date**: 2026-10-31 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/016-dynamic-scene-scripting/spec.md`

## Summary

Expand the Pydantic schema `CorteVideo` with a `scenes: list[Scene]` field and refactor the Extractor node prompts (`EXTRACTOR_SYSTEM_PROMPT_TEMPLATE`, `EXTRACTOR_FEW_SHOT_EXAMPLES`) so that every validated cut candidate is segmented into sequential 2–4 second scenes with contextual visual metaphors and dynamic animation triggers. 

The feature strictly utilizes Constrained Decoding (`instructor` + Pydantic JSON Schema) without any regex or manual JSON parsing, preserves single-model cognitive routing across both Ollama and Gemini backends, maintains strict synchronous LangGraph execution, and persists scenes seamlessly across SQLite checkpoints and HITL human review manifests (`review.json`).

## Technical Context

**Language/Version**: Python 3.12+ (tested on Python 3.12 – 3.14)  
**Primary Dependencies**: `pydantic` (already in stack), `instructor` (already in stack), `openai` (already in stack), `langgraph` (already in stack)  
**Storage**: SQLite via `SqliteSaver` (`/app/output/estado.db`), `review.json` in `/app/output/reviews/<id>/`  
**Testing**: `unittest` (project standard, `PYTHONPATH=src`)  
**Target Platform**: Linux (Debian-slim Docker on WSL2 Ubuntu)  
**Project Type**: Single project (`src/clipper/`)  
**Performance Goals**: Extractor node mock execution overhead strictly under 50ms wall-clock (SC-003); minimal extra tokens per cut  
**Constraints**: 8 GB RAM / WSL2; zero new dependencies; strict synchronous node contracts (`def`); no regex / manual json.loads for LLM output (AGENTS.md Rule 5); fail-fast on empty scenes (FR-009); transparent SQLite serialization  
**Scale/Scope**: Typically 1–10 cuts per podcast episode, each subdivided into 5–25 scenes of 2–4 seconds

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
|---|---|---|
| No new heavy dependencies | ✅ PASS | Only existing `pydantic`, `instructor`, `openai`, `langgraph` |
| Memory budget respected | ✅ PASS | Pure data modeling & prompt engineering; zero VRAM/RAM overhead |
| Constrained Decoding only | ✅ PASS | Strictly `instructor` + Pydantic JSON Schema; no regex or `json.loads` |
| Single-Model cognitive routing | ✅ PASS | Same model (Qwen2.5 or Gemini) across Thinker and Extractor nodes |
| Strict synchronous node contract | ✅ PASS | All nodes remain `def`, `create_llm_client()` returns `openai.OpenAI`, connections closed in `finally` |
| State serialization in SQLite | ✅ PASS | `scenes` is a list of plain dicts of string primitives; natively JSON-safe in `SqliteSaver` |
| Fail-fast validation | ✅ PASS | Empty scenes list rejected via Pydantic `min_length=1` and explicit `ValueError` guard |
| No external telemetry | ✅ PASS | Observability via standard logging in `pipeline.log` |
| Zero regressions | ✅ PASS | Preserves backward-compatible instantiation for existing 172 unit/contract tests |

**Post-design re-check**: No violations. The design adheres strictly to all AGENTS.md rules and architectural constraints.

## Project Structure

### Documentation (this feature)

```text
specs/016-dynamic-scene-scripting/
├── plan.md              ← this file (/speckit.plan command output)
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/
│   └── corte_video_schema.json   ← Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (affected files)

```text
src/clipper/
├── core/
│   ├── schemas.py       ← define Scene(BaseModel), add scenes to CorteVideo
│   ├── prompts.py       ← update EXTRACTOR_SYSTEM_PROMPT_TEMPLATE & few-shot assistant messages
│   └── orchestrator.py  ← harden extractor_node: fail-fast on empty scenes & duration warning
└── review/
    └── review.py        ← render scene breakdown in review HTML page; review.json serialization

tests/
├── test_scene_scripting.py            ← NEW: comprehensive unit, contract, and persistence tests
├── test_instructor_sync_contract.py   ← contract validation for mock instructor payload with scenes
└── test_review.py                     ← verify review page HTML formatting with scenes
```

**Structure Decision**: Single project layout (`src/clipper/`). No new module or service boundaries needed; modifications enhance existing core schemas, prompts, orchestrator, and review presentation.

## Complexity Tracking

> No Constitution Check violations.
