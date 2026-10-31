# Feature Specification: Self-Healing Coder DAG

**Feature Branch**: `017-self-healing-coder-dag`
**Created**: 2026-10-31
**Status**: Draft
**Input**: User description: "Fase 3: Orquestração do Agente Codificador — substituição do editor_node por coder_node + execution_node + self-healing via arestas condicionais LangGraph com máximo de 3 tentativas."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — LLM generates a render script from an approved cut (Priority: P1)

An operator approves a video cut. Instead of MoviePy being called directly, the pipeline asks the configured LLM to write a self-contained Python render script tailored to the cut's scene list, word timestamps, visual style, and audio path. The generated script is saved to disk and its path is recorded in the pipeline state.

**Why this priority**: This is the core architectural shift — replacing the deterministic editor with an LLM-driven coder. All subsequent nodes depend on a valid script file existing in state.

**Independent Test**: Can be tested by injecting a mock `VideoState` with a populated `cortes_finais` entry and asserting that a non-empty Python file is written to the output directory and its path lands in `VideoState`.

**Acceptance Scenarios**:

1. **Given** a `VideoState` containing an approved cut with scene list, word timestamps, style dict, and audio path, **When** `coder_node` is invoked, **Then** a `render_script.py` file is written to `/app/output/<cut_id>/render_script.py` and its path is stored in `VideoState["render_script_path"]`.
2. **Given** `coder_node` receives all required inputs, **When** the LLM returns a valid Python string, **Then** the file is saved with UTF-8 encoding and the node does not raise an exception.
3. **Given** the LLM response is empty or malformed, **When** `coder_node` processes the response, **Then** the node raises an error that triggers the self-healing retry flow (sets `render_error` in state).

---

### User Story 2 — Script is executed safely and outcome is captured (Priority: P2)

After the script file exists in state, the pipeline executes it in an isolated subprocess. Whether the script succeeds or crashes, the result (exit code, stdout, stderr) is captured and stored in state without crashing the orchestrator.

**Why this priority**: Safe execution and reliable failure capture are prerequisites for self-healing. Without this node the retry loop cannot function.

**Independent Test**: Can be tested by providing a trivially valid Python script and a deliberately broken one, verifying that exit codes and error logs flow into `VideoState` correctly in both cases.

**Acceptance Scenarios**:

1. **Given** `VideoState["render_script_path"]` points to a syntactically valid Python script that runs without error, **When** `execution_node` is invoked, **Then** `VideoState["render_exit_code"]` is `0` and `VideoState["render_error"]` is empty.
2. **Given** the render script raises a runtime exception, **When** `execution_node` captures the subprocess output, **Then** `VideoState["render_exit_code"]` is non-zero and `VideoState["render_error"]` contains the full `stderr` text from the subprocess.
3. **Given** the subprocess completes (success or failure), **When** `execution_node` returns, **Then** the orchestrator DAG continues to the next conditional edge without raising an unhandled exception.

---

### User Story 3 — Pipeline self-heals by retrying up to 3 times before giving up (Priority: P3)

When the render script fails, the error log is fed back to the LLM so it can generate a corrected version. This retry loop is governed by a counter in state. After three consecutive failures the pipeline aborts the cut with a clear error record, allowing the rest of the pipeline to continue with other cuts.

**Why this priority**: Automated recovery avoids operator intervention for transient or fixable LLM mistakes, delivering a more autonomous pipeline. It is built on top of P1 and P2.

**Independent Test**: Can be tested by wiring a mock `coder_node` that always produces a failing script, verifying the counter increments on each retry and the DAG transitions to the abort edge after the third failure.

**Acceptance Scenarios**:

1. **Given** `execution_node` reports a non-zero exit code and `VideoState["render_attempts"]` is less than `3`, **When** the conditional edge is evaluated, **Then** the DAG routes back to `coder_node` with the previous `render_error` available in state for the LLM prompt.
2. **Given** `execution_node` reports a non-zero exit code and `VideoState["render_attempts"]` equals `3`, **When** the conditional edge is evaluated, **Then** the DAG routes to the abort/skip edge, sets `VideoState["render_aborted"]` to `True`, and does **not** retry.
3. **Given** a retry corrects the script and `execution_node` reports exit code `0`, **When** the conditional edge is evaluated, **Then** the DAG proceeds normally to the next downstream node and the retry counter is not incremented further.

---

### Edge Cases

- What happens when the LLM returns an empty string for the render script?
- What happens when the render subprocess exceeds a reasonable wall-clock time limit (e.g., hangs indefinitely)?
- What happens if disk is full and the script file cannot be written?
- What happens when `render_attempts` is missing from `VideoState` (first run with no checkpoint)?
- What happens if `coder_node` itself raises an exception (network error calling the LLM API)?
- What happens when `stderr` from the subprocess is longer than a safe token budget for the LLM retry prompt?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pipeline MUST replace the current `editor_node` entry point with `coder_node` as the first rendering step for approved cuts.
- **FR-002**: `coder_node` MUST accept the cut's scene list, word timestamp array, audio file path, and visual style configuration as inputs and produce a self-contained Python render script as output.
- **FR-003**: `coder_node` MUST persist the generated render script to a deterministic file path within the output volume and record that path in `VideoState`.
- **FR-004**: `execution_node` MUST run the render script as an isolated subprocess, capturing both `stdout` and `stderr` without allowing subprocess failures to crash the orchestrator process.
- **FR-005**: `execution_node` MUST store the subprocess exit code and the full `stderr` content in `VideoState` after each execution attempt.
- **FR-006**: The DAG MUST include conditional edges from `execution_node` that route to `coder_node` on failure (exit code ≠ 0, attempts < 3) and to the downstream node on success (exit code = 0).
- **FR-007**: `VideoState` MUST include a `render_attempts` counter initialized to `0` that is incremented by `execution_node` on each invocation for a given cut.
- **FR-008**: After three consecutive failed render attempts for a cut, the DAG MUST route to an abort edge that marks `VideoState["render_aborted"]` as `True` and skips the cut without terminating the overall pipeline.
- **FR-009**: When `coder_node` is retried after a failure, the LLM prompt MUST include the `stderr` from the previous failed execution so the model can reason about the error.
- **FR-010**: Both `coder_node` and `execution_node` MUST be synchronous functions (`def`) compatible with LangGraph's `StateGraph` synchronous invocation contract.
- **FR-011**: The same LLM backend selected by `LLM_PROVIDER` (Ollama or Gemini) MUST be used by `coder_node`, with no additional model loaded simultaneously.
- **FR-012**: The `render_attempts` counter and `render_aborted` flag MUST be persisted by the existing `SqliteSaver` checkpointer so retries survive container restarts.

### Key Entities

- **`coder_node`**: A LangGraph node that calls the configured LLM to generate a Python render script from cut metadata and returns the script file path via `VideoState`.
- **`execution_node`**: A LangGraph node that executes the render script as a subprocess and writes exit code and stderr back to `VideoState`.
- **`render_script_path`** (VideoState field): Absolute path to the generated `.py` file for the current cut.
- **`render_attempts`** (VideoState field): Integer counter tracking how many execution attempts have been made for the current cut; reset per cut.
- **`render_error`** (VideoState field): String containing the `stderr` of the last failed subprocess execution; empty string on success.
- **`render_aborted`** (VideoState field): Boolean flag set to `True` when the cut is skipped after exhausting all retry attempts.
- **Conditional Edge (execution → coder / downstream / abort)**: The routing function that reads `render_exit_code` and `render_attempts` to decide the next DAG node.

## Assumptions

- The render script generated by the LLM is expected to use only libraries already present in the Docker image (`moviepy==1.0.3`, `ffmpeg`, `Pillow`, standard library). The LLM system prompt will enumerate allowed imports explicitly.
- A subprocess timeout will be set to a project-defined environment variable (e.g., `RENDER_TIMEOUT_SECONDS`, defaulting to `300`); hanging subprocesses will be killed and treated as failures.
- `stderr` fed back to the LLM on retry will be truncated to a configurable maximum length (e.g., `RENDER_ERROR_MAX_CHARS`, defaulting to `2000`) to stay within token budget.
- The `render_attempts` counter is per-cut, not global. It resets when a new cut begins processing.
- The existing `approval_node` `interrupt()` HITL flow is unchanged; `coder_node` only activates after human approval is granted.
- No second LLM is introduced; `coder_node` reuses the `create_llm_client` factory already present in the codebase.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An approved cut produces a valid rendered video file without operator intervention in at least 90% of end-to-end pipeline runs using a standard test video.
- **SC-002**: When a deliberately broken render script is injected, the DAG completes the retry loop and marks the cut as aborted within 3 attempts, without crashing the orchestrator or corrupting the SQLite checkpoint.
- **SC-003**: The `coder_node` and `execution_node` each complete their synchronous execution within 500ms of wall-clock overhead (excluding LLM API latency and subprocess rendering time).
- **SC-004**: The entire test suite (including existing 202 tests) continues to pass at 100% with zero regressions after the feature is implemented.
- **SC-005**: The `render_attempts` counter and `render_aborted` flag are correctly recovered from the SQLite checkpoint after a simulated container crash mid-retry-loop.
