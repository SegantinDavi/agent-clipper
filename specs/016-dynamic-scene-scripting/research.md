# Research: Dynamic Scene Scripting via Constrained Decoding (016)

**Branch**: `016-dynamic-scene-scripting` | **Date**: 2026-10-31

---

## 1. How should `Scene` and `CorteVideo` schemas be defined to satisfy both constrained decoding and backward compatibility?

**Decision**: 
Define `Scene(BaseModel)` with four required fields (`start_word`, `end_word`, `visual_metaphor`, `animation_trigger`) each configured with `Field(min_length=1)`. In `CorteVideo(BaseModel)`, define `scenes: list[Scene] = Field(default_factory=list, min_length=1, description="...")`.

**Rationale**:
- **Constrained Decoding & Strict Schema**: In `openai.pydantic_function_tool(CortesResponse)`, OpenAI/Ollama structured outputs with `strict: True` mandate that all properties appear in `required`. The generator marks `scenes` as required and enforces `"minItems": 1`. When the LLM generates structured output via `instructor`, it is mathematically forced to output a non-empty array of scenes with all four non-empty string attributes.
- **Fail-Fast on Empty Array**: If the LLM produces an empty list `{"scenes": []}`, Pydantic raises a `ValidationError` (`too_short`) immediately.
- **Fail-Fast on Empty Strings**: If `start_word` or `end_word` are empty strings `""`, `Field(min_length=1)` raises a `ValidationError` (`string_too_short`) immediately.
- **Python-level Backward Compatibility**: Existing unit tests across `tests/test_review.py`, `tests/test_pause_editing.py`, `tests/test_speaker_focus.py`, and `tests/test_style_node.py` instantiate `CorteVideo(title=..., start_time=..., end_time=...)` for testing pause planning, visual identity, or speaker focus without specifying scenes. Using `default_factory=list` allows these legacy unit tests to instantiate `CorteVideo` with `scenes=[]` without breaking the 172-test regression suite.
- **Explicit Fail-Fast in Extractor Node**: In `extractor_node`, an explicit check `if not corte.scenes: raise ValueError(...)` guarantees that any extraction without scenes is caught fail-fast before downstream nodes proceed (satisfying FR-009).

**Alternatives considered**:
- `scenes: list[Scene] = Field(..., min_length=1)` without `default_factory`: Rejected — breaks 15+ existing unit test helper fixtures across multiple test files that mock `CorteVideo` without scenes, violating the zero-regression and non-destructive refactoring principles.
- Separate extraction schema (`CorteVideoExtraction`) vs state schema (`CorteVideo`): Rejected — adds unnecessary abstraction layers and schema duplication; violates AGENTS.md Clean Code principles.

---

## 2. How should extractor prompts guide the LLM to segment speech into 2–4s scenes with metaphors and animation triggers?

**Decision**:
Update `EXTRACTOR_SYSTEM_PROMPT_TEMPLATE` with explicit operational rules for scene division, and provide two complete, realistic few-shot demonstrations in `EXTRACTOR_FEW_SHOT_EXAMPLES` showing how transcript phrases map to `Scene` objects with diverse metaphors and dynamic camera/animation triggers.

**Rationale**:
- The Thinker node (`thinker_node`) performs unconstrained strategic reasoning on editorial potential. The Extractor node (`extractor_node`) validates the boundaries and formats the work-order.
- Guiding the Extractor to segment the speech interval into 2–4 second windows ensures high-velocity pacing appropriate for vertical video formats (Shorts/TikTok/Reels).
- Each scene must identify anchor words (`start_word` and `end_word`) matching the actual transcript text, assign a descriptive `visual_metaphor` (concrete visual representations like "balança desequilibrada", "calendário folheando", "gráfico despencando"), and select an `animation_trigger` (such as `zoom_in`, `zoom_out`, `cut_transition`, `whip_pan`, `shake`, `impact`).
- Few-shot examples anchor the LLM's constrained decoding behavior, preventing repetitive or generic values and ensuring consistent adherence to the schema.

**Alternatives considered**:
- Shifting scene scripting to `thinker_node`: Rejected — the Thinker node is responsible for holistic editorial evaluation (hook, progress, value) across the entire video. Adding granular 2–4s word-level scene segmentation to the Thinker prompt would explode reasoning token usage and degrade editorial clip selection quality.
- Adding a third LLM node ("Director" / "Scripter"): Rejected — strictly prohibited by AGENTS.md Rule 4 (Single-Model Cognitive Routing with exactly two LLM nodes: Thinker and Extractor).

---

## 3. How will `scenes` be checkpointed, persisted, and restored across container crashes?

**Decision**:
Rely transparently on LangGraph's `SqliteSaver` checkpointer and standard dictionary serialization (`cut.model_dump()`).

**Rationale**:
- `VideoState.cortes_finais` stores a list of dictionaries (`[cut.model_dump() for cut in cortes]`).
- Because `Scene` contains exclusively primitive strings (`str`), `cut.model_dump()` produces a plain, JSON-serializable Python data structure:
  ```python
  {
      "title": "...",
      "description": "...",
      "start_time": 0.0,
      "end_time": 30.0,
      "scenes": [
          {
              "start_word": "...",
              "end_word": "...",
              "visual_metaphor": "...",
              "animation_trigger": "..."
          }
      ]
  }
  ```
- `SqliteSaver` serializes this dictionary transparently into `/app/output/estado.db`.
- When resuming from a crash, downstream nodes rehydrate cuts using `CorteVideo.model_validate(cut)`, preserving all `scenes` without any disk re-reads or loss of precision.

**Alternatives considered**:
- Storing scenes in a separate database table or auxiliary JSON file: Rejected — violates LangGraph state encapsulation and creates split-brain synchronization hazards during crash recovery.

---

## 4. How should the human review interface (HITL) present scenes to the operator?

**Decision**:
Update `ReviewManifest` and `render_review_page` in `src/clipper/review/review.py` to serialize scenes into `review.json` and render an unobtrusive scene breakdown list inside each cut card.

**Rationale**:
- `ReviewManifest.cuts` already holds `list[CorteVideo]`. When `prepare_review()` executes, `manifest.model_dump_json()` writes `review.json` containing the full `scenes` array for each cut.
- In `render_review_page()`, each card can check `if cut.scenes:` and append a structured `<div class="scenes">` block displaying the scene sequence (`start_word` → `end_word`, metaphor, animation trigger).
- If `cut.scenes` is empty (e.g. in tests or legacy review manifests), the block is omitted, ensuring 100% backward compatibility and zero HTML layout breakage.

**Alternatives considered**:
- Interactive scene editing in the HITL page: Rejected — out of scope for Feature 016; User Story 3 requires visual inspection and full-cut approval/rejection without modifying individual scene parameters.

---

## 5. How should editorial duration thresholds (> 4s per scene) be handled?

**Decision**:
In `extractor_node`, evaluate each scene's implied duration against `word_timestamps` if available (or word count heuristics), and emit a `logger.warning` if a scene exceeds 4.0 seconds, without raising an exception or discarding the cut.

**Rationale**:
- The specification explicitly notes: *"O que acontece quando a duração implícita de uma Scene excede 4 s? O pipeline emite log de aviso editorial, mas não rejeita o corte — o threshold é diretriz editorial, não restrição técnica rígida."*
- Pacing is an editorial guideline; conversational cadence varies naturally, and forcing rigid duration rejections would cause false-positive pipeline failures on legitimate speech pauses or deliberate pacing.

**Alternatives considered**:
- Hard failure on scenes > 4s: Rejected — violates spec edge case requirements.
- Silent ignoring: Rejected — misses the opportunity for editorial observability in `pipeline.log`.
