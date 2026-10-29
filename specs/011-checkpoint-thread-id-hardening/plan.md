# Implementation Plan: Checkpoint Thread ID Hardening

**Branch**: `011-checkpoint-thread-id-hardening` | **Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/011-checkpoint-thread-id-hardening/spec.md`

---

## Summary

This feature hardens the LangGraph checkpointer `thread_id` derivation in `src/clipper/core/orchestrator.py` against context collisions and cross-contamination when switching execution configurations. 

Specifically, the `thread_id` is derived as a pure, deterministic 16-character SHA-256 hexadecimal hash computed from the canonical pipe-delimited string `[video_id]|[LLM_PROVIDER]|[MODEL_NAME]|[LLM_BASE_URL]|[SILENCE_CUT_ENABLED]|[SILENCE_MIN_PAUSE]`. This ensures that:
- Runs for the same video with different LLM providers (`ollama` vs `gemini`), models, or endpoints generate distinct `thread_id` values, preventing context contamination, VRAM thrashing, or prompt schema mismatches.
- Runs with differing silence detection settings (`SILENCE_CUT_ENABLED` or `SILENCE_MIN_PAUSE`) generate distinct `thread_id` values, ensuring pause plans and cut approvals are not erroneously reused.
- Runs with identical parameters generate mathematically identical `thread_id` values (100% deterministic idempotency), preserving legitimate crash recovery.
- Checkpoints derived from older versions are cleanly separated and orphaned without silent, corrupt resumption.
- Clear, structured `INFO` level logging enables full traceability in `pipeline.log`.

---

## Technical Context

**Language/Version**: Python 3.12+ (tested on Python 3.12 - 3.14)  
**Primary Dependencies**: `langgraph>=0.2.0`, `instructor`, `pydantic`, `moviepy==1.0.3`, `faster-whisper`, `yt-dlp`, `ctranslate2`, `onnxruntime`, `av<19`  
**Storage**: SQLite (`SqliteSaver` checkpointer in `/app/output/estado.db`), `pipeline.log` in `/app/output/`  
**Testing**: Python `unittest` suite (new `tests/test_checkpoint_thread_id.py` + updates to `tests/test_llm_api.py` and `tests/test_pause_editing.py`)  
**Target Platform**: Docker (Debian-slim) on WSL2 (Ubuntu), 8GB RAM, 8GB Swap, RTX 3060 12GB VRAM  
**Project Type**: Single project / Python domain package under `src/`  
**Performance Goals**: 
- `thread_id` computation time <1ms (imperceptible overhead).
- Zero additional memory footprint or background process overhead.  
**Constraints**:
- Strict adherence to `AGENTS.md` rules: English naming, clean code, no external telemetry.
- SHA-256 truncated to 16 hex characters (`^[0-9a-f]{16}$`).
- Tolerant of `None` / missing optional parameters with documented safe defaults from `config.py`.
- Inline warning comment explicitly noting that changes to the function invalidate existing checkpoints in `estado.db`.
- Pure function implementation with no network or disk I/O side effects during hash computation.  
**Scale/Scope**: Focused update to `checkpoint_thread_id` and startup logging in `src/clipper/core/orchestrator.py`, helper video ID extraction in `src/clipper/core/ingestion.py` / `orchestrator.py`, and comprehensive unit test coverage.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Regra Arquitetural (AGENTS.md) | Status | Avaliação / Justificativa |
|---|---|---|
| **1. Gerenciamento de Memória (WSL 8GB / RTX 3060 12GB)** | **PASS** | Hash SHA-256 executado em microssegundos na CPU sem impacto de RAM ou VRAM. |
| **2. Ingestão & Fatiamento Preventivo** | **PASS** | Fatiamento de áudio (`node_0`) e download permanecem inalterados. |
| **3. Orquestração Obrigatória (LangGraph)** | **PASS** | Fortalece a isolação de checkpoints do `SqliteSaver` em `/app/output/estado.db`. |
| **4. Cognitive Routing (Single-Model)** | **PASS** | Pensador e Extrator mantêm integridade sequencial sem alteração. |
| **5. Constrained Decoding (Sem Regex)** | **PASS** | Estruturas de dados e schemas Pydantic permanecem intactos. |
| **6. Manipulação de Vídeo (MoviePy/ImageMagick)** | **PASS** | Parâmetros de vídeo inalterados; previne reaproveitamento de planos de corte de silêncio errôneos. |
| **7. Containerização e Variáveis** | **PASS** | Cumpre diretamente a diretriz da Regra 7 de AGENTS.md, garantindo que vídeo, provedor, modelo, endpoint (LLM_BASE_URL) e configurações de cortes de silêncio componham a identidade do checkpoint. |
| **8. Padrões de Código (Clean Code & English)** | **PASS** | Nomenclatura 100% em inglês com comentários explicativos restritos ao "porquê". |
| **9. SDD e Observabilidade Restrita** | **PASS** | Especificação SDD gerada antes da implementação. Observabilidade feita via `pipeline.log` tradicional. |
| **10. Atualização Contínua de Documentação (Doc Sync)** | **PASS** | Sincronização documentada em `GEMINI.md` e artefatos de spec. |

---

## Project Structure

### Documentation (this feature)

```text
specs/011-checkpoint-thread-id-hardening/
├── spec.md              # Requisitos funcionais, cenários de aceitação e critérios de sucesso
├── plan.md              # Este plano de implementação
├── research.md          # Fase 0: Pesquisa técnica e decisões de hashing e normalização
├── data-model.md        # Fase 1: Modelo de dados, esquema e ciclo de vida do thread_id
├── quickstart.md        # Fase 1: Guia prático de testes e validação
├── contracts/           # Fase 1: Contratos de interface e observabilidade
│   └── checkpoint-thread-id-contract.md
└── checklists/
    └── requirements.md  # Checklist de qualidade da especificação
```

### Source Code (Target Layout)

```text
src/clipper/
├── core/
│   ├── orchestrator.py  # ATUALIZAR: checkpoint_thread_id, main() logging e extract_video_id
│   ├── ingestion.py     # REUTILIZAR: extract_video_id ou lógica de extração
│   ├── schemas.py
│   ├── node_0.py
│   └── prompts.py
├── runtime/
│   ├── config.py        # REUTILIZAR: LLM_PROVIDER, MODEL_NAME, LLM_BASE_URL, SILENCE_CUT_ENABLED, SILENCE_MIN_PAUSE
│   └── runtime_options.py
tests/
├── test_checkpoint_thread_id.py # NOVO: Testes unitários dedicados para FR-001 a FR-008
├── test_llm_api.py              # ATUALIZAR: Validar test_checkpoint_identity_isolates...
└── test_pause_editing.py        # ATUALIZAR: Validar test_settings_are_part_of_checkpoint_identity
```

---

## Complexity Tracking

> **Nenhuma violação ou exceção às regras arquiteturais de AGENTS.md.**

| Mudança Técnica | Complexidade Adicionada | Justificativa | Alternativa Rejeitada |
|---|---|---|---|
| Hash SHA-256[:16] determinístico | ~10 linhas de Python padrão (`hashlib`) | Elimina colisão de contexto entre provedores, modelos, endpoints e configurações de silêncio | Manter prefixo antigo e dump JSON desnecessário |
| Normalização segura com fallbacks | ~15 linhas de código defensivo | Garante tolerância a `None` e tipos variados (bool, int, str) sem quebrar o pipeline | Lançar exceções rígidas que quebram CLI e integrações existentes |
| Extração limpa de `video_id` | ~6 linhas de helper regex | Permite que tanto URLs completas quanto IDs isolados sejam aceitos de forma consistente | Exigir que o operador configure manualmente duas variáveis separadas |

---

## Planned Phases

### Phase 0: Outline & Research *(Concluída)*
- Definir formato canônico: `f"{video_id}|{provider}|{model}|{endpoint}|{silence_enabled}|{silence_min_pause}"`.
- Resolver política de hashing: SHA-256 truncado a 16 caracteres hexadecimais sem prefixo customizado.
- Formalizar regras de tolerância a `None` e fallback para runtime `config.py`.
- Documentar em `research.md`.

### Phase 1: Design & Contracts *(Concluída)*
- Modelar entidade `CheckpointIdentity` e mapeamento com SQLite em `data-model.md`.
- Definir contrato rigoroso da função e observabilidade em `contracts/checkpoint-thread-id-contract.md`.
- Elaborar guia prático de validação e reprodução em `quickstart.md`.
- Atualizar contexto do agente (`update-agent-context.sh gemini`).

### Phase 2: Implementation Breakdown *(Para `/speckit.tasks`)*
- **Task 1**: Implementar helper `extract_video_id` em `src/clipper/core/ingestion.py` e refatorar `checkpoint_thread_id` em `src/clipper/core/orchestrator.py` com o aviso inline e contrato canônico incluindo `LLM_BASE_URL`.
- **Task 2**: Atualizar o log de inicialização em `orchestrator.py:main` para registrar o `thread_id` calculado no nível `INFO`.
- **Task 3**: Criar a suíte de testes unitários `tests/test_checkpoint_thread_id.py` cobrindo determinismo, isolamento de provider, isolamento de modelo, isolamento de endpoint, isolamento de flags de silêncio, tolerância a `None` e formato de 16 hexadecimais.
- **Task 4**: Atualizar testes legados em `tests/test_llm_api.py` e `tests/test_pause_editing.py` para compatibilidade com o novo formato de 16 hexadecimais sem enfraquecer asserções.
- **Task 5**: Executar a suíte de testes completa (`python -m unittest discover tests/ -p "test_*.py"`) e validar ausência de regressões.
