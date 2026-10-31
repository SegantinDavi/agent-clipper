# Data Model: Dynamic Scene Scripting via Constrained Decoding (016)

**Branch**: `016-dynamic-scene-scripting` | **Date**: 2026-10-31

---

## Entities

### 1. `Scene` (Pydantic BaseModel)

**Location**: `src/clipper/core/schemas.py`  
**Purpose**: Represents an atomic visual scene of 2–4 seconds of speech within a video cut, enriched with visual metaphors and animation triggers for downstream automated and human video editing.

```python
from pydantic import BaseModel, Field

class Scene(BaseModel):
    start_word: str = Field(
        min_length=1,
        description="Palavra exata de início do segmento da cena na transcrição.",
    )
    end_word: str = Field(
        min_length=1,
        description="Palavra exata de término do segmento da cena na transcrição.",
    )
    visual_metaphor: str = Field(
        min_length=1,
        description="Metáfora visual, imagem conceitual ou representação gráfica de apoio.",
    )
    animation_trigger: str = Field(
        min_length=1,
        description="Gatilho de animação, corte ou movimento de câmera recomendado (ex: zoom_in, impact, cut_transition).",
    )
```

| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `start_word` | `str` | Yes | `min_length=1` | Exact starting word of the spoken segment |
| `end_word` | `str` | Yes | `min_length=1` | Exact ending word of the spoken segment |
| `visual_metaphor` | `str` | Yes | `min_length=1` | Conceptual visual metaphor/b-roll idea |
| `animation_trigger` | `str` | Yes | `min_length=1` | Dynamic camera/motion/transition trigger |

**Validation Rules**:
- Must not be empty strings. An empty string raises `pydantic.ValidationError` (`string_too_short`).
- Any string value is accepted for `animation_trigger` and `visual_metaphor` (open vocabulary for creative prompting).

---

### 2. `CorteVideo` (Pydantic BaseModel) — extended

**Location**: `src/clipper/core/schemas.py`  
**Purpose**: Represents an approved video cut candidate for vertical video formats (Shorts/TikTok/Reels). Extended to contain a sequential list of `Scene` objects.

```python
class CorteVideo(BaseModel):
    title: str = Field(
        description="O título curado do corte para viralização.",
    )
    description: str = Field(
        default="",
        description="Resumo factual do tema do corte em uma ou duas frases.",
    )
    start_time: float = Field(
        description="O tempo de início do corte em segundos.",
    )
    end_time: float = Field(
        description="O tempo de término do corte em segundos.",
    )
    scenes: list[Scene] = Field(
        default_factory=list,
        min_length=1,
        description="Lista ordenada de cenas lógicas de 2 a 4 segundos com metáforas e gatilhos de animação.",
    )
```

| Field | Type | Default | Constraints | Description |
|---|---|---|---|---|
| `title` | `str` | required | None | Curated viral short title |
| `description` | `str` | `""` | None | Factual summary |
| `start_time` | `float` | required | `start_time >= 0` | Cut start timestamp in seconds |
| `end_time` | `float` | required | `end_time > start_time` | Cut end timestamp in seconds |
| `scenes` | `list[Scene]` | `[]` (factory) | `min_length=1` on explicit input | Sequential list of logical scenes |

**Validation Rules**:
- When parsed from LLM JSON or explicit dictionary containing `"scenes": []`, raises `pydantic.ValidationError` (`too_short`).
- When instantiated in legacy test fixtures without the `scenes` argument, defaults to `[]` to preserve backward compatibility across existing test suites.
- In `extractor_node`, an explicit guard asserts `if not corte.scenes: raise ValueError(...)` ensuring fail-fast execution before outputting to state.
- In `extractor_node`, scene duration is evaluated against `word_timestamps` inside `[corte.start_time, corte.end_time]`. If duration exceeds 4.0s, a non-blocking `logger.warning` is emitted. If `word_timestamps` is empty or absent from state, duration evaluation is skipped gracefully without raising an exception.
- The JSON Schema contract for structured decoding is generated via `openai.pydantic_function_tool(CortesResponse)["function"]["parameters"]` (`additionalProperties: false`, all properties `required`).

---

### 3. `CortesResponse` (Pydantic BaseModel)

**Location**: `src/clipper/core/schemas.py`  
**Purpose**: Top-level response container for Instructor constrained decoding.

```python
class CortesResponse(BaseModel):
    cortes: list[CorteVideo] = Field(
        description="Lista contendo os melhores cortes selecionados para Shorts.",
        min_length=0,
    )
```

---

### 4. `ReviewManifest` (Pydantic BaseModel)

**Location**: `src/clipper/review/review.py`  
**Purpose**: Manifest saved as `review.json` in the review directory.

```python
class ReviewManifest(BaseModel):
    cuts: list[CorteVideo]
    pause_plans: list[PausePlan] = Field(default_factory=list)
```

**Persistence**:
- Serialized to `review.json` via `manifest.model_dump_json()`.
- Automatically includes `scenes` array for each cut.
- Deserialized via `ReviewManifest.model_validate_json(...)` in the review HTTP server.

---

### 5. `VideoState` (TypedDict) — Channel `cortes_finais`

**Location**: `src/clipper/core/orchestrator.py`  
**Storage**: SQLite database `/app/output/estado.db` managed by LangGraph `SqliteSaver`.

**Payload Schema**:
```python
cortes_finais: list[dict] = [
    {
        "title": "Seis meses construindo algo sem demanda",
        "description": "O participante relata o fracasso de um produto...",
        "start_time": 120.0,
        "end_time": 175.0,
        "scenes": [
            {
                "start_word": "O",
                "end_word": "problema",
                "visual_metaphor": "alvo com flecha errada",
                "animation_trigger": "zoom_in",
            },
            {
                "start_word": "Passamos",
                "end_word": "prioridade",
                "visual_metaphor": "calendário folheando",
                "animation_trigger": "cut_transition",
            },
        ],
    }
]
```

---

## Data Flow & Lifecycle

```
[thinker_node]
     │
     ▼ produces `raciocinio_bruto` (unconstrained markdown/text)
[extractor_node]
     │
     ├── Calls LLM via Instructor (mode=JSON_SCHEMA, response_model=CortesResponse)
     ├── Enforces EXTRACTOR_SYSTEM_PROMPT_TEMPLATE + EXTRACTOR_FEW_SHOT_EXAMPLES
     ├── Validates Scene and CorteVideo schemas via Pydantic
     ├── Asserts non-empty scenes (fail-fast ValueError)
     ├── Evaluates scene durations (> 4s emits editorial warning)
     ▼ returns `cortes_finais` ([cut.model_dump() for cut in cortes])
[LangGraph Checkpoint / SqliteSaver]
     │
     ▼ persists `cortes_finais` with `scenes` to SQLite BLOB
[preview_node] & [approval_node]
     │
     ├── Writes `review.json` via ReviewManifest (containing scenes)
     ├── Renders HTML review page with structured scene breakdown
     ▼ Human approves / rejects cuts
[editor_node]
     │
     └── Reads approved cuts with intact `scenes` for final rendering work-order
```
