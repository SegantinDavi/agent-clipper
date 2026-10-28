# Implementation Plan: LangGraph Native Human-in-the-Loop Checkpoint Integration

**Branch**: `010-manual-review-langgraph-integration` | **Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/010-manual-review-langgraph-integration/spec.md`

---

## Summary

This feature integrates human cut approval natively into LangGraph's state machine and SQLite checkpointer (`/app/output/estado.db`) using native Human-in-the-Loop primitives (`interrupt()` and `Command(resume=...)`). 

By decoupling the review HTTP server from graph execution and managing it strictly within `run_with_review()` in `src/clipper/core/orchestrator.py`:
- `approval_node` invokes `interrupt()`, synchronously yielding control back to the LangGraph runtime, which commits the interrupted state to SQLite before any HTTP listener begins.
- An orchestrator driver loop checks for a committed `decision.json` on disk before launching the HTTP server. If present (e.g. from a previous container run that died before resume), it injects the decision directly into `Command(resume=...)`, bypassing the browser interface.
- If no decision exists, the orchestrator serves the review page on `127.0.0.1`, awaits the browser POST, writes `decision.json` atomically, and resumes the graph.
- Using `--restart` deterministically purges existing checkpoints for that thread in SQLite and generates a fresh review session, ensuring full clean reruns from `START`.
- Resuming without `--restart` handles all 4 crash scenarios seamlessly, eliminating redundant downloads, Whisper transcriptions, and LLM inferences.

---

## Technical Context

**Language/Version**: Python 3.12+ (tested on Python 3.12 - 3.14)  
**Primary Dependencies**: `langgraph>=0.2.0`, `instructor`, `pydantic`, `moviepy==1.0.3`, `faster-whisper`, `yt-dlp`, `ctranslate2`, `onnxruntime`, `av<19`  
**Storage**: SQLite (`SqliteSaver` checkpointer in `/app/output/estado.db`), atomic JSON files (`review.json`, `decision.json`)  
**Testing**: Python `unittest` suite (expanding `tests/test_review.py`)  
**Target Platform**: Docker (Debian-slim) on WSL2 (Ubuntu), 8GB RAM, 8GB Swap, RTX 3060 12GB VRAM  
**Project Type**: Single project / Python domain package under `src/`  
**Performance Goals**: 
- SQLite checkpoint saved within <2s of reaching `approval_node`.
- Review page re-served on container restart within <30s without repeating prior node work.
- Zero extra memory footprint or hanging background threads.  
**Constraints**:
- Strict adherence to `AGENTS.md` memory limits, MoviePy 1.0.3 constraints, and clean code standards.
- No blocking loops inside LangGraph nodes; `approval_node` must yield execution via `interrupt()`.
- HTTP server must run outside the LangGraph DAG thread.
- Atomic write for `decision.json` via `.partial` file rename.
- In-node `interrupt()` chosen; `interrupt_before` rejected to avoid double-interruption.  
**Scale/Scope**: Modifications to `src/clipper/core/orchestrator.py` (`run_with_review`, `approval_node`, and checkpoint purge helper) and comprehensive test additions in `tests/test_review.py`.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Regra Arquitetural (AGENTS.md) | Status | Avaliação / Justificativa |
|---|---|---|
| **1. Gerenciamento de Memória (WSL 8GB / RTX 3060 12GB)** | **PASS** | HITL desacoplado não aloca modelos adicionais nem retém frames na memória. O servidor HTTP é efêmero e local. |
| **2. Ingestão & Fatiamento Preventivo** | **PASS** | Nós de download, fatiamento (`node_0`) e transcrição permanecem inalterados. |
| **3. Orquestração Obrigatória (LangGraph)** | **PASS** | Reforça a arquitetura LangGraph ao substituir loops procedurais por `interrupt()` e `Command(resume=...)` sobre o `SqliteSaver`. |
| **4. Cognitive Routing (Single-Model)** | **PASS** | Pensador e Extrator continuam executando sequencialmente com o mesmo LLM configurado. |
| **5. Constrained Decoding (Sem Regex)** | **PASS** | `ApprovalDecision` e validações continuam utilizando Pydantic rigorosamente. |
| **6. Manipulação de Vídeo (MoviePy/ImageMagick)** | **PASS** | `editor_node` continua exigindo aprovação estrita antes de iniciar a renderização e segue as regras de dimensões pares e `method="chain"`. |
| **7. Containerização e Variáveis** | **PASS** | Paridade mantida com Docker. Checkpoints em `/app/output/estado.db`. `--restart` purga checkpoint para garantir reprodutibilidade. |
| **8. Padrões de Código (Clean Code & English)** | **PASS** | Todas as novas funções e variáveis em inglês com comentários explicativos restritos ao "porquê". |
| **9. SDD e Observabilidade Restrita** | **PASS** | Artefatos SDD completos gerados antes da implementação. Observabilidade restrita a logs tradicionais em `pipeline.log`. |

---

## Project Structure

### Documentation (this feature)

```text
specs/010-manual-review-langgraph-integration/
├── spec.md              # Requisitos funcionais, cenários de aceitação e critérios de sucesso
├── plan.md              # Este plano de implementação
├── research.md          # Pesquisa técnica (Fase 0): HITL primitives, durability e restart
├── data-model.md        # Entidades de estado, modelo de transição e esquema SQLite
├── quickstart.md        # Guia do desenvolvedor para validação de cenários de crash
├── contracts/           # Contratos de interfaces e persistência
│   ├── orchestrator-hitl-contract.md
│   └── review-persistence-contract.md
└── checklists/
    └── requirements.md  # Checklist de qualidade da especificação
```

### Source Code (Target Layout)

```text
src/clipper/
├── core/
│   ├── orchestrator.py  # ATUALIZAR: run_with_review, approval_node, purge_checkpoint
│   ├── schemas.py
│   ├── ingestion.py
│   ├── node_0.py
│   └── prompts.py
├── review/
│   └── review.py        # Validação e servidor HTTP
├── video/
│   ├── editor.py
│   ├── pause_editing.py
│   └── speaker_focus.py
└── runtime/
    ├── config.py
    ├── cuda_runtime.py
    └── runtime_options.py

tests/
└── test_review.py       # ATUALIZAR: Testes de crash recovery, HITL interrupt, e --restart
```

---

## Complexity Tracking

> **Nenhuma violação ou exceção às regras arquiteturais de AGENTS.md.**

| Mudança Técnica | Complexidade Adicionada | Justificativa | Alternativa Rejeitada |
|---|---|---|---|
| In-node `interrupt()` com `Command(resume=...)` | Utiliza tipos nativos do LangGraph 0.2+ | Permite persistência do estado no SQLite antes de esperar input humano | Manter loop `while server.decision is None` dentro de nó ou de forma síncrona (perde checkpoints em crash) |
| Purga de thread SQLite em `--restart` | 4 linhas de SQL (`DELETE FROM checkpoints/writes WHERE thread_id=?`) | Garante que o comando `--restart` comece do zero sem resíduos de interrupts anteriores | Deletar todo o arquivo `estado.db` (perde histórico de outros vídeos) ou ignorar checkpoint (re-dispara o interrupt) |
| Checagem de `decision.json` pré-servidor | 8 linhas de verificação e desserialização Pydantic | Recupera decisões confirmadas mesmo se o container cair antes do `Command(resume=...)` | Forçar re-abertura do servidor web (inconveniente ao usuário e risco de decisões conflitantes) |

---

## Planned Phases

### Phase 0: Outline & Research *(Concluída)*
- Definido o uso de `interrupt()` no nó `approval_node` com payload descritivo.
- Rejeitado o uso de `interrupt_before=["approval"]` para evitar double-interruption e manter o grafo limpo.
- Definida a máquina de estados em `run_with_review()` cobrindo todas as variantes de crash e retomada.
- Definida a estratégia de purga de checkpoints SQLite para `--restart`.
- Artefato gerado: `research.md`.

### Phase 1: Design & Contracts *(Concluída)*
- Mapeado o modelo de dados de `VideoState`, payloads de `interrupt` e `Command(resume=...)`.
- Modelado o diagrama de transições de estado do orchestrator e persistência.
- Definidos os contratos de interface em `contracts/orchestrator-hitl-contract.md` e `contracts/review-persistence-contract.md`.
- Elaborado o guia prático em `quickstart.md`.
- Atualizado o contexto do agente.
- Artefatos gerados: `data-model.md`, `contracts/*`, `quickstart.md`.

### Phase 2: Implementation Breakdown *(Próximo comando: `@speckit.tasks`)*
- **Tarefa 1**: Atualizar `orchestrator.py` para incluir a função de invalidação de checkpoint SQLite (`purge_thread_checkpoints`).
- **Tarefa 2**: Refatorar `run_with_review` em `orchestrator.py` para implementar o loop de condução de HITL com verificação de `decision.json` em disco e purga no `--restart`.
- **Tarefa 3**: Expandir `tests/test_review.py` com casos de teste dedicados para:
  - Interrupção nativa e checkpoint SQLite verificado via `app.get_state()`.
  - Retomada sem `--restart` quando o container cai com `decision.json` já gravado (pula servidor).
  - Retomada sem `--restart` quando o container cai durante a espera do servidor (reabre servidor).
  - Execução com `--restart` purga o checkpoint existente e executa do início.
  - Execução sobre run já concluído sem `--restart` encerra com mensagem informativa.
- **Tarefa 4**: Validação completa da suíte de 67+ testes e verificação de não-regressão.
