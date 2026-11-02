# Feature Specification: HITL Review Delivery — Script Display & Conditional Rendering

**Feature Branch**: `019-hitl-review-delivery`  
**Created**: 2026-11-02  
**Status**: Draft  
**Input**: User description: "Exibir roteiro e metáforas visuais no servidor HTML de revisão e condicionar disparo do agente de renderização apenas aos cortes aprovados pelo HITL"

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — View Scene Script Before Rendering (Priority: P1)

As a content creator reviewing a cut in the web interface, I want to see the visual metaphors and animation triggers the AI planned for each scene so that I can make an informed approval decision before committing GPU/API resources to the heavy rendering phase.

**Why this priority**: This is the most critical user-facing value: without knowing *what* will be generated, the reviewer cannot make a meaningful approval decision. It also prevents wasted rendering time on unwanted creative directions.

**Independent Test**: Navigate to the review page for any pending cut and verify that the planned scenes (including `animation_trigger` and `visual_metaphor` fields) are rendered alongside the audio preview. No rendering work needs to happen for this to be testable.

**Acceptance Scenarios**:

1. **Given** a cut has been processed by the thinker and extractor nodes, **When** the reviewer opens the review page for that cut, **Then** each scene card is displayed with its `animation_trigger` label and `visual_metaphor` description clearly visible below or beside the audio/video preview.
2. **Given** a cut with multiple scenes, **When** the page renders, **Then** all scenes are listed in order, each in its own visual section, without truncation.
3. **Given** the review page is opened on a mobile viewport (≤ 768 px wide), **When** the scenes are rendered, **Then** the layout reflows responsively and all scene information remains legible without horizontal scrolling.
4. **Given** a cut with an empty `scenes` list (e.g. from a legacy checkpoint or test fixture), **When** the review page renders, **Then** a clear "No scene script available" placeholder is shown instead of a broken or empty section.

---

### User Story 2 — Approve Only Selected Cuts for Rendering (Priority: P2)

As a pipeline operator, I want the coder and execution nodes to process only the cuts I explicitly approved so that API tokens, GPU time, and CPU are not spent on rejected or skipped cuts.

**Why this priority**: Directly controls cost and processing time. Skipping this gate allows expensive rendering to fire on rejected content.

**Independent Test**: Trigger the pipeline to the rendering phase with a `decision.json` that marks some cuts as rejected. Verify that no render script is generated and no subprocess is launched for those rejected cuts.

**Acceptance Scenarios**:

1. **Given** a `decision.json` containing `approved_cut_ids: ["cut-0", "cut-2"]` and three total cuts, **When** the coder/execution loop runs, **Then** only `cut-0` and `cut-2` produce render scripts and subprocesses; `cut-1` is completely skipped with a log entry.
2. **Given** a `decision.json` where `approved_cut_ids` is an empty list, **When** the coder/execution loop runs, **Then** no render subprocess is launched and the pipeline logs a warning that all cuts were rejected before advancing gracefully to the final node.
3. **Given** a `decision.json` where all cuts are approved, **When** the coder/execution loop runs, **Then** every cut is processed in order, maintaining existing behavior with no regressions.
4. **Given** the pipeline is resumed from a checkpoint after a crash mid-render, **When** the orchestrator re-runs, **Then** the `approved_cut_ids` gate is re-evaluated from the persisted decision so that only the same approved set is rendered again.

---

### Edge Cases

- What happens when `decision.json` is missing or malformed? → When `review_directory` is present, the pipeline must fail fast with a `ValueError`, not silently render all cuts (isolated tests omitting `review_directory` fall back to `approved_cut_ids` in state).
- What happens when a `Scene` object has a `None` or empty `visual_metaphor`? → The review page must render a graceful fallback (e.g., "—") rather than an empty or broken cell.
- What happens when `approved_cut_ids` contains an ID that does not match any cut in `VideoState`? → The pipeline must log a warning for the unmatched ID and continue without crashing.
- What happens when the review page is loaded before the extractor node has written scene data? → The page must show a clear "Scene data not yet available" state.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The review page MUST display each `Scene` object's `animation_trigger` and `visual_metaphor` fields for a cut, rendered within that cut's existing preview card.
- **FR-002**: The review page MUST present scene information in the order it appears in the `scenes` list returned by the extractor node.
- **FR-003**: The review page layout MUST remain responsive at viewport widths from 320 px to 1920 px without breaking or hiding scene information.
- **FR-004**: The review page MUST display a clearly labelled fallback section when a cut has no scene data (empty or null `scenes` list).
- **FR-005**: Individual `Scene` fields (`animation_trigger`, `visual_metaphor`) that are empty or null MUST be replaced by a visible placeholder (e.g., "—") rather than rendering blank space.
- **FR-006**: The `coder_node` MUST read `approved_cut_ids` from the persisted `decision.json` and iterate the coder → execution loop exclusively over the cuts whose IDs appear in that list.
- **FR-007**: Cuts whose IDs are absent from `approved_cut_ids` MUST be skipped entirely — no render script generated, no subprocess launched — and each skip MUST produce a log entry at INFO level.
- **FR-008**: When `approved_cut_ids` is an empty list, the pipeline MUST log a warning, skip all rendering, and advance gracefully directly to LangGraph terminal node `END` without error.
- **FR-009**: The pipeline MUST fail fast with a `ValueError` (or equivalent explicit error) if `decision.json` is missing, unreadable, or structurally invalid at the point where `approved_cut_ids` is expected.
- **FR-010**: The `approved_cut_ids` gate MUST be re-applied correctly when the pipeline resumes from a checkpoint, ensuring no additional cuts are rendered beyond the persisted decision.

### Key Entities

- **Scene**: A structured object produced by the extractor node, containing at minimum `animation_trigger` (short label) and `visual_metaphor` (descriptive text). Displayed in the review page.
- **Decision**: A persisted record (sourced from `decision.json` and the SQLite checkpoint) containing `approved_cut_ids` — the authoritative list of cut identifiers cleared for rendering.
- **Cut**: A video segment identified by a unique ID, processed sequentially through the coder → execution loop. Its rendering is conditional on appearing in `approved_cut_ids`.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For 100% of cuts that have scene data, the review page displays both `animation_trigger` and `visual_metaphor` without manual intervention.
- **SC-002**: 0% of rejected cuts (absent from `approved_cut_ids`) result in a render subprocess being launched.
- **SC-003**: When `approved_cut_ids` is empty, the pipeline completes the delivery phase in under 5 seconds without errors.
- **SC-004**: The full test suite (unit + integration) continues to pass with 0 regressions after implementation; the two new feature behaviours each covered by at least one automated test.
- **SC-005**: The review page is fully legible and functional on viewports ranging from 320 px (mobile) to 1920 px (desktop) without horizontal overflow.

---

## Assumptions

- The `Scene` Pydantic model (with `animation_trigger` and `visual_metaphor` fields) already exists and is populated by the extractor node from feature 016.
- `decision.json` is written to the review directory by the approval node from feature 010, and its schema includes an `approved_cut_ids` field (list of strings).
- The review page is a server-side rendered HTML page (Jinja2 or equivalent) served from `src/clipper/review/review.py`. No JavaScript-heavy SPA framework is introduced.
- The `VideoState` object carried through LangGraph includes a `cortes_finais` field (with optional test-compatibility alias `cuts`) whose entries map to the values in `approved_cut_ids`.
- No new LLM, GPU, or network dependency is introduced by this feature.
- The SQLite checkpointer already persists the decision payload as part of the LangGraph state resume mechanism.

---

## Dependencies

- Feature 010 (manual-review-langgraph-integration): provides the HITL interrupt, `decision.json` schema, and `approved_cut_ids` field.
- Feature 016 (dynamic-scene-scripting): provides the `Scene` Pydantic model with `animation_trigger` and `visual_metaphor` fields.
- Feature 017 (self-healing-coder-dag): provides the `coder_node` and `execution_node` being gated by this feature.
- Feature 018 (sandbox-memory-management): provides the `release_cuda_memory` call in the `execution_node` finally block — must remain intact after gating logic is added.
