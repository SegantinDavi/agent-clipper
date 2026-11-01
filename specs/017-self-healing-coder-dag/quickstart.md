# Quickstart: Feature 017 — Self-Healing Coder DAG

**Branch**: `017-self-healing-coder-dag`

---

## Overview

Feature 017 implements **Phase 3: Self-Healing Coder DAG**. It replaces the monolithic deterministic `editor_node` with a modular, self-healing code generation and execution architecture in LangGraph:
1. **`coder_node`**: Invokes the configured LLM using Instructor Constrained Decoding to generate a self-contained Python render script (`render_script.py`) based on scenes, timestamps, visual identity, and previous error logs.
2. **`execution_node`**: Executes the generated script in an isolated child subprocess, capturing stdout, stderr, and exit codes without risking orchestrator crashes.
3. **Conditional Self-Healing Edge**: Automatically routes back to `coder_node` on failure (up to 3 attempts) with `stderr` diagnostics injected into the retry prompt, or routes to `abort_node` if attempts are exhausted.

---

## Modified & Added Files

| File | Changes |
|---|---|
| `src/clipper/core/schemas.py` | Defines `RenderScriptPayload(BaseModel)` with constrained decoding schema |
| `src/clipper/core/prompts.py` | Adds `CODER_SYSTEM_PROMPT` and `CODER_RETRY_PROMPT_TEMPLATE` |
| `src/clipper/core/orchestrator.py` | Implements `coder_node`, `execution_node`, `abort_node`, `route_execution_outcome`, extends `VideoState`, and updates DAG in `create_graph` |
| `tests/test_coder_dag.py` | **New file**: Comprehensive test suite covering script generation, subprocess execution, retry loops, abort handling, and SQLite crash recovery |

---

## Verification & Testing

### 1. Run Feature-Specific Test Suite

Execute the dedicated coder DAG and self-healing test suite:

```bash
PYTHONPATH=src venv/bin/python -m unittest tests/test_coder_dag.py
```

### 2. Run LangGraph Contract & Architecture Tests

Verify that all DAG nodes adhere strictly to synchronous contracts:

```bash
PYTHONPATH=src venv/bin/python -m unittest tests/test_instructor_sync_contract.py tests/test_checkpoint_thread_id.py
```

### 3. Run Full Discovery Regression Suite

Verify 100% passing status across all existing unit and integration tests (202+ tests, 0 regressions):

```bash
PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"
```

---

## Inspecting Execution & Self-Healing

### 1. In `pipeline.log`

Inspect the coder node and execution node logs:

```bash
grep -E "coder_node|execution_node|Self-healing|aborted" output/pipeline.log
```

Expected output on retry:
```text
INFO - coder_node: Generating render script for cut '1' (Attempt 1/3)...
INFO - coder_node: Script written to /app/output/1/render_script.py
INFO - execution_node: Executing /app/output/1/render_script.py in isolated subprocess...
WARNING - execution_node: Execution failed with exit code 1. Stderr: ZeroDivisionError: division by zero
INFO - Self-healing triggered: Retrying cut '1' with previous error feedback (Attempt 2/3)...
INFO - execution_node: Execution succeeded with exit code 0.
```

### 2. Generated Render Scripts

The self-contained render scripts are saved per cut:

```bash
cat output/<cut_id>/render_script.py
```
