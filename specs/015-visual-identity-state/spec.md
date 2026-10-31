# Feature Specification: Visual Identity & Global State

**Feature Branch**: `015-visual-identity-state`  
**Created**: 2026-10-31  
**Status**: Draft  
**Input**: User description: "Fase 1: Identidade Visual e Estado Global — Carregar estilo.json dinâmico, expandir VideoState com visual_identity e implementar style_node no LangGraph"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pipeline Runs with Custom Brand Style (Priority: P1)

A content creator configures a brand identity file (`estilo.json`) in the project root before running the pipeline. When the pipeline executes, every generated Short/Reel clip reflects the brand's color palette, typography, and motion guidelines — without requiring manual edits to environment variables for each individual run.

**Why this priority**: This is the foundational capability that unlocks brand-consistent output. Without it, all downstream visual customization work has no stable entry point. Every downstream visual feature depends on the style being available in the DAG state.

**Independent Test**: Can be tested end-to-end by placing a valid `estilo.json` file in the project root, running the pipeline, and confirming the approved MP4 uses the specified caption color instead of the hardcoded default (`#25E600`).

**Acceptance Scenarios**:

1. **Given** a valid `estilo.json` exists in the project root, **When** the pipeline starts, **Then** the style definitions (palette, typography, motion) are loaded and made available to all downstream nodes via `VideoState.visual_identity`.
2. **Given** `estilo.json` does not exist, **When** the pipeline starts, **Then** the pipeline continues normally using the existing hardcoded defaults — no exception is raised and no node fails.
3. **Given** `estilo.json` exists but contains an incomplete structure, invalid JSON syntax, or malformed values, **When** the pipeline starts, **Then** the pipeline applies defaults for missing/invalid fields and emits a WARNING-level log entry identifying the issue — it does not crash.

---

### User Story 2 - Visual Style Survives Checkpoint Recovery (Priority: P2)

A pipeline run is interrupted mid-way (e.g., Docker container crash). When the operator resumes via `SqliteSaver` checkpoint, the visual identity loaded in the initial run is present in the recovered state — the operator does not need to re-supply or re-load the style file.

**Why this priority**: The pipeline already guarantees crash recovery for all other state fields. Excluding `visual_identity` from the checkpoint would cause silent inconsistency between the approved preview and the final exported clip.

**Independent Test**: Can be tested by running the pipeline until after the `style_node` completes, killing the process, and resuming — confirming `VideoState.visual_identity` is restored from SQLite without re-reading `estilo.json`.

**Acceptance Scenarios**:

1. **Given** a pipeline run was interrupted after `style_node` executed, **When** the pipeline resumes from checkpoint, **Then** `VideoState.visual_identity` is restored from SQLite with its original values intact.
2. **Given** a pipeline run is resumed with `--restart`, **When** the orchestrator purges the old checkpoint, **Then** `style_node` executes again and re-reads `estilo.json` from disk.

---

### User Story 3 - Operator Inspects Loaded Style at Runtime (Priority: P3)

An operator debugging a style inconsistency can confirm exactly which style values the pipeline loaded for a given run by reading the structured pipeline log (`pipeline.log`) — without inspecting the SQLite checkpoint directly.

**Why this priority**: Observability is required for diagnostics in the 8 GB RAM constrained environment where interactive debugging is impractical.

**Independent Test**: Can be tested by running the pipeline with a known `estilo.json`, then grepping `pipeline.log` for the style loading event, and asserting the logged values match the file.

**Acceptance Scenarios**:

1. **Given** the pipeline starts with `estilo.json` present, **When** `style_node` executes, **Then** an INFO-level log entry is written to `pipeline.log` listing the loaded style keys and their values.
2. **Given** no `estilo.json` is found, **When** `style_node` executes, **Then** a WARNING-level log entry is written stating that no style file was found and defaults are being used.

---

### Edge Cases

- What happens when `estilo.json` is valid JSON but contains unexpected top-level keys not recognized by the schema? → Unrecognized keys are ignored; no error is raised.
- What happens when `estilo.json` contains invalid JSON syntax or a non-dict root? → Handled gracefully; falls back to all field defaults and logs a WARNING without crashing.
- What happens when a HEX color value in `estilo.json` is malformed (e.g., `"#ZZZZZZ"`) or numeric values are non-positive? → The field falls back to the hardcoded default for that specific key and a WARNING is logged.
- What happens when `estilo.json` is absent or empty (`{}`)? → Treated identically to "missing fields" — all defaults apply and the complete dictionary of defaults is stored in `VideoState.visual_identity`.
- What happens when `VideoState.visual_identity` is `None` in a node downstream of `style_node`? → That node must fall back gracefully to module-level defaults; it must never raise a `KeyError` or `TypeError` due to a missing style field.
- What happens when the pipeline is run with `--restart`? → The `style_node` re-reads `estilo.json` from disk, overwriting any previously checkpointed `visual_identity`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST load style definitions from `estilo.json` located in the project root directory when the file is present at pipeline startup.
- **FR-002**: The system MUST operate without raising any exception when `estilo.json` is absent, applying all hardcoded defaults instead.
- **FR-003**: The system MUST apply per-field defaults for any key that is missing from `estilo.json`, logging a WARNING for each missing field.
- **FR-004**: The `VideoState` TypedDict MUST include a `visual_identity` field typed as `dict` to carry the style definitions through the LangGraph DAG.
- **FR-005**: The `visual_identity` field MUST be serializable to and from SQLite by the `SqliteSaver` checkpointer without data loss or type coercion.
- **FR-006**: The pipeline MUST include a `style_node` synchronous function registered in the `StateGraph` that reads the style configuration and writes it to `VideoState.visual_identity`.
- **FR-007**: The `style_node` MUST execute before any node that consumes visual style properties (e.g., caption rendering in video editor).
- **FR-008**: The `style_node` MUST emit an INFO-level log entry listing all loaded style values when `estilo.json` is found.
- **FR-009**: The `style_node` MUST emit a WARNING-level log entry when `estilo.json` is absent or when individual fields fall back to defaults.
- **FR-010**: All nodes downstream of `style_node` that currently read caption/visual constants directly from `config.py` MUST read from `VideoState.visual_identity` instead, falling back to the same hardcoded defaults if the field is absent or a key is missing.

### Key Entities

- **`estilo.json`**: A JSON file at the project root containing named style categories: `palette` (HEX color strings by role), `typography` (font sizes and stroke dimensions in pixels; font family is fixed to `Liberation-Sans-Bold` per AGENTS.md Rule 6), `layout` (caption positioning ratios), and `motion` (animation timing and caption grouping guidelines). All fields are optional with defined defaults.
- **`visual_identity`** (VideoState field): A flat dict of style properties derived from `estilo.json` (or defaults). Carries only serializable primitive values (strings, numbers, booleans). No file paths, no callable objects.
- **`style_node`**: A synchronous LangGraph node function that reads `estilo.json` and returns a partial state update `{"visual_identity": {...}}`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When `estilo.json` is present, 100% of its recognized style fields are reflected in `VideoState.visual_identity` with no data loss after the `style_node` executes.
- **SC-002**: When `estilo.json` is absent, the pipeline completes a full run producing a valid output clip with the same quality as before this feature existed — no regressions.
- **SC-003**: When the pipeline is interrupted and resumed from checkpoint after `style_node`, `VideoState.visual_identity` is byte-for-byte identical to the value stored before the interruption.
- **SC-004**: All existing tests continue to pass after this change (zero regression in the test suite).
- **SC-005**: The `style_node` execution overhead adds no more than 100ms to total pipeline wall-clock time, as verified by log timestamps.
- **SC-006**: An INFO or WARNING log entry related to style loading is present in `pipeline.log` for every pipeline run, with no run silently omitting this event.

## Assumptions

- The `estilo.json` schema is project-defined and not externally standardized. The initial schema will include at minimum the keys that replace the current `CAPTION_*` variables in `config.py`.
- `visual_identity` is a plain dict of primitives; no nested objects that are not JSON-serializable will be stored.
- The `style_node` is positioned in the DAG between `fatiamento_node` and `transcription_node` (and before `thinker_node`), matching the sequential pipeline flow.
- Downstream nodes that currently read `CAPTION_*` from `config.py` will be updated as part of this feature only to the extent they use the `visual_identity` dict from state — the `config.py` constants are preserved as fallback defaults, not removed.
- No GPU, CUDA, or heavy inference resources are used by `style_node`; it is a pure I/O operation.
