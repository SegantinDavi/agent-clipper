# Phase 0 Research: HITL Review Delivery — Script Display & Conditional Rendering

**Feature**: 019-hitl-review-delivery  
**Date**: 2026-11-02  
**Status**: Completed  

---

## 1. Technical Context & Unknowns Resolution

### Research 1.1: HTML Review Page Scene Script Rendering & Fallbacks
- **Unknown**: How should scene script data (`Scene` with `animation_trigger` and `visual_metaphor`) be formatted in the HTML review page when `scenes` is present, empty, or contains null/empty fields, while maintaining viewport responsiveness (320 px to 1920 px)?
- **Decision**: 
  - Enhance `render_review_page()` in `src/clipper/review/review.py` with structured scene card generation.
  - When `cut.scenes` is non-empty: iterate in sequence, rendering each scene's `start_word`, `end_word`, `visual_metaphor`, and `animation_trigger`.
  - When `cut.scenes` is empty or `None`: render a dedicated fallback block with class `scenes scenes-empty` displaying the placeholder `"No scene script available"` (FR-004).
  - For individual `Scene` fields: introduce a sanitizer helper that checks whether `visual_metaphor` or `animation_trigger` is `None`, empty string, or whitespace-only; if missing or empty, substitute with a visible placeholder `"&mdash;"` (`"—"`) instead of empty space (FR-005). All string content must be escaped via `html.escape()` to prevent HTML injection.
  - CSS responsiveness: Ensure `.scenes`, `.scenes-list`, and `.scene-item` contain `word-break: break-word` and `overflow-wrap: anywhere`. Add `@media (max-width: 480px)` styles for padding and single-column layout so that cards fit neatly on 320 px viewports without horizontal scrolling (FR-003, SC-005).
- **Rationale**: Keeps implementation dependency-free (no template engine needed; pure Python standard library `html`), robust against missing metadata, and fully responsive across mobile and desktop devices.
- **Alternatives Considered**:
  - *Jinja2 templating*: Adding Jinja2 would introduce a new dependency or unnecessary template files for a single server-side HTML page. Rejected to maintain minimal dependencies and keep review server self-contained.
  - *Client-side JavaScript rendering*: Fetching scene data via asynchronous AJAX requests in the browser. Rejected because server-side rendering is simpler, faster, works without JavaScript, and eliminates client-side hydration issues.

---

### Research 1.2: Decision Schema Alignment (`approved_ids` vs `approved_cut_ids`)
- **Unknown**: How should `ApprovalDecision` in `src/clipper/review/review.py` and `decision.json` reconcile `approved_ids: list[StrictInt]` (from Feature 010) with `approved_cut_ids: list[str | int]` (required by Feature 019 spec)?
- **Decision**:
  - Update `ApprovalDecision` in `src/clipper/review/review.py` to support both `approved_ids` and `approved_cut_ids` using `Union[int, str]` item types.
  - Implement Pydantic `@model_validator(mode="before")` and `@model_validator(mode="after")` to synchronize the two fields bidirectionally:
    - If `approved_cut_ids` is provided in the input dictionary/JSON, copy its values to `approved_ids`.
    - If `approved_ids` is provided, copy its values to `approved_cut_ids`.
    - When `save_approval_decision()` serializes to `decision.json`, both fields are written to disk.
  - In `load_approval_decision()`, return the list of approved IDs (supporting both string IDs like `"cut-0"` and integer IDs like `1`).
- **Rationale**: Ensures 100% backward compatibility with existing tests and modules that expect `approved_ids`, while natively supporting `approved_cut_ids` as mandated by Feature 019 requirements (FR-006, FR-009).
- **Alternatives Considered**:
  - *Hard break to only `approved_cut_ids`*: Would break ~20 existing tests in `test_review.py` and `test_coder_dag.py` that serialize `ApprovalDecision(approved_ids=[1])`. Rejected.
  - *Dynamic property*: Pydantic v2 properties do not serialize to JSON by default without computed fields, whereas bidirectional validators guarantee both keys appear in `decision.json`.

---

### Research 1.3: Coder Node Gating, Fail-Fast Decision Validation & Skip Auditing
- **Unknown**: How should `coder_node` validate `decision.json`, log skipped cuts, and gate execution so that rejected cuts never spawn render subprocesses?
- **Decision**:
  - **Fail-Fast Validation**: When `state.get("review_directory")` is present, `coder_node` checks for `decision.json`:
    - If `decision.json` does not exist: raise `ValueError(f"decision.json missing in review directory: {review_dir}")` (FR-009).
    - If `decision.json` is malformed or invalid: raise `ValueError(f"decision.json is unreadable or structurally invalid in: {review_dir}")` (FR-009).
    - If `review_directory` is empty or missing (e.g., in unit tests directly invoking `coder_node` with mocked state): fall back to `state.get("approved_cut_ids", [])`.
  - **Skip Logging (FR-007)**:
    - When starting cut iteration (`current_cut_index == 0`), `coder_node` inspects all cuts in the state (`cortes_finais` or `cuts`).
    - For each cut whose identifier is NOT in `approved_cut_ids`, emit `logger.info("Cut '%s' is not in approved_cut_ids. Skipping rendering.", cut_id)`.
    - For any ID in `approved_cut_ids` that does not match any cut in the state, emit `logger.warning("Approved cut ID '%s' does not match any cut in VideoState.", cut_id)`.
  - **Cut ID Matching**:
    - Support matching by explicit `id` key/attribute (e.g., `"cut-0"`, `"cut_42"`), 1-based index integer/string (e.g., `1`, `"1"`), or prefix pattern `"cut-{index}"`.
- **Rationale**: Satisfies FR-006, FR-007, and FR-009 with clear audit logs, without breaking existing callers or isolated unit tests.
- **Alternatives Considered**:
  - *Relying only on in-memory state*: Reading `approved_cut_ids` only from `VideoState` without checking `decision.json`. Rejected because FR-006 and FR-009 explicitly require reading and validating the persisted `decision.json`.

---

### Research 1.4: Zero-Subprocess Termination on Empty Approved Cuts
- **Unknown**: How to guarantee 0% subprocesses launched (SC-002) and under 5-second graceful completion (SC-003) when `approved_cut_ids` is an empty list?
- **Decision**:
  - **Graph Level (`create_graph`)**:
    - Add conditional routing function `route_approval_outcome(state: VideoState) -> str`:
      - If `state.get("approved_cut_ids")`: route to `"coder"`.
      - If `not state.get("approved_cut_ids")`: log warning `"No cuts approved in decision. Skipping all rendering."` and route directly to `END` (or delivery).
  - **Node Level Safeguards**:
    - In `coder_node`: If `not approved_ids`, log warning and return `{"render_script_path": "", "render_error": "No approved cuts available to process."}`.
    - In `execution_node`: If `not approved_ids` or `current_cut_index >= len(approved_ids)`, log warning and return `{"render_attempts": 0, "render_exit_code": 0, "render_error": ""}`.
- **Rationale**: When all cuts are rejected, routing immediately terminates at `END` in < 1ms, launching 0 subprocesses and logging a clear warning (FR-008, SC-002, SC-003). The node-level safeguards ensure that even if `coder_node` or `execution_node` is invoked directly or manually, it will never trigger a 3-attempt failure retry loop.
- **Alternatives Considered**:
  - *Retaining linear edge `approval` -> `coder`*: Causes `coder` to fail, triggering `execution_node` error handling and 3 dummy retry cycles before aborting. Rejected as a violation of FR-008 and SC-003.

---

### Research 1.5: Resumption and Idempotency Across Checkpoints
- **Unknown**: How does the SQLite checkpointer (`SqliteSaver`) interact with `decision.json` and `approved_cut_ids` on resume (FR-010)?
- **Decision**:
  - When the pipeline resumes from a checkpoint, `state["approved_cut_ids"]` is restored from the SQLite snapshot.
  - `coder_node` re-reads and re-validates `decision.json` from `review_directory`, ensuring the persisted disk decision remains the single source of truth.
  - The loop continues strictly over `approved_cut_ids` from `current_cut_index`, never processing rejected cuts.
- **Rationale**: Guarantees deterministic, idempotent resumption without rendering rejected cuts.
- **Alternatives Considered**:
  - *Overwriting `decision.json` on resume*: Unnecessary and risks state corruption. The persisted decision should be read-only during render.
