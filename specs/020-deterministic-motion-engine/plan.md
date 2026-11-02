# Implementation Plan: Restauração do Motor Determinístico com Motion Design Nativo

**Branch**: `020-deterministic-motion-engine` | **Date**: 2026-11-02 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/020-deterministic-motion-engine/spec.md`

---

## Summary

Restaurar a arquitetura determinística de renderização de vídeo no pipeline agent-clipper através da reintegração do nó `editor_node` conectado ao módulo `cut_and_format_video` (`src/clipper/video/editor.py`), eliminando o ciclo estocástico de geração de código por LLM (`coder_node` + `execution_node` + auto-cura). Introduzir o motor nativo de motion design (`src/clipper/video/motion_engine.py`) para traduzir as cenas (`Scene`) e gatilhos de animação (`impact`, `zoom_in`, `cut_transition`) em efeitos visuais determinísticos de enquadramento e escala via MoviePy 1.0.3 e Pillow, garantindo 100% de integridade e sincronismo nas legendas e preservando as garantias de liberação de memória RAM e VRAM.

---

## Technical Context

**Language/Version**: Python 3.12+ (compatível com 3.12 – 3.14)  
**Primary Dependencies**: `moviepy==1.0.3` (restrito a métodos v1.0.3), `pydantic`, `langgraph`, `Pillow`, `numpy`, `fonts-liberation`  
**Storage**: SQLite via `SqliteSaver` (`/app/output/estado.db`), `pipeline.log`, `decision.json` em `/app/output/reviews/<id>/`  
**Testing**: `unittest` (`PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"`)  
**Target Platform**: Linux (Debian-slim Docker sobre WSL2 Ubuntu, 8 GB RAM / 8 GB Swap, GPU RTX 3060 12 GB VRAM)  
**Project Type**: Single project (`src/clipper/`)  
**Performance Goals**: Tempo de renderização < 120s por corte; encerramento < 5s para decisões vazias; consumo de pico de RAM < 2 GB por corte; overhead de flush de VRAM < 50ms  
**Constraints**: Sem novas dependências pesadas; dimensões estritamente pares no crop/resize (9:16); métodos MoviePy v1.0.3 apenas; sem truncamento de palavras (`[:100]`); nós LangGraph estritamente síncronos (`def`); desalocação garantida de memória via `.close()`, `del`, `gc.collect()` e `release_cuda_memory()`.  
**Scale/Scope**: Episódios longos de podcast fatiados em chunks, resultando em 1 a 10 cortes finais aprovados por episódio.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
|---|---|---|
| No new heavy dependencies | ✅ PASS | Utiliza apenas a stack existente (`moviepy==1.0.3`, `Pillow`, `pydantic`, `langgraph`). |
| Memory budget respected | ✅ PASS | Pico de RAM < 2 GB; desalocação explícita de clips; `release_cuda_memory()` acionado no bloco `finally:` de cada corte. |
| Deterministic Video Rendering | ✅ PASS | Substitui a geração ad-hoc de scripts por LLM por renderização determinística em Python testado. |
| Full Subtitle Integrity | ✅ PASS | 100% dos `word_timestamps` do corte são enviados ao gerador de legendas, sem truncamento `[:100]`. |
| Native Motion Design | ✅ PASS | Mapeamento determinístico de `scenes` para efeitos visuais (`impact`, `zoom_in`, `cut_transition`). |
| Dimensões Pares (H.264) | ✅ PASS | Crop e resize forçam estritamente paridade dimensional em 9:16 (ex.: 1080x1920). |
| Fontes Liberation | ✅ PASS | Tipografia estritamente Liberation Sans Bold via Pillow, sem fontes do Windows. |
| Human-in-the-Loop Nativo | ✅ PASS | `editor_node` valida `decision.json`, garante 0% de renderização para rejeitados e saída rápida para vazios. |
| Strict Synchronous Nodes | ✅ PASS | `editor_node` é uma função síncrona convencional (`def`). |
| No external telemetry | ✅ PASS | Observabilidade via logs físicos em `pipeline.log`. |

**Post-design re-check**: Todos os portões foram validados com sucesso. O design respeita 100% das diretrizes do `AGENTS.md` e `GEMINI.md`.

---

## Project Structure

### Documentation (this feature)

```text
specs/020-deterministic-motion-engine/
├── plan.md              # Este plano de implementação
├── research.md          # Diagnóstico técnico e decisões arquiteturais
├── data-model.md        # Entidades, SceneInterval, MotionPlan e VideoState
├── contracts/
│   └── deterministic_editor_contract.md # Contratos de interface do editor e motion engine
├── quickstart.md        # Guia de execução e testes
└── tasks.md             # Tarefas detalhadas (geradas via speckit.tasks)
```

### Source Code

```text
src/clipper/
├── core/
│   ├── orchestrator.py  # Restaura editor_node, remove coder_node do fluxo principal, ajusta DAG
│   └── schemas.py       # Schemas CorteVideo, Scene, VideoState
├── video/
│   ├── editor.py        # cut_and_format_video integrado com legendas integrais e motion design
│   ├── motion_engine.py # Motor determinístico de cálculo de intervalos e efeitos visuais
│   └── pause_editing.py # Encurtamento de pausas e remapeamento de legendas
└── runtime/
    └── cuda_runtime.py  # release_cuda_memory() para limpeza profunda de VRAM

tests/
├── test_motion_engine.py # Testes unitários do motor de motion design
├── test_editor.py        # Testes de integração da renderização determinística
├── test_orchestrator.py  # Testes do fluxo DAG e nós síncronos
└── test_review_delivery.py # Testes de HITL e seletividade de cortes
```

---

## Complexity Tracking

*Nenhuma violação constitucional identificada.*
