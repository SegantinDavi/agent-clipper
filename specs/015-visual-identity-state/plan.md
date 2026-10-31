# Implementation Plan: Visual Identity & Global State

**Branch**: `015-visual-identity-state` | **Date**: 2026-10-31 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/015-visual-identity-state/spec.md`

## Summary

Implement a `style_node` synchronous LangGraph node that reads an optional `estilo.json` file from the project root, validates its fields against a Pydantic schema with per-field defaults, writes the result into `VideoState.visual_identity` (a serializable `dict`), and then update all downstream caption-rendering logic in `editor.py` to read style values from state instead of directly from `config.py` module-level constants.

The feature adds zero GPU/inference dependencies — it is a pure I/O operation that runs before `thinker_node`. Crash recovery is guaranteed because `visual_identity` is a plain dict of primitives, which `SqliteSaver` checkpoints natively. All `CAPTION_*` constants in `config.py` are preserved as fallback defaults.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: `pydantic` (already in stack), `langgraph` (already in stack), `moviepy==1.0.3` (already in stack)  
**Storage**: SQLite via `SqliteSaver` (`/app/output/estado.db`) — `visual_identity` is a plain dict, serialized transparently  
**Testing**: `unittest` (project standard, `PYTHONPATH=src`)  
**Target Platform**: Docker (Debian-slim) / WSL2 Ubuntu; CPU-only for this node  
**Project Type**: Single project (`src/clipper/`)  
**Performance Goals**: `style_node` overhead < 100ms wall-clock (SC-005); pure file I/O, no inference  
**Constraints**: 8 GB RAM / WSL2; no GPU, CUDA, or heavy library imports in `style_node`; `visual_identity` values must be JSON-primitive (strings, numbers, booleans)  
**Scale/Scope**: Single pipeline run per Docker invocation; ~15 fields initially (CAPTION_* keys)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
|------|--------|-------|
| No new heavy dependencies | ✅ PASS | Only `pydantic` (already installed) and stdlib `json`/`pathlib` |
| Memory budget respected | ✅ PASS | `style_node` is pure I/O; no GPU/CUDA/inference resource |
| Synchronous node contract | ✅ PASS | `style_node` is a `def` function, no `async` |
| All state fields serializable | ✅ PASS | `visual_identity` is `dict[str, str | int | float | bool]` — SQLite-safe |
| `config.py` defaults preserved | ✅ PASS | Constants remain; nodes fall back when `visual_identity` key absent |
| No Regex / json.loads cleanup | ✅ PASS | Pydantic validates `estilo.json`, no string scraping |
| No telemetry library added | ✅ PASS | Observability via `pipeline.log` only |
| `create_graph()` sync guard maintained | ✅ PASS | `style_node` will pass the existing `iscoroutinefunction` check |

**Post-design re-check**: No violations. The design is fully compliant with AGENTS.md.

## Project Structure

### Documentation (this feature)

```text
specs/015-visual-identity-state/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/
│   └── visual_identity_schema.json   ← Phase 1 output
└── tasks.md             # Phase 2 output (speckit.tasks)
```

### Source Code (affected files)

```text
src/clipper/
├── core/
│   ├── orchestrator.py          ← add VideoState.visual_identity field + style_node + DAG edge
│   └── style_loader.py          ← NEW: pure I/O module (load_visual_identity)
├── video/
│   └── editor.py                ← read CAPTION_* from visual_identity when available
└── runtime/
    └── config.py                ← unchanged (constants kept as defaults)

tests/
└── test_style_node.py           ← NEW: comprehensive unit + integration test suite
```

**Structure Decision**: Single project layout. No new package or service boundary required; `style_loader.py` is a lightweight sibling of `ingestion.py` inside `core/`.

## Complexity Tracking

> No Constitution Check violations.
