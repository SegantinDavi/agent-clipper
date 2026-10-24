# Data Model: Few-Shot Prompting no Extractor Node

**Feature**: `001-few-shot-extractor`  
**Date**: 2026-10-23  
**Status**: Completed  

---

## 1. Entities & Schemas

### 1.1 `CorteVideo` (Core Domain Schema)
Located in `schemas.py`. Represents an individual curated video cut ready for vertical cropping and subtitle rendering.

```python
class CorteVideo(BaseModel):
    title: str = Field(description="O título curado do corte para viralização.")
    start_time: float = Field(description="O tempo de início do corte em segundos.")
    end_time: float = Field(description="O tempo de término do corte em segundos.")
```

#### Validation Rules & Constraints:
- `start_time`: Must be `>= 0.0`. Must align with timestamp segments present in `transcript_grouped`.
- `end_time`: Must be `> start_time`.
- `duration`: `end_time - start_time` must be between `15.0` and `60.0` seconds (optimal YouTube Shorts / TikTok duration).
- `title`: Non-empty string, click-worthy hook title.

---

### 1.2 `ChatMessage` (API Protocol Entity)
Standard message dict structure used by OpenAI/Ollama chat completion API.

```python
class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str
```

#### Usage in Extractor Node:
```python
messages: list[ChatMessage] = [
    {"role": "system", "content": EXTRACTOR_SYSTEM_PROMPT_TEMPLATE},
    *EXTRACTOR_FEW_SHOT_EXAMPLES,
    {"role": "user", "content": user_prompt},
]
```

---

### 1.3 `VideoState` (LangGraph State - Read Only / Immutable in this feature)
Defined in `orchestrator.py`. No modifications to this entity in this feature (`FR-007`).

| Field | Type | Description |
|---|---|---|
| `video_url` | `str` | Target YouTube URL |
| `video_path` | `str` | Local file path to downloaded MP4 |
| `audio_chunks` | `list` | Sliced audio chunk metadata |
| `transcript_grouped` | `str` | Grouped transcript text with timestamps |
| `word_timestamps` | `list` | Word-level timestamps for subtitle synchronization |
| `raciocinio_bruto` | `str` | Unstructured Chain-of-Thought output from `thinker_node` |
| `cortes_finais` | `list[CorteVideo]` | Structured list of cuts produced by `extractor_node` |

---

## 2. Mock Few-Shot Data Specification

The few-shot mock data must represent the exact schema structure in serialized JSON format:

### Mock User Turn
```text
Transcrição do vídeo:
[120.00 - 175.00] Então, o maior erro que empreendedores cometem é não validar o problema antes de construir a solução. Eu mesmo errei assim na minha primeira startup. Gastamos seis meses desenvolvendo um produto que ninguém queria comprar no final. Se eu pudesse voltar no tempo, conversaria com cem clientes em potencial antes de escrever uma linha de código sequer.

Raciocínio Estratégico:
O segmento de 120s a 175s apresenta uma abertura de alto impacto ('o maior erro') seguida de confissão pessoal vulnerável ('gastei seis meses num produto que ninguém queria'). Gera identificação imediata e curiosidade. Duração de 55 segundos é perfeita para o ritmo dos Shorts.

Extraia a lista final dos cortes ideais conforme as instruções.
```

### Mock Assistant Turn (Raw JSON String)
```json
[
  {
    "title": "O Maior Erro dos Empreendedores (Confissão Real)",
    "start_time": 120.0,
    "end_time": 175.0
  }
]
```
