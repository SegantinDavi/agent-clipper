# Contract: Decision Gating & Conditional Execution

**Feature**: 019-hitl-review-delivery  
**Contract ID**: CTR-019-02  
**Applies to**: `src/clipper/core/orchestrator.py` (`coder_node`, `execution_node`, `create_graph`, `route_approval_outcome`) and `src/clipper/review/review.py` (`ApprovalDecision`, `save_approval_decision`)  

---

## 1. Persisted Decision Format (`decision.json`)

`decision.json` stored in `/app/output/reviews/<review_id>/decision.json` MUST adhere to the following JSON schema:

```json
{
  "approved_ids": [1, 3],
  "approved_cut_ids": [1, 3]
}
```
Or for string IDs:
```json
{
  "approved_ids": ["cut-0", "cut-2"],
  "approved_cut_ids": ["cut-0", "cut-2"]
}
```

Both `approved_ids` and `approved_cut_ids` MUST be present upon serialization. Readers MUST accept either key.

---

## 2. Fail-Fast Validation Contract (FR-009)

When `coder_node` executes:
1. If `review_directory` is present in state:
   - Check if `Path(review_directory) / "decision.json"` exists on disk.
   - If missing: raise `ValueError(f"decision.json not found in review directory: {review_dir}")`.
   - If corrupted or structurally invalid: raise `ValueError(f"decision.json is unreadable or structurally invalid in: {review_dir}")`.
2. If `review_directory` is empty or omitted (isolated unit test mode):
   - Fall back to `state.get("approved_cut_ids", [])`.

---

## 3. Gating & Skip Auditing Contract (FR-006, FR-007, FR-008, SC-002, SC-003)

### 3.1 Rejected Cuts (FR-007, SC-002)
- On the initial iteration pass only (`current_cut_index == 0 and render_attempts == 0`), for every cut in `cortes_finais` (or `cuts`) whose identifier does NOT appear in `approved_cut_ids`:
  - MUST emit an audit log entry at level `INFO`:
    `logger.info("Cut '%s' is not in approved_cut_ids. Skipping rendering.", cut_id)`
  - MUST NOT generate a `render_script.py` for this cut.
  - MUST NOT invoke `subprocess.run` or spawn any subprocess for this cut (0% subprocess execution).

### 3.2 Empty Selection / Rejection of All Cuts (FR-008, SC-003)
- When `approved_cut_ids == []`:
  - `route_approval_outcome(state)` evaluates after `approval_node`.
  - MUST emit a warning log:
    `logger.warning("No cuts approved in decision. Skipping all rendering.")`
  - MUST route directly to `END` (or delivery complete) without triggering coder retries or abort errors.
  - Pipeline MUST terminate in under 5 seconds (target < 500ms).

### 3.3 Unknown / Unmatched Cut IDs (Edge Case)
- When `approved_cut_ids` contains an ID that does not match any cut in `VideoState`:
  - MUST emit a warning log:
    `logger.warning("Approved cut ID '%s' does not match any cut in VideoState.", cut_id)`
  - MUST NOT crash or raise unhandled exceptions; continues iteration over remaining approved cuts.

### 3.4 Cut Identifier Resolution Strategy (I2 Remediation)
When matching an item `cut_id` from `approved_cut_ids` to the video cut in `cortes_finais` (or `cuts`), `coder_node` must resolve the cut object using the following deterministic precedence:
1. **Explicit dictionary `id`**: If the item in `cortes_finais` is a `dict` with key `"id"`, match `str(corte["id"]) == str(cut_id)`.
2. **Positional Pattern Match**: If `cut_id` is a string matching regex `^cut[-_]?(\d+)$` (case-insensitive):
   - Parse index $N$: if $0 \le N < \text{len(cortes)}$, match `cortes[N]` (0-based convention).
3. **1-based Integer Index**: If `cut_id` is an `int` (or a string containing only digits), and $1 \le \text{int}(cut\_id) \le \text{len(cortes)}$:
   - Match `cortes[cut_id - 1]`.
4. **Fallback Unmatched**: If no rule matches, emit `logger.warning("Approved cut ID '%s' does not match any cut in VideoState.", cut_id)` and do not render.

---

## 4. Checkpoint Resumption Invariant (FR-010)

- When resuming an interrupted or crashed graph from `SqliteSaver`, the gate `approved_cut_ids` is re-read from `decision.json` on disk by `coder_node`.
- No cuts beyond those recorded in `decision.json` may be rendered.
