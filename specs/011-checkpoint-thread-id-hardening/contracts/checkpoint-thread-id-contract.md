# Interface Contract: Checkpoint Thread ID Derivation

**Feature**: `011-checkpoint-thread-id-hardening`  
**Date**: 2026-10-28  
**Scope**: Orchestrator checkpoint thread derivation, parameter normalization, and logging contracts.

---

## 1. Function Contract (`checkpoint_thread_id`)

### Signature
```python
def checkpoint_thread_id(
    video_id: str,
    llm_provider: str | None = None,
    model_name: str | None = None,
    llm_base_url: str | None = None,
    silence_cut_enabled: bool | str | None = None,
    silence_min_pause: float | str | None = None,
) -> str:
    """Derives a deterministic 16-character hexadecimal thread ID for LangGraph checkpointers.
    
    WARNING: Altering this function or its identity formula invalidates all existing
    checkpoints stored in estado.db.
    """
```

### Parameters

| Parameter | Type | Required | Default Fallback | Normalization Rule |
|---|---|---|---|---|
| `video_id` | `str` | Yes | N/A | Stripped of surrounding whitespace; preserved raw without destructive transformation. Empty strings permitted (evaluates to `""`). |
| `llm_provider` | `str \| None` | No | `config.LLM_PROVIDER` | Stripped and converted to lowercase (e.g. `"GEMINI"` -> `"gemini"`). If unresolved, defaults to `"gemini"`. |
| `model_name` | `str \| None` | No | `config.MODEL_NAME` | Stripped of surrounding whitespace. If unresolved, defaults to `""`. |
| `llm_base_url` | `str \| None` | No | `config.LLM_BASE_URL` | Stripped of surrounding whitespace and trailing slashes. If unresolved, defaults to `""`. |
| `silence_cut_enabled` | `bool \| str \| None` | No | `config.SILENCE_CUT_ENABLED` | Parsed as boolean (`True` if in `{True, 1, "1", "true", "yes"}` else `False`). Serialized strictly as `"true"` or `"false"`. |
| `silence_min_pause` | `float \| str \| None` | No | `config.SILENCE_MIN_PAUSE` | Parsed via `float(val)` and serialized strictly as `str(float(val))` (e.g., `0.6` -> `"0.6"`, `1` -> `"1.0"`). Fallback to `"0.6"` if invalid or `None`. |

### Return Value
- **Type**: `str`
- **Specification**: Exactly 16 lowercase hexadecimal characters matching regex `^[0-9a-f]{16}$`.
- **Determinism**: Given identical normalized parameters, the return value is guaranteed to be mathematically identical across all invocations and execution environments.

### Exception Guarantees
- **No-throw guarantee**: The function MUST NOT raise uncaught exceptions on missing, `None`, or malformed optional parameters; it must substitute documented safe fallbacks.

---

## 2. Orchestrator Integration & Logging Contract

### Orchestrator Startup (`orchestrator.py:main`)
```python
video_url = YOUTUBE_URL
...
video_id = extract_video_id(video_url) or video_url
thread_id = checkpoint_thread_id(video_id)
logger.info("Calculated checkpoint thread_id: %s (video_id: %s)", thread_id, video_id)
```

### Logging Requirements
- **Level**: `logging.INFO`
- **Channel**: Root/module logger `clipper.core.orchestrator`
- **Output Destination**: Output file `/app/output/pipeline.log` and standard output stream.
- **Content**: Must output the 16-character `thread_id` to ensure complete post-run traceability.
- **Security**: Must NOT output raw API keys or sensitive credentials into log lines.

---

## 3. Test Coverage Contract

Unit test suite (`tests/test_checkpoint_thread_id.py` and updates to existing suites) must verify:
1. **Determinism**: Calling `checkpoint_thread_id("vid1", "gemini", "gemini-3.6-flash", True, 0.6)` repeatedly produces the exact same 16-character hex hash.
2. **Provider Isolation**: Same video with `ollama` vs `gemini` yields distinct thread IDs.
3. **Model Isolation**: Same video and provider with different models yields distinct thread IDs.
4. **Endpoint Isolation**: Same video, provider, and model with different endpoints (`LLM_BASE_URL`) yields distinct thread IDs.
5. **Silence Flag Isolation**: Same video with `silence_cut_enabled=True` vs `False` yields distinct thread IDs.
6. **Silence Pause Isolation**: Same video with `silence_min_pause=0.6` vs `1.0` yields distinct thread IDs.
7. **Video Isolation**: Different videos (`video-a` vs `video-b`) yield distinct thread IDs.
8. **Optional & None Fallbacks**: Passing `None` for all optional parameters runs without errors and utilizes config defaults.
9. **Format & Length**: Output strictly matches `^[0-9a-f]{16}$` (length 16, lowercase hex).
