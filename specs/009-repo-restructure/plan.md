# Implementation Plan: Modular Domain Repository Restructuring

**Branch**: `009-repo-restructure` | **Date**: 2026-10-27 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/009-repo-restructure/spec.md`

---

## Summary

As the project expanded across 8 previous features, the repository accumulated 31 files directly in the root directory, mixing pipeline nodes, video filters, approval servers, runtime configs, loose drafts, and 9 test suites.

This plan executes a structural reorganization following **Option 1 (Modular by Domain)**:
- Establishing a `src/clipper/` package with 4 cohesive subpackages: `core`, `video`, `review`, and `runtime`.
- Consolidating all test suites into an isolated `tests/` directory.
- Relocating loose draft notes to `docs/`.
- Harmonizing path anchoring in `config.py` to `PROJECT_ROOT`.
- Updating imports across the entire codebase to clean `clipper.<domain>.<module>` paths.
- Adapting `run_pipeline.sh` and `dockerfile` with zero disruption to container workflows, volume persistence, or test passing rates.

---

## Technical Context

**Language/Version**: Python 3.12+ (tested on Python 3.12 - 3.14)  
**Primary Dependencies**: `langgraph`, `instructor`, `pydantic`, `moviepy==1.0.3`, `faster-whisper`, `yt-dlp`, `ctranslate2`, `onnxruntime`, `av<19`  
**Storage**: SQLite (`SqliteSaver` checkpointer pointing to `/app/output/estado.db`)  
**Testing**: Python `unittest` suite (9 test files, 67 test cases)  
**Target Platform**: Docker (Debian-slim) on WSL2 (Ubuntu), 8GB RAM, 8GB Swap, RTX 3060 12GB VRAM  
**Project Type**: Single project / Python domain package under `src/`  
**Performance Goals**: Zero runtime latency overhead; zero memory footprint changes; test execution time unchanged (<25s)  
**Constraints**:
- Strict adherence to `AGENTS.md` memory limits, MoviePy 1.0.3 constraints, and clean code standards.
- Zero functional regression in video rendering, pause cutting, or active speaker tracking.
- All file paths anchored to `PROJECT_ROOT` to maintain container and host parity.  
**Scale/Scope**: 12 application modules relocated, 9 test files relocated, 2 entrypoint files updated (`dockerfile`, `run_pipeline.sh`), 1 draft doc relocated.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Regra Arquitetural (AGENTS.md) | Status | Avaliação / Justificativa |
|---|---|---|
| **1. Gerenciamento de Memória (WSL 8GB / RTX 3060 12GB)** | **PASS** | Refatoração puramente estrutural e organizacional. Nenhum modelo novo, sem alterações em buffers ou alocações de VRAM/RAM. |
| **2. Ingestão & Fatiamento Preventivo** | **PASS** | `node_0.py` e `ingestion.py` migrados para `clipper.core` sem qualquer alteração na lógica de chunks ou silencedetect. |
| **3. Orquestração Obrigatória (LangGraph)** | **PASS** | `StateGraph`, `VideoState`, e o checkpointer SQLite (`/app/output/estado.db`) permanecem idênticos. |
| **4. Cognitive Routing (Single-Model)** | **PASS** | Pensador e Extrator continuam intactos em `clipper.core.orchestrator` usando os prompts de `clipper.core.prompts`. |
| **5. Constrained Decoding (Sem Regex)** | **PASS** | Nenhuma alteração nas validações com Instructor e Pydantic. |
| **6. Manipulação de Vídeo (MoviePy/ImageMagick)** | **PASS** | Restrições de dimensões pares, `pix_fmt yuv420p`, fontes `Liberation-Sans-Bold`, e concatenação `method="chain"` preservadas integralmente em `clipper.video`. |
| **7. Containerização e Variáveis** | **PASS** | `dockerfile` ajustado para `ENV PYTHONPATH=/app/src` e `CMD ["python", "-m", "clipper.core.orchestrator"]`. Volume `/app/output` inalterado. |
| **8. Padrões de Código (Clean Code & English)** | **PASS** | Estrutura inteiramente em inglês (`core`, `video`, `review`, `runtime`). Código limpo e sem poluição na raiz. |
| **9. SDD e Observabilidade Restrita** | **PASS** | Plano e especificações SDD completos gerados antes de qualquer modificação de código. Logs mantidos em `pipeline.log`. |

---

## Project Structure

### Documentation (this feature)

```text
specs/009-repo-restructure/
├── spec.md              # Especificação de requisitos e critérios de aceitação
├── plan.md              # Este plano de implementação
├── research.md          # Pesquisa técnica (Fase 0): empacotamento, imports e Docker
├── data-model.md        # Mapa de domínio, catálogo de módulos e grafo de dependências acíclico
├── quickstart.md        # Guia do desenvolvedor para a nova estrutura
├── contracts/           # Contratos de exportação e entrypoints
│   ├── package-exports.md
│   └── cli-entrypoints.md
└── checklists/
    └── requirements.md  # Checklist de qualidade da especificação
```

### Source Code (Target Layout)

```text
agent-clipper/
├── src/
│   └── clipper/
│       ├── __init__.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── ingestion.py
│       │   ├── node_0.py
│       │   ├── orchestrator.py
│       │   ├── prompts.py
│       │   └── schemas.py
│       ├── video/
│       │   ├── __init__.py
│       │   ├── editor.py
│       │   ├── pause_editing.py
│       │   └── speaker_focus.py
│       ├── review/
│       │   ├── __init__.py
│       │   └── review.py
│       └── runtime/
│           ├── __init__.py
│           ├── config.py
│           ├── cuda_runtime.py
│           └── runtime_options.py
│
├── tests/
│   ├── __init__.py
│   ├── test_cuda_bootstrap.py
│   ├── test_cuda_runtime.py
│   ├── test_editor_render.py
│   ├── test_llm_api.py
│   ├── test_pause_editing.py
│   ├── test_review.py
│   ├── test_runtime_options.py
│   ├── test_speaker_focus.py
│   └── test_transcription.py
│
├── docs/
│   └── prompts_revisado.txt
│
├── tools/
│   ├── export_speaker_models.py
│   └── requirements-speaker-export.txt
│
├── assets/
│   └── speaker_focus/
├── specs/
├── output/
│
├── AGENTS.md
├── README.md
├── dockerfile
├── run_pipeline.sh
├── requirements.txt
├── requirements-cuda.txt
├── requirements-gpu.txt
├── .env.example
├── .dockerignore
└── .gitignore
```

---

## Complexity Tracking

> **Nenhuma violação ou exceção às regras arquiteturais de AGENTS.md.**

| Mudança Estrutural | Complexidade Adicionada | Justificativa | Alternativa Rejeitada |
|---|---|---|---|
| Pacote `src/clipper` com 4 subpacotes | Adiciona 1 nível de diretório e 5 arquivos `__init__.py` | Organiza código por responsabilidade e isola código de produção de testes | Deixar na raiz (31 arquivos caóticos) ou layout flat (não resolve separação por domínio) |
| Diretório `tests/` | 1 novo diretório | Padrão Python para descoberta automatizada de testes com pytest/unittest | Deixar testes misturados com o código de produção |
| `PROJECT_ROOT` ancorado via `parents[3]` | 1 linha em `config.py` | Garante paridade absoluta entre container Docker (`/app`) e host | Usar caminhos relativos ao `cwd` (frágil a comandos executados fora da raiz) |

---

## Planned Phases

### Phase 0: Outline & Research *(Concluída)*
- Definidos os 4 domínios: `core`, `video`, `review`, `runtime`.
- Definida a estratégia de importação absoluta (`from clipper.<domain>.<module> import ...`).
- Definida a adaptação de paths em `config.py` e compatibilidade com `run_pipeline.sh` e `dockerfile`.
- Artefato gerado: `research.md`.

### Phase 1: Design & Contracts *(Concluída)*
- Mapeado o catálogo completo de módulos e suas responsabilidades.
- Verificado o grafo de dependências para garantir aciclicidade estrita (sem imports circulares).
- Definidos os contratos de exportação e interfaces CLI.
- Artefatos gerados: `data-model.md`, `contracts/package-exports.md`, `contracts/cli-entrypoints.md`, `quickstart.md`.

### Phase 2: Implementation Breakdown *(Próximo comando: `@speckit.tasks`)*
- Criação das pastas `src/clipper/`, subpastas de domínio e `tests/`.
- Migração dos módulos `runtime/` (`config.py`, `cuda_runtime.py`, `runtime_options.py`) e ancoragem do `PROJECT_ROOT`.
- Migração dos módulos `core/` (`schemas.py`, `prompts.py`, `ingestion.py`, `node_0.py`, `orchestrator.py`).
- Migração dos módulos `video/` (`editor.py`, `pause_editing.py`, `speaker_focus.py`).
- Migração do módulo `review/` (`review.py`).
- Migração dos 9 testes para `tests/` e atualização dos alvos de `@patch`.
- Atualização de `run_pipeline.sh` e `dockerfile`.
- Validação completa com execução da suíte de testes.
