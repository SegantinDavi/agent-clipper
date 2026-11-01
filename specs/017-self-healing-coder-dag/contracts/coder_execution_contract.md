# Interface Contract: Coder Node, Execution Node & Self-Healing DAG

**Branch**: `017-self-healing-coder-dag` | **Date**: 2026-10-31 | **Spec**: [spec.md](../spec.md)

---

## 1. Module: `clipper.core.orchestrator`

### Contract 1: `coder_node(state: VideoState) -> dict`

#### Description
Generates a self-contained Python render script (`render_script.py`) tailored to an approved cut candidate using Constrained Decoding via Instructor and Pydantic (`RenderScriptPayload`).

#### Signature
```python
def coder_node(state: VideoState) -> dict: ...
```

#### Preconditions
1. `state` must be a valid dictionary matching `VideoState`.
2. `state.get("approval_complete") is True` (enforced by upstream `approval_node`).
3. An approved cut must be accessible via `cortes_finais` and `approved_cut_ids`.
4. If this is a retry attempt (`state.get("render_attempts", 0) > 0`), `state.get("render_error")` contains the diagnostic `stderr` from the previous execution failure.

#### Postconditions
1. Must be declared as a strict synchronous function (`inspect.iscoroutinefunction(coder_node) is False`).
2. The raw LLM client is instantiated via `create_llm_client()` and closed deterministically in a `finally: raw_client.close()` block.
3. Constrained decoding is executed via `instructor.from_openai(raw_client, mode=instructor.Mode.JSON_SCHEMA)` with `response_model=RenderScriptPayload` and strict JSON Schema.
4. The generated Python script is written to `/app/output/<cut_id>/render_script.py` (or test directory) with UTF-8 encoding.
5. Returns a state update dictionary containing:
   - `"render_script_path"`: absolute string path to the saved script file.
6. If the LLM produces empty/invalid content or fails, `coder_node` sets `"render_error"` in state, allowing the self-healing conditional edge to process the failure safely without unhandled crashes.

---

### Contract 2: `execution_node(state: VideoState) -> dict`

#### Description
Executes the generated `render_script.py` in an isolated child subprocess, increments the `render_attempts` counter, and captures exit code, stdout, and stderr into state without crashing the orchestrator.

#### Signature
```python
def execution_node(state: VideoState) -> dict: ...
```

#### Preconditions
1. `state` must be a valid dictionary matching `VideoState`.
2. `state.get("render_script_path")` contains the script path to run, or empty string if upstream generation failed.

#### Postconditions
1. Must be declared as a strict synchronous function (`inspect.iscoroutinefunction(execution_node) is False`).
2. Increments `render_attempts` counter by 1 (`state.get("render_attempts", 0) + 1`).
3. If `render_script_path` is empty or the file does not exist: skips subprocess execution, sets `render_exit_code = -1`, and records `"Render script file missing or not generated"` in `render_error` (or preserves upstream error).
4. If `render_script_path` exists: executes via `subprocess.run([sys.executable, script_path], capture_output=True, text=True, timeout=RENDER_TIMEOUT_SECONDS)`.
5. Handles timeout gracefully: if `subprocess.TimeoutExpired` occurs, the process is killed, exit code is set to non-zero (`-1`), and `render_error` records the timeout.
6. Handles subprocess failures gracefully: does not raise unhandled exceptions for runtime errors inside the script.
7. Returns a state update dictionary containing:
   - `"render_attempts"`: updated integer counter (`1`, `2`, or `3`).
   - `"render_exit_code"`: integer return code (`0` for success, non-zero for failure).
   - `"render_error"`: `""` on success, or captured `stderr` string on failure.

---

### Contract 3: `route_execution_outcome(state: VideoState) -> str`

#### Description
Conditional routing function evaluated by LangGraph after `execution_node` completes an attempt.

#### Signature
```python
def route_execution_outcome(state: VideoState) -> str: ...
```

#### Routing Logic:
- If `state.get("render_exit_code", 0) == 0`:
  - Returns `"complete"` (routes downstream to completion or next cut).
- If `state.get("render_exit_code", 0) != 0`:
  - If `state.get("render_attempts", 0) < 3`:
    - Returns `"retry"` (routes back to `coder_node`).
  - Else (`state.get("render_attempts", 0) >= 3`):
    - Returns `"abort"` (routes to `abort_node`).

---

### Contract 4: `abort_node(state: VideoState) -> dict`

#### Description
Terminal recovery node executed when a cut exhausts all 3 render attempts without succeeding.

#### Signature
```python
def abort_node(state: VideoState) -> dict: ...
```

#### Postconditions
1. Must be declared as a strict synchronous function (`inspect.iscoroutinefunction(abort_node) is False`).
2. Logs an error/warning in `pipeline.log` noting that the cut was aborted after 3 attempts.
3. Returns a state update dictionary containing:
   - `"render_aborted": True`
4. The orchestrator continues safely without crashing or terminating the entire pipeline.
