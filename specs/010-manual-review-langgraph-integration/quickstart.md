# Developer Quickstart: LangGraph Native HITL Checkpoint Integration

**Feature Branch**: `010-manual-review-langgraph-integration`  
**Date**: 2026-10-28  
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

This quickstart guides developers through testing and validating the crash-safe Human-in-the-Loop review integration with LangGraph.

---

## 1. Running HITL Approval Tests

Execute the unit tests specifically validating the decoupled review server, `interrupt()` handling, atomic `decision.json` durability, and crash recovery:

```bash
# Run review and HITL tests:
PYTHONPATH=src venv/bin/python -m unittest tests/test_review.py

# Run all test suites:
PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"
```

---

## 2. Validating Crash Resilience Scenarios

### Scenario A: Resuming when killed during the review wait window
1. Run pipeline against a test video:
   ```bash
   PYTHONPATH=src venv/bin/python -m clipper.core.orchestrator
   ```
2. Wait until the review URL appears:
   ```text
   Revise e aprove os cortes no navegador: http://127.0.0.1:8765/
   ```
3. Send `SIGKILL` (`Ctrl+\` or `kill -9 <PID>`).
4. Re-run the exact same command (without `--restart`):
   ```bash
   PYTHONPATH=src venv/bin/python -m clipper.core.orchestrator
   ```
5. **Expected behavior**:
   - The pipeline does NOT repeat video download, fatiamento, transcription, or LLM reasoning.
   - It immediately detects the SQLite interrupt snapshot and re-opens the review server at `http://127.0.0.1:8765/`.

---

### Scenario B: Resuming after `decision.json` committed
1. While review server is open, submit approval in browser (or manually place a valid `decision.json` in the review directory).
2. Immediately terminate the process before video rendering completes.
3. Re-run the pipeline without `--restart`:
   ```bash
   PYTHONPATH=src venv/bin/python -m clipper.core.orchestrator
   ```
4. **Expected behavior**:
   - The orchestrator detects `decision.json`.
   - The review server is skipped completely.
   - Execution resumes directly at `editor_node` to render the approved cuts.

---

### Scenario C: Clean restart with `--restart`
1. Run the pipeline with `--restart`:
   ```bash
   PYTHONPATH=src venv/bin/python -m clipper.core.orchestrator --restart
   ```
2. **Expected behavior**:
   - Previous SQLite checkpoints for this thread are purged.
   - The pipeline executes cleanly from the initial `download` node, ignoring prior manifests and decisions.

---

## 3. Key Source Files

- `src/clipper/core/orchestrator.py`:
  - `approval_node`: Issues `interrupt()`.
  - `run_with_review`: Orchestrates snapshot inspection, disk decision lookup, server lifecycle, and `Command(resume=...)`.
  - `checkpoint_thread_id`: Generates deterministic thread IDs.
- `src/clipper/review/review.py`:
  - `wait_for_approval` & `create_review_server`: Serves HTML UI and performs atomic write of `decision.json`.
- `tests/test_review.py`:
  - Unit and integration tests covering HITL suspension, SQLite persistence, and `--restart` behavior.
