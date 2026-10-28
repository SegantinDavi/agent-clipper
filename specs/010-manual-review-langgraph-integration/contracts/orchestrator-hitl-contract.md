# API Contract: Orchestrator Human-in-the-Loop Interface

**Feature**: `010-manual-review-langgraph-integration`  
**Date**: 2026-10-28  
**Scope**: LangGraph node suspension, orchestrator driver, and command resumption contracts.

---

## 1. Approval Node Contract (`approval_node`)

### Signature
```python
def approval_node(state: VideoState) -> dict:
    ...
```

### Suspension Behavior
- When `state.get("cortes_finais")` is empty:
  - **Returns**: `{"approved_cut_ids": [], "approval_complete": True}`
  - Does NOT call `interrupt()`.
- When candidate cuts are present:
  - Calls `interrupt({"review_directory": state["review_directory"], "cut_count": len(cuts)})`.
  - On resumption, receives `decision: dict` payload passed by `Command(resume=...)`.
  - Validates `decision` with `validate_approval(decision, len(cuts))`.
  - **Returns**: `{"approved_cut_ids": ids, "approval_complete": True}`.

---

## 2. Orchestrator Driver Contract (`run_with_review`)

### Signature
```python
def run_with_review(
    app: CompiledStateGraph,
    initial_state: VideoState,
    graph_config: dict,
    restart: bool = False,
    review_port: int = 8765,
) -> dict:
    ...
```

### Preconditions
- `graph_config` must contain `{"configurable": {"thread_id": str}}`.
- SQLite checkpointer must be connected and initialized on `app.checkpointer`.
- Checkpoint purge on `--restart` accesses `app.checkpointer` directly without requiring explicit connection arguments.

### Postconditions
- On `--restart=True`:
  - Existing records for `thread_id` are deleted from the checkpointer.
  - The graph starts fresh from `START`.
- On container restart (no `--restart`):
  - If previous run completed: logs completion and returns `snapshot.values` without executing any node.
  - If previous run was interrupted at review:
    - If `decision.json` exists on disk: resumes graph via `Command(resume={"approved_ids": ids})` without launching review server.
    - If `decision.json` does not exist: serves review page on `http://127.0.0.1:{review_port}/`, waits for approval POST, commits `decision.json`, and resumes graph via `Command(resume={"approved_ids": ids})`.
- The function returns the final graph state dictionary upon completion of all nodes.

---

## 3. Command Resume Contract

### Format
```python
Command(resume={"approved_ids": list[int]})
```

### Constraints
- `approved_ids` MUST be a list of 1-based indices corresponding to candidate cuts in `cortes_finais`.
- An empty list `[]` denotes explicit rejection of all cuts.
- Invalid cut IDs, out-of-range indices, duplicates, or non-integer values MUST raise `ValueError` during validation before state is mutated.
