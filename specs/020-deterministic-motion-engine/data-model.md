# Data Model: Restauração do Motor Determinístico com Motion Design Nativo

**Feature Branch**: `020-deterministic-motion-engine`  
**Date**: 2026-11-02  
**Status**: Completed  
**Spec**: [spec.md](./spec.md)

---

## 1. Entidades Principais

### 1.1 `Scene` (Existente, Schema Pydantic)
Representa uma cena planejada pelo nó Extrator dentro de um corte.

```python
class Scene(BaseModel):
    start_word: str = Field(..., description="Palavra inicial do segmento de fala da cena")
    end_word: str = Field(..., description="Palavra final do segmento de fala da cena")
    visual_metaphor: str = Field(..., description="Metáfora visual sugerida para a cena")
    animation_trigger: str = Field(..., description="Gatilho de animação sugerido (impact, zoom_in, slow_zoom, cut_transition, etc.)")
```

### 1.2 `SceneInterval` (Novo, Modelo Interno de Execução de Motion Design)
Representa o intervalo de tempo resolvido e os parâmetros de transformação visual aplicados pelo motor determinístico a uma cena de corte.

```python
@dataclass
class SceneInterval:
    scene_index: int
    start_time: float      # Timestamp absoluto no vídeo original (segundos)
    end_time: float        # Timestamp absoluto no vídeo original (segundos)
    rel_start: float       # Início relativo ao começo do corte (segundos)
    rel_end: float         # Fim relativo ao começo do corte (segundos)
    duration: float        # Duração da cena (segundos)
    animation_trigger: str # Gatilho de animação normalizado (ex: 'impact', 'zoom_in', 'cut_transition')
    visual_metaphor: str   # Descrição da metáfora visual
    scale_factor: float    # Fator de escala do enquadramento (ex: 1.12 para impact, 1.0 para normal)
    crop_offset_x: float   # Deslocamento horizontal do centro (para alternância de enquadramento)
```

### 1.3 `MotionPlan` (Novo, Plano de Cenas do Corte)
Sequência contígua e não sobreposta de `SceneInterval`s que cobre 100% da duração do corte, garantindo que não existam descontinuidades temporais no vídeo gerado.

```python
@dataclass
class MotionPlan:
    cut_id: int | str
    cut_start: float
    cut_end: float
    duration: float
    intervals: list[SceneInterval]
```

### 1.4 `CorteVideo` (Schema Pydantic Atualizado / Validado)
```python
class CorteVideo(BaseModel):
    id: int | str | None = None
    title: str
    description: str
    start_time: float
    end_time: float
    scenes: list[Scene] = Field(default_factory=list)
```

### 1.5 `VideoState` (LangGraph TypedDict)
Campos do estado trafegados no grafo LangGraph.

| Campo | Tipo | Descrição |
|---|---|---|
| `video_url` | `str` | URL original do YouTube |
| `video_path` | `str` | Caminho do arquivo de vídeo baixado no host |
| `cortes_finais` | `list[CorteVideo]` | Lista de cortes propostos e validados |
| `word_timestamps` | `list[dict]` | 100% dos timestamps de palavras do vídeo completo |
| `approved_cut_ids` | `list[int \| str]` | IDs aprovados na revisão HITL |
| `approval_complete`| `bool` | Flag confirmando conclusão da aprovação |
| `visual_identity` | `dict` | Configurações de estilo e identidade visual |
| `rendered_video_paths` | `list[str]` | Lista de caminhos absolutos dos MP4s finais gerados |

---

## 2. Regras de Validação e Mapeamento

1. **Resolução de Palavras para Timestamps**:
   - Para cada `Scene`, o sistema busca `start_word` e `end_word` dentro do subconjunto de `word_timestamps` do corte.
   - A correspondência deve ser resiliente: remoção de pontuação, minúsculas (`unicodedata.normalize('NFKD', ...)`).
   - Caso `start_word` ou `end_word` não sejam encontradas, o motor calcula timestamps proporcionais baseados na contagem de cenas sobre a duração do corte.
2. **Cobertura Temporal Estrita**:
   - O primeiro `SceneInterval` inicia exatamente em `rel_start = 0.0`.
   - O último `SceneInterval` termina exatamente em `rel_end = duration`.
   - Cenas adjacentes conectam-se continuamente (`intervals[i].rel_end == intervals[i+1].rel_start`), sem gaps ou sobreposições.
3. **Paridade Dimensional Obrigatória**:
   - Toda operação de enquadramento (crop) ou redimensionamento (resize) deve forçar dimensões pares:
     ```python
     if width % 2 != 0:
         width -= 1
     if height % 2 != 0:
         height -= 1
     ```
