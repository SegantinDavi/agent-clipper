# Implementation Plan: Inserts Animados de Motion Design (Pipeline Híbrido)

**Branch**: `021-animated-motion-inserts` | **Date**: 2026-11-02 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/021-animated-motion-inserts/spec.md`

---

## Summary

Implementar a arquitetura híbrida de **inserts animados de motion design** para os cortes verticais do agent-clipper. A funcionalidade combina:
1. Um catálogo estruturado de assets locais em `/assets` (animações WebM VP9 com canal alfa, ícones PNG/SVG e efeitos sonoros WAV) regido por `assets/manifest.json`.
2. Um resolvedor semântico (`AssetResolver`) em `src/clipper/video/asset_resolver.py` que traduz as metáforas visuais das cenas para assets do catálogo ou gera cards procedurais dinâmicos com física elástica em fallback.
3. Extensão do motor de motion design (`src/clipper/video/motion_engine.py`) com curvas de interpolação matemática (*ease-out-back* pop-in, micro-flutuação senoidal e fade-out), sobreposição transparente com respeito à zona segura das legendas e mixagem não-destrutiva de SFX no áudio principal.
4. Uma ferramenta auxiliar de linha de comando (`src/clipper/tools/asset_tool.py`) para validar canal alfa, paridade dimensional H.264 e sincronizar stubs no `manifest.json`.
5. Preservação estrita das garantias de memória RAM (< 2 GB) e VRAM (flush incondicional via `release_cuda_memory()`).

---

## Technical Context

**Language/Version**: Python 3.12+ (compatível com 3.12 – 3.14)  
**Primary Dependencies**: `moviepy==1.0.3` (restrito a métodos v1.0.3), `Pillow`, `numpy`, `pydantic`, `langgraph`, `fonts-liberation`, `ffprobe` (via standard library / subprocess)  
**Storage**: Diretório local `/assets` com `manifest.json`, SQLite via `SqliteSaver` (`/app/output/estado.db`), `pipeline.log`  
**Testing**: `unittest` (`PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"`)  
**Target Platform**: Linux (Debian-slim Docker sobre WSL2 Ubuntu, 8 GB RAM / 8 GB Swap, GPU RTX 3060 12 GB VRAM)  
**Project Type**: Single project (`src/clipper/`)  
**Performance Goals**: Resolução semântica de asset < 10ms por cena; tempo adicional de renderização de inserts e áudio < 25%; auditoria do catálogo via CLI < 5s para 50 arquivos; pico de RAM < 2 GB.  
**Constraints**: Dimensões estritamente pares no crop, resize e overlays (H.264); métodos MoviePy v1.0.3 apenas (sem métodos v2.x); zona segura superior/média (y <= 72%), sem colisão com legendas (y >= 75%); fechamento explícito de clips (`.close()`, `del`, `gc.collect()`); flush de VRAM em `finally:`; sem dependências pesadas de IA generativa em tempo de renderização.  
**Scale/Scope**: Catálogo inicial com ~15 a 25 assets e efeitos sonoros, suportando de 1 a 10 cortes aprovados por execução de podcast.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
|---|---|---|
| No new heavy dependencies | ✅ PASS | Utiliza apenas a stack existente (`moviepy==1.0.3`, `Pillow`, `numpy`, `pydantic`). Sem Node.js, sem Chromium, sem novos modelos pesados de IA. |
| Memory budget respected | ✅ PASS | Pico de RAM < 2 GB por corte; fechamento determinístico de clips intermediários; flush incondicional de VRAM via `release_cuda_memory()` em bloco `finally:`. |
| Deterministic Video Rendering | ✅ PASS | 100% determinístico e síncrono em Python via `editor_node` e `motion_engine.py`. |
| Full Subtitle Integrity | ✅ PASS | Inserts respeitam a zona segura (y <= 72%) e não sobrepõem nem truncam as legendas transcritas. |
| Native Motion Design & Easing | ✅ PASS | Curvas matemáticas puras (*ease-out-back*, flutuação e fade) e WebM com canal alfa nativo. |
| Dimensões Pares (H.264) | ✅ PASS | Todo clipe e overlay gerado força largura e altura pares (`w % 2 == 0` e `h % 2 == 0`). |
| Fontes Liberation | ✅ PASS | Textos e badges de inserts utilizam tipografia Liberation Sans Bold via Pillow. |
| Strict Synchronous Nodes | ✅ PASS | Integração no grafo LangGraph via funções síncronas convencionais (`def`). |
| No external telemetry | ✅ PASS | Diagnósticos e auditorias registrados apenas em `pipeline.log`. |

**Post-design re-check**: Todos os portões foram validados com sucesso. O design respeita 100% das diretrizes do `AGENTS.md` e `GEMINI.md`.

---

## Project Structure

### Documentation (this feature)

```text
specs/021-animated-motion-inserts/
├── plan.md              # Este plano de implementação
├── research.md          # Pesquisa de codecs, formato de manifest, curvas de easing e CLI
├── data-model.md        # Modelos Pydantic (AssetItem, AssetManifest), ResolvedInsert e EasingProfile
├── contracts/
│   └── motion_inserts_contract.md # Contratos de interface do AssetResolver, renderização e CLI
├── quickstart.md        # Guia de execução de testes e uso da CLI
└── checklists/
    └── requirements.md  # Checklist de qualidade da especificação
```

### Source Code (repository root)

```text
assets/                          # Catálogo inicial de assets do projeto
├── manifest.json                # Metadados e indexação semântica de assets
├── animations/                  # Clipes curtos em WebM VP9 com canal alfa (transparência)
│   ├── business/
│   ├── emotions/
│   └── tech/
├── icons/                       # Ícones de alta resolução em PNG/SVG
│   ├── finance/
│   └── general/
└── sfx/                         # Efeitos sonoros curtinhos (.wav)
    ├── pops/
    └── whooshes/

src/clipper/
├── video/
│   ├── asset_resolver.py        # NOVO: Resolvedor semântico de metáforas visuais para assets
│   ├── motion_engine.py         # ATUALIZADO: Curvas de easing, sobreposição WebM e mixagem SFX
│   └── editor.py                # ATUALIZADO: cut_and_format_video integrando inserts e áudio
├── tools/
│   └── asset_tool.py            # NOVO: CLI para validação técnica de assets e sync de manifest
└── core/
    └── schemas.py               # Schemas Pydantic centralizados

tests/
├── test_asset_resolver.py       # NOVO: Testes unitários do AssetResolver e manifest.json
├── test_asset_tool.py           # NOVO: Testes da ferramenta CLI de validação e sincronização
├── test_motion_inserts.py       # NOVO: Testes de composição de overlays alfa, easing e mixagem de SFX
├── test_motion_engine.py        # Testes de regressão do motor de enquadramento por cena
└── test_editor.py               # Testes de integração do editor determinístico
```

---

## Complexity Tracking

*Nenhuma violação constitucional identificada.*
