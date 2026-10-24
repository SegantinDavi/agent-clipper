# Phase 0 Research: Few-Shot Prompting no Extractor Node

**Feature**: `001-few-shot-extractor`  
**Date**: 2026-10-23  
**Status**: Completed  

---

## 1. Multi-Turn Messages vs System Prompt String Concatenation

### Context & Problem
Under high contextual load (transcripts > 3000 tokens from 60+ min podcasts), the Qwen2.5:14b model suffers from attention degradation and "forgets" the required Pydantic schema structure expected by `instructor`. This causes JSON parsing failures and pipeline crashes.

### Alternatives Evaluated

| Approach | Pros | Cons | Decision |
|---|---|---|---|
| **Option A**: String Concatenation in `system_prompt` | Simplest change; only modifies a single string variable. | Qwen2.5 often treats system prompt guidelines as weak instructions under heavy context, ignoring schema demonstrations. | **Rejected** |
| **Option B**: Multi-Turn Messages (`user` / `assistant` pairs) | Triggers In-Context Learning (ICL) pattern matching; primes the probability distribution to output exact JSON structure; conforms to OpenAI chat specification. | Slightly larger payload structure (`list[dict]` instead of `str`). | **Selected** |
| **Option C**: Regex-based post-processing cleanup | Can salvage poorly formatted text. | Explicitly prohibited by project constitution (`AGENTS.md` Rule 5). Introduces fragile heuristics. | **Rejected (Prohibited)** |

### Rationale & Details
Passing few-shot examples as explicit conversational turns (`role="user"` with mock transcript/reasoning, followed by `role="assistant"` with serialized JSON array) grounds the model before the actual payload arrives:
```python
messages = (
    [{"role": "system", "content": EXTRACTOR_SYSTEM_PROMPT_TEMPLATE}]
    + EXTRACTOR_FEW_SHOT_EXAMPLES
    + [{"role": "user", "content": user_prompt}]
)
```
Instructor in `mode=instructor.Mode.JSON` transparently passes all conversation history to Ollama's `/v1/chat/completions` endpoint and intercepts only the final assistant response for validation against `response_model=list[CorteVideo]`.

---

## 2. Token Budget & Hardware Impact

### WSL2 8GB RAM & RTX 3060 12GB VRAM Constraints
- **Context Window**: Qwen2.5:14b on Ollama has a standard context window of 8,192 to 32,768 tokens.
- **Few-Shot Overhead**:
  - Mock User message: ~150-180 tokens (compact transcript snippet + mock retention reasoning).
  - Mock Assistant message: ~50-70 tokens (JSON array with 1-2 `CorteVideo` items).
  - Total overhead: ~200-250 tokens (~1.5% of an 8k context window).
- **VRAM / Compute Impact**: The additional ~250 tokens in the prompt evaluation phase add negligible latency (< 5% overhead) and zero incremental VRAM allocation, fully respecting `AGENTS.md` Rule 1.

---

## 3. Architecture & Modularity of `prompts.py`

### Decision
Extract all prompt strings out of `orchestrator.py` into a new root-level module `prompts.py`.

### Exports Defined
1. `THINKER_SYSTEM_PROMPT: str`: System prompt for Node 4 (Thinker / Pensador), focused on viral strategy, pattern interruption, and retention hooks.
2. `EXTRACTOR_SYSTEM_PROMPT_TEMPLATE: str`: System prompt for Node 5 (Extractor / Extrator), focused on time constraints (15-60s), exact timestamp alignment, and viral titles.
3. `EXTRACTOR_FEW_SHOT_EXAMPLES: list[dict[str, str]]`: Structured turn-based examples demonstrating input format and valid JSON output.

### Dependencies
`prompts.py` has **zero** third-party or internal module dependencies, guaranteeing no circular imports and 100% isolated testability.

---

## 4. Parameter Stability

In compliance with spec requirement `FR-005`:
- `OLLAMA_BASE_URL`: remains `"http://localhost:11434/v1"` (or configured from environment).
- `MODEL_NAME`: remains `"qwen2.5:14b"`.
- `temperature`: remains `0.1` on `extractor_node` (deterministic structured decoding) and `0.7` on `thinker_node` (creative chain-of-thought analysis).
