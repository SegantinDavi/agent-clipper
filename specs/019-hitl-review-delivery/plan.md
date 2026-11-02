# Implementation Plan: HITL Review Delivery — Script Display & Conditional Rendering

**Branch**: `019-hitl-review-delivery` | **Date**: 2026-11-02 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/019-hitl-review-delivery/spec.md`

## Summary

Implement **Feature 019: HITL Review Delivery — Script Display & Conditional Rendering** for the agent-clipper pipeline.

This feature completes the human-in-the-loop review and render-gating lifecycle:
1. **Scene Script & Metaphor Review Display**: Enhances `render_review_page()` in `src/clipper/review/review.py` to display visual metaphors (`visual_metaphor`) and animation triggers (`animation_trigger`) for each scene within preview cards in sequence. Incorporates a clear fallback message (`"No scene script available"`) for cuts with empty/null scene lists (FR-004), visible placeholders (`"—"`) for empty/null scene fields (FR-005), and responsive styles avoiding horizontal overflow on 320 px to 1920 px viewports (FR-003, SC-005).
2. **Selective Cut Gating & Subprocess Protection**: Updates `ApprovalDecision` in `src/clipper/review/review.py` to support both `approved_ids` and `approved_cut_ids` transparently. Gating logic in `coder_node` reads and validates `decision.json` from the review directory (failing fast with `ValueError` if missing or malformed, FR-009), ensuring the render loop processes only explicitly approved cuts while logging an `INFO` skip audit for rejected cuts (FR-006, FR-007).
3. **Graceful Empty Selection Completion**: Updates graph routing via `route_approval_outcome()` in `src/clipper/core/orchestrator.py` so that when `approved_cut_ids` is empty, all rendering is bypassed, logging a warning and advancing to graph termination in < 5 seconds without triggering error retries or spawning subprocesses (FR-008, SC-002, SC-003).

## Technical Context

**Language/Version**: Python 3.12+ (tested on Python 3.12 – 3.14)  
**Primary Dependencies**: `pydantic` (already in stack), `langgraph` (already in stack), `moviepy==1.0.3` (already in stack), Python standard library (`html`, `logging`, `pathlib`, `json`)  
**Storage**: SQLite via `SqliteSaver` (`/app/output/estado.db`), `decision.json` in `/app/output/reviews/<id>/`, logs in `/app/output/pipeline.log`  
**Testing**: `unittest` (standard project test harness, `PYTHONPATH=src`)  
**Target Platform**: Linux (Debian-slim Docker on WSL2 Ubuntu, 8 GB RAM / 8 GB Swap)  
**Project Type**: Single project (`src/clipper/`)  
**Performance Goals**: Empty selection completion < 5s (SC-003); review page rendering overhead < 50ms; 0% subprocesses launched for rejected cuts (SC-002)  
**Constraints**: 8 GB RAM / WSL2; zero new dependencies; strict synchronous node contracts (`def`); no regex / manual json.loads for LLM output (AGENTS.md Rule 5); backward compatibility with existing callers and tests; safe responsive HTML layout across 320 px to 1920 px viewports  
**Scale/Scope**: Typically 1–10 cuts per podcast episode, each containing 3–15 planned scenes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
|---|---|---|
| No new heavy dependencies | ✅ PASS | Zero new dependencies. Uses Python standard library (`html`, `logging`, `pathlib`) and existing project stack (`pydantic`, `langgraph`). |
| Memory budget respected | ✅ PASS | WSL2 8GB RAM / RTX 3060 12GB VRAM. No additional memory footprint introduced. |
| Constrained Decoding only | ✅ PASS | `ApprovalDecision`, `Scene`, `CorteVideo` validated via Pydantic schemas. No regex or manual `json.loads` parsing of LLM output. |
| Single-Model cognitive routing | ✅ PASS | Preserved; no changes to LLM client allocation. |
| Strict synchronous node contract | ✅ PASS | All graph nodes (`approval_node`, `coder_node`, `execution_node`, `advance_cut_node`) remain synchronous callables (`def`). |
| State serialization in SQLite | ✅ PASS | `approved_cut_ids` is a list of primitives (`int` / `str`), serializing cleanly with `SqliteSaver`. |
| Subprocess isolation & Timeout | ✅ PASS | Coder/execution subprocess isolation and timeout protection intact; 0% subprocesses fired for rejected cuts. |
| Safe CPU/Ollama fallback | ✅ PASS | Review page rendering and gating logic are fully hardware-agnostic, running identically on CPU and GPU profiles. |
| No external telemetry | ✅ PASS | Observability via standard logging in `pipeline.log`. |
| Zero regressions | ✅ PASS | 100% backward-compatible schemas (`approved_ids` and `approved_cut_ids` synchronized), preserving all 256 existing tests. |

**Post-design re-check**: No violations. The design adheres strictly to all AGENTS.md rules and architectural constraints.

## Project Structure

### Documentation (this feature)

```text
specs/019-hitl-review-delivery/
├── plan.md              ← this file (/speckit.plan command output)
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── checklists/
│   └── requirements.md  ← specification checklist
├── contracts/
│   ├── review_html_contract.md     ← Phase 1 output (DOM structure, fallbacks, placeholders, responsiveness)
│   └── decision_gating_contract.md ← Phase 1 output (decision.json schema, fail-fast validation, skip auditing)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (affected files)

```text
src/clipper/
├── review/
│   └── review.py        ← enhance render_review_page with scene fallbacks/placeholders/responsive styles, and update ApprovalDecision with bidirectional synchronization
└── core/
    └── orchestrator.py  ← add route_approval_outcome conditional edge, fail-fast decision.json validation in coder_node, cut skip auditing, and safe empty-approval termination

tests/
├── test_review_delivery.py  ← NEW: unit and integration tests for scene display, placeholders, fallbacks, decision gating, skip logging, and empty approval termination
├── test_review.py           ← verify compatibility with existing review and HITL tests
└── test_coder_dag.py        ← verify compatibility with existing coder DAG tests
```

**Structure Decision**: Single project layout (`src/clipper/`). No new packages or external services required. Changes integrate directly into `src/clipper/review/review.py` and `src/clipper/core/orchestrator.py`, with dedicated tests in `tests/test_review_delivery.py`.

## Complexity Tracking

> No Constitution Check violations.
