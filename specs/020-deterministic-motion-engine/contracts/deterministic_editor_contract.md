# Interface Contract: Deterministic Editor & Motion Design Engine

**Branch**: `020-deterministic-motion-engine` | **Date**: 2026-11-02 | **Spec**: [spec.md](../spec.md)

---

## 1. Module: `clipper.video.motion_engine`

### Contract 1: `build_motion_plan(corte: CorteVideo, words: list[dict], duration: float) -> MotionPlan`

#### Description
Mapeia deterministicamente as cenas (`Scene`) de um corte para uma sequência contígua de `SceneInterval` com timestamps exatos, gatilhos de animação e fatores de escala visual.

#### Signature
```python
def build_motion_plan(corte: CorteVideo, words: list[dict], duration: float) -> MotionPlan: ...
```

#### Preconditions
1. `corte` deve ser uma instância válida de `CorteVideo` ou dicionário contendo `start_time`, `end_time` e opcionalmente `scenes`.
2. `words` deve ser uma lista de dicionários contendo `word`, `start` e `end`.
3. `duration` deve ser um número float estritamente positivo representando a duração do corte em segundos.

#### Postconditions
1. Retorna uma instância de `MotionPlan`.
2. O plano cobre 100% da duração do corte: `intervals[0].rel_start == 0.0` e `intervals[-1].rel_end == duration`.
3. Não há gaps nem sobreposições temporais entre cenas adjacentes.
4. Cada `SceneInterval` possui um `animation_trigger` válido (`"impact"`, `"zoom_in"`, `"slow_zoom"`, `"cut_transition"`, `"whip_pan"` ou `"standard"`).
5. Se `corte.scenes` for vazio, retorna um `MotionPlan` com um único intervalo cobrindo toda a duração com enquadramento padrão.

---

### Contract 2: `apply_motion_design(clip: VideoClip, motion_plan: MotionPlan, visual_identity: dict | None = None) -> VideoClip`

#### Description
Aplica os efeitos visuais de escala, punch-in, aproximação e transição de enquadramento ao clipe de vídeo base recortado em 9:16, de acordo com o `MotionPlan`.

#### Signature
```python
def apply_motion_design(clip: VideoClip, motion_plan: MotionPlan, visual_identity: dict | None = None) -> VideoClip: ...
```

#### Preconditions
1. `clip` deve ser um `VideoClip` do MoviePy 1.0.3 já recortado ou preparado para o aspecto vertical 9:16.
2. `motion_plan` deve ser uma instância válida de `MotionPlan`.

#### Postconditions
1. Retorna um `VideoClip` composto com os efeitos aplicados e mesma duração do clipe de entrada.
2. Todas as transformações mantêm dimensões estritamente pares.
3. Se `motion_plan` contiver apenas uma cena padrão, o clipe é retornado sem operações redundantes de concatenação.
4. Utiliza concatenação via `method="chain"` para evitar acúmulo de frames na RAM.

---

## 2. Module: `clipper.video.editor`

### Contract 3: `cut_and_format_video(...) -> list[str]`

#### Description
Renderiza deterministicamente os cortes aprovados em vídeos verticais 9:16 com legendas completas e motion design nativo.

#### Signature
```python
def cut_and_format_video(
    video_path: str,
    cortes_validados: list[CorteVideo],
    word_timestamps: list[dict],
    output_dir: str,
    pause_plans: list[PausePlan] | None = None,
    visual_identity: dict | None = None,
) -> list[str]: ...
```

#### Preconditions
1. `video_path` deve existir no disco.
2. `cortes_validados` deve conter apenas cortes aprovados.
3. `word_timestamps` deve conter todos os timestamps de palavras do vídeo (sem truncamento).
4. `output_dir` deve ser um diretório gravável.

#### Postconditions
1. Retorna a lista de caminhos absolutos dos arquivos MP4 renderizados.
2. Gera cada vídeo com resolução 9:16 e dimensões pares.
3. As legendas cobrem todas as palavras do corte via Pillow.
4. Aplica os efeitos de `MotionPlan` baseados nas cenas de cada corte.
5. Fecha todos os recursos com `.close()`, `del` e `gc.collect()`.

---

## 3. Module: `clipper.core.orchestrator`

### Contract 4: `editor_node(state: VideoState) -> dict`

#### Description
Nó síncrono do LangGraph que coordena a renderização determinística dos cortes aprovados, validando a aprovação, garantindo 0% de renderização para cortes rejeitados e liberando cache de VRAM incondicionalmente no final de cada corte.

#### Signature
```python
def editor_node(state: VideoState) -> dict: ...
```

#### Preconditions
1. `state.get("approval_complete") is True`.
2. Se `review_directory` existir, `decision.json` deve estar presente e válido.

#### Postconditions
1. Função estritamente síncrona (`inspect.iscoroutinefunction(editor_node) is False`).
2. Se nenhum corte for aprovado, registra log e retorna `{"rendered_video_paths": []}` imediatamente.
3. Filtra estritamente os cortes em `approved_cut_ids`, emitindo log INFO para cortes descartados.
4. Executa `cut_and_format_video` para os cortes aprovados.
5. Dispara `release_cuda_memory(cut_id=...)` em bloco `finally:` de cada corte no perfil CUDA.
6. Retorna `{"rendered_video_paths": arquivos_gerados}`.
