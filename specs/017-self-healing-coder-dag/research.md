# Research: Self-Healing Coder DAG (017)

**Branch**: `017-self-healing-coder-dag` | **Date**: 2026-10-31

---

## 1. How should `coder_node` prompt the LLM and extract the render script without regex or formatting hallucinations?

**Decision**:
Use Constrained Decoding via `instructor.from_openai(raw_client, mode=instructor.Mode.JSON_SCHEMA)` with a dedicated Pydantic model `RenderScriptPayload(BaseModel)` containing a `script_code: str = Field(min_length=1, description="...")` field, enforced with strict JSON Schema.

**Rationale**:
- **Compliance with AGENTS.md Rule 5**: Manual regex (`re.search`) or manual `json.loads` to strip markdown tags (such as ` ```python `) from LLM completions is strictly forbidden in this repository. Constrained Decoding guarantees that the LLM response is returned directly as a typed Python object where `payload.script_code` contains the exact script string.
- **Provider Neutrality (Rule 4 & 11)**: The same `instructor` client wrapping `create_llm_client()` operates identically with both Ollama local (`qwen2.5:14b`) and Gemini API (`gemini-2.5-flash`), with no second LLM loaded.
- **Fail-Fast Schema Validation**: If the LLM generates an empty string or malformed response, Pydantic raises a `ValidationError` immediately, which `coder_node` captures to record in `render_error` and trigger self-healing.
- **Deterministic File Generation (FR-003)**: `coder_node` extracts `payload.script_code`, writes it to `/app/output/<cut_id>/render_script.py` with UTF-8 encoding, and updates `VideoState["render_script_path"]`.

**Alternatives considered**:
- Free-form completion with regex fence stripping (`re.sub(r"^```python", ...)`): Rejected — strictly prohibited by AGENTS.md Rule 5.
- Executing LLM output directly in-memory via `eval()` or `exec()`: Rejected — violates process isolation, risks polluting the orchestrator process, and prevents clean subprocess resource cleanup.

---

## 2. How should `execution_node` run the render script safely in isolation?

**Decision**:
Execute the generated `render_script.py` in an isolated subprocess using `subprocess.run([sys.executable, render_script_path], capture_output=True, text=True, timeout=RENDER_TIMEOUT_SECONDS)`.

**Rationale**:
- **Process Isolation (FR-004)**: Running the script in a dedicated Python subprocess ensures that any fatal segmentation fault, OOM error, MoviePy `BrokenPipeError`, or syntax failure terminates only the subprocess and cannot crash the orchestrator DAG.
- **Resource Cleanup**: Subprocess termination releases all memory and open file descriptors cleanly back to the operating system, respecting WSL2's 8 GB RAM boundary.
- **Timeout Protection**: A configurable timeout (`RENDER_TIMEOUT_SECONDS`, default `300` seconds) prevents rogue or deadlocked rendering loops from hanging the pipeline. If `subprocess.TimeoutExpired` is raised, `execution_node` kills the child process and captures a descriptive timeout message in `render_error`.
- **Capture Outcomes (FR-005)**: Subprocess exit code is stored in `VideoState["render_exit_code"]`, and stdout/stderr are captured. If exit code is `0`, `render_error` is cleared to `""`. If non-zero, `render_error` contains the full `stderr` output.

**Alternatives considered**:
- Multi-threading / `multiprocessing` worker within orchestrator: Rejected — does not provide complete crash isolation from C-level library failures (e.g. FFmpeg or CTranslate2) and introduces complex IPC serialization.
- Docker-in-Docker isolation: Rejected — unnecessary complexity and overhead for WSL2/Docker environments; a standard child subprocess under the same virtualenv is fully isolated for script execution.

---

## 3. How should `stderr` be truncated and fed back into `coder_node` during self-healing retries?

**Decision**:
Truncate `stderr` to `RENDER_ERROR_MAX_CHARS` (default `2000` characters) taking the tail of the error stream, and feed it into `coder_node` using `CODER_RETRY_PROMPT_TEMPLATE`.

**Rationale**:
- **Token Budget Protection**: Raw FFmpeg or Python tracebacks can be verbose (thousands of lines of frame metadata). Truncating to 2,000 characters prevents context window overflow and saves tokens on both Ollama and Gemini backends.
- **Tail Selection**: In Python and FFmpeg, the root cause exception and final traceback frame always appear at the end (tail) of `stderr`. Taking `stderr[-RENDER_ERROR_MAX_CHARS:]` preserves the most actionable diagnostic information for the LLM.
- **Prompt Structure (FR-009)**: On retries (`render_attempts > 0` and `render_error` non-empty), `coder_node` constructs a user message including the previous script code and the captured `render_error`, instructing the model to diagnose the failure and write a corrected version.

**Alternatives considered**:
- Sending full untruncated stderr: Rejected — risks exploding context window tokens and triggering OOM or API rate limit errors on verbose FFmpeg failures.
- Summarizing stderr with an extra LLM call: Rejected — adds latency, costs extra tokens, and violates single-model simplicity.

---

## 4. How should the LangGraph DAG conditional edges and retry counter be structured?

**Decision**:
Wire conditional edges from `execution_node` using a deterministic router function `route_execution_outcome(state)` that evaluates `render_exit_code` and `render_attempts`.

**Topology**:
```
START -> download -> fatiamento -> style -> transcricao -> pensador -> extrator -> preview -> approval -> coder -> execution
                                                                                                              │
                                                                                 ┌────────────────────────────┴────────────────────────────┐
                                                                                 ▼                                                         ▼
                                                                     [exit != 0 & attempts < 3]                               [exit == 0 OR attempts >= 3]
                                                                                 │                                                         │
                                                                                 ▼                                                         │
                                                                               coder (retry)                                               ▼
                                                                                                                                [exit == 0] -> complete (END / next cut)
                                                                                                                                [attempts >= 3] -> abort -> END
```

**Routing Rules**:
1. If `render_exit_code == 0`: Cut rendering succeeded. Proceed to downstream completion (`END` or next approved cut).
2. If `render_exit_code != 0` and `render_attempts < 3`: Retry loop. Route back to `coder_node`.
3. If `render_exit_code != 0` and `render_attempts >= 3`: Retries exhausted. Route to `abort_node` which sets `VideoState["render_aborted"] = True`, logs the abortion, and ends or skips to the next cut.

**Rationale**:
- **LangGraph Native State & Synchronous Contract (FR-006, FR-010)**: All nodes remain standard synchronous functions (`def`), invoked sequentially via `app.invoke`. The conditional edge inspects state dictionary values without side effects.
- **Deterministic Termination**: The counter `render_attempts` is strictly incremented by `execution_node` on every run, guaranteeing that the loop terminates after at most 3 attempts.

**Alternatives considered**:
- While-loop inside a single node: Rejected — violates LangGraph architecture, prevents step-by-step SQLite checkpointing per retry attempt, and makes debugging impossible.
- Dynamic Subgraph recursion: Rejected — unnecessary complexity; flat conditional edges in `StateGraph` are idiomatic and fully supported by `SqliteSaver`.

---

## 5. How should `VideoState` fields be persisted across SQLite checkpoints for crash recovery?

**Decision**:
Add primitive fields to `VideoState` in `src/clipper/core/orchestrator.py`:
- `render_script_path: str` (default `""`)
- `render_attempts: int` (default `0`)
- `render_error: str` (default `""`)
- `render_exit_code: int` (default `0`)
- `render_aborted: bool` (default `False`)
- `current_cut_index: int` (default `0`)

**Rationale**:
- **SQLite Native Serialization (FR-012, SC-005)**: All fields are basic Python types (`str`, `int`, `bool`) that serialize directly to JSON-compatible structures in `SqliteSaver` (`estado.db`).
- **Crash Recovery**: If the Docker container or host crashes during attempt 2, the checkpointer restores `render_attempts=2` and the last `render_error`. The resumed invocation continues from the checkpoint without repeating downloads or transcription.
- **Thread ID Isolation**: Reuses `checkpoint_thread_id(video_id)` so checkpoints remain strictly isolated by video and configuration scope.

**Alternatives considered**:
- Storing execution state in external JSON files on disk: Rejected — causes split-brain state hazards with LangGraph's checkpointer.

---

## 6. What libraries and constraints must the LLM follow when authoring `render_script.py`?

**Decision**:
The system prompt `CODER_SYSTEM_PROMPT` explicitly restricts the generated script to:
- `moviepy.editor` (`VideoFileClip`, `ImageClip`, `CompositeVideoClip`, `concatenate_videoclips`) fixed to `moviepy==1.0.3` syntax.
- `PIL` (`Image`, `ImageDraw`, `ImageFont`) for caption rendering to avoid ImageMagick policy blocks.
- `Liberation-Sans-Bold` as the mandatory font (from `fonts-liberation`).
- Even pixel dimensions for H.264 video exports (`width % 2 == 0` and `height % 2 == 0`).
- FFmpeg output parameters: `ffmpeg_params=["-pix_fmt", "yuv420p", "-profile:v", "main"]`.
- Scene transitions and animation triggers matching the approved `Scene` specifications (from Feature 016).
- Saving the final MP4 to a deterministic output path provided in the cut specification.

**Rationale**:
- Avoids LLM hallucinations of non-existent MoviePy 2.x APIs (e.g. `with_position`, `resized`).
- Adheres 100% to AGENTS.md Rule 6 (Manipulação de Vídeo) and Rule 7 (Containerização).
