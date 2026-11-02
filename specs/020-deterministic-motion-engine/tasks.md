# Tasks: Restauração do Motor Determinístico com Motion Design Nativo

**Input**: Design documents from `/specs/020-deterministic-motion-engine/`  
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/  

**Tests**: Testes são incluídos explicitamente conforme especificado em spec.md (SC-006) e plan.md.  

**Organization**: Tarefas organizadas por User Story para permitir implementação e testes independentes de cada história.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Pode rodar em paralelo (arquivos distintos, sem dependências mútuas)
- **[Story]**: A qual User Story a tarefa pertence (ex.: US1, US2, US3, US4)
- Inclui caminhos exatos dos arquivos

## Path Conventions

- **Código-fonte**: `src/clipper/video/`, `src/clipper/core/`
- **Testes**: `tests/`
- Afeta `src/clipper/video/motion_engine.py`, `src/clipper/video/editor.py`, `src/clipper/core/orchestrator.py`, `tests/test_motion_engine.py`, `tests/test_editor.py`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicialização de infraestrutura de testes e mocks compartilhados

- [x] T001 Inicializar estrutura de fixtures e testes em `tests/test_motion_engine.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Criação do módulo de motion design e resolução de intervalos de cenas

**⚠️ CRITICAL**: Nenhuma história de usuário pode iniciar sem esta fundação

- [x] T002 Implementar dataclasses `SceneInterval`, `MotionPlan` e funções auxiliares de normalização de palavras em `src/clipper/video/motion_engine.py`
- [x] T003 Implementar `build_motion_plan(corte, words, duration)` em `src/clipper/video/motion_engine.py` mapeando `Scene`s para intervalos contíguos de 0.0 até duration sem gaps

**Checkpoint**: Fundação pronta - tarefas das histórias de usuário podem prosseguir

---

## Phase 3: User Story 1 - Renderização Determinística de Cortes Aprovados (Priority: P1) 🎯 MVP

**Goal**: Restaurar o nó síncrono `editor_node` conectado ao `cut_and_format_video` no DAG LangGraph, desativando o ciclo estocástico de LLM (`coder_node` + `execution_node` + auto-cura), garantindo 0% de renderização para cortes rejeitados e saída rápida (<5s) quando a aprovação for vazia.

**Independent Test**: Executar `editor_node` com mock de aprovações parciais e vazias, verificando que os vídeos aprovados são renderizados diretamente via Python sem invocar LLM e que `rendered_video_paths` é retornado.

### Tests for User Story 1
- [x] T004 [P] [US1] Criar testes unitários para `editor_node` verificando validação de `decision.json`, seletividade de cortes aprovados, e retorno de `rendered_video_paths` em `tests/test_editor.py`
- [x] T005 [P] [US1] Criar testes do DAG LangGraph em `tests/test_orchestrator.py` validando roteamento de `approval_node` diretamente para `editor_node` ou `END`

### Implementation for User Story 1
- [x] T006 [US1] Restaurar a função `editor_node` em `src/clipper/core/orchestrator.py` lendo `approved_cut_ids`, filtrando cortes aprovados, registrando INFO para rejeitados e chamando `cut_and_format_video`
- [x] T007 [US1] Atualizar `create_graph()` em `src/clipper/core/orchestrator.py` conectando `approval` -> `route_approval_outcome` (se aprovado vai para `editor_node`, se vazio vai para `END`) e `editor_node` -> `END`
- [x] T008 [US1] Executar testes da User Story 1 via `PYTHONPATH=src venv/bin/python -m unittest tests/test_editor.py tests/test_orchestrator.py`

**Checkpoint**: User Story 1 100% funcional e testável de forma independente

---

## Phase 4: User Story 2 - Legendas Sincronizadas e Contínuas (Priority: P2)

**Goal**: Garantir que 100% das palavras do corte transcritas pelo Whisper sejam repassadas ao gerador de legendas do `editor.py` (sem truncamento `[:100]`), sincronizando legendas do início ao fim do vídeo via Pillow e `Liberation-Sans-Bold`.

**Independent Test**: Renderizar corte longo (>150 palavras) e verificar que todas as palavras geram clipes de legenda cobrindo do início ao fim da fala.

### Tests for User Story 2
- [x] T009 [P] [US2] Criar testes unitários em `tests/test_editor.py` validando que cortes com >100 palavras não sofrem truncamento e geram legendas até o final da fala
- [x] T010 [P] [US2] Validar sincronismo de legendas com plano de corte de pausas (`remap_word_groups`) e identidade visual em `tests/test_editor.py`

### Implementation for User Story 2
- [x] T011 [US2] Garantir que `editor_node` e `cut_and_format_video` recebam e processem a lista completa de palavras do corte em `src/clipper/video/editor.py` e `src/clipper/core/orchestrator.py`
- [x] T012 [US2] Ajustar criação de `caption_clips` em `src/clipper/video/editor.py` para aplicar estilos de `visual_identity` (cor primária, stroke, fontes liberation e posicionamento a 79%)
- [x] T013 [US2] Executar testes da User Story 2 via `PYTHONPATH=src venv/bin/python -m unittest tests/test_editor.py`

**Checkpoint**: User Story 2 100% funcional com legendas completas

---

## Phase 5: User Story 3 - Execução de Gatilhos de Motion Design por Cena (Priority: P3)

**Goal**: Implementar `apply_motion_design` em `src/clipper/video/motion_engine.py` e integrá-lo a `cut_and_format_video`, gerando efeitos de enquadramento (punch-in `impact`, aproximação `zoom_in`/`slow_zoom`, alternância `cut_transition`/`whip_pan`) e pills/badges de metáforas visuais.

**Independent Test**: Injetar corte com cenas contendo gatilhos distintos e verificar que os subclips gerados possuem os fatores de escala e enquadramento esperados com dimensões pares.

### Tests for User Story 3
- [x] T014 [P] [US3] Criar testes unitários em `tests/test_motion_engine.py` para os gatilhos `impact` (escala 1.12x), `zoom_in` e `cut_transition`
- [x] T015 [P] [US3] Criar testes de validação de paridade dimensional (largura e altura pares) e concatenação contígua em `tests/test_motion_engine.py`

### Implementation for User Story 3
- [x] T016 [US3] Implementar função `apply_motion_design(clip, motion_plan, visual_identity)` em `src/clipper/video/motion_engine.py` aplicando enquadramentos dinâmicos por cena
- [x] T017 [US3] Implementar renderização determinística opcional de pill/badge com a metáfora visual via Pillow em `src/clipper/video/motion_engine.py`
- [x] T018 [US3] Integrar `motion_engine` dentro de `cut_and_format_video` em `src/clipper/video/editor.py` antes da sobreposição de legendas
- [x] T019 [US3] Executar testes da User Story 3 via `PYTHONPATH=src venv/bin/python -m unittest tests/test_motion_engine.py`

**Checkpoint**: User Story 3 100% funcional com motion design ativo

---

## Phase 6: User Story 4 - Preservação Estrita de Memória RAM e VRAM (Priority: P4)

**Goal**: Garantir que a renderização determinística desaloca todos os clips intermediários (`.close()`, `del`, `gc.collect()`), mantém o consumo de pico de RAM < 2 GB e executa `release_cuda_memory(cut_id=...)` incondicionalmente no perfil CUDA ao final de cada corte.

**Independent Test**: Verificar que `release_cuda_memory()` é disparado no bloco `finally:` de cada corte e que chamadas de `.close()` são invocadas em todos os clips intermediários e compostos.

### Tests for User Story 4
- [x] T020 [P] [US4] Criar testes em `tests/test_editor.py` verificando disparo incondicional de `release_cuda_memory()` e desalocação de buffers em bloco `finally:`

### Implementation for User Story 4
- [x] T021 [US4] Assegurar fechamento de clips, invocação de `gc.collect()` e chamada a `release_cuda_memory(cut_id=cut_id)` no bloco `finally:` em `src/clipper/core/orchestrator.py` (`editor_node`) e `src/clipper/video/editor.py`
- [x] T022 [US4] Executar testes da User Story 4 via `PYTHONPATH=src venv/bin/python -m unittest tests/test_editor.py`

**Checkpoint**: User Story 4 100% validada quanto ao gerenciamento de recursos

---

## Phase 7: Polish & Regression Suite

**Purpose**: Verificação completa de regressão em toda a base de testes e sincronização de documentação

- [x] T023 Executar suíte completa de testes de regressão do projeto (`PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"`)
- [x] T024 Sincronizar documentação e regras operacionais em `README.md`, `AGENTS.md` e `GEMINI.md` refletindo a arquitetura do motor determinístico e motion design
