# Implementation Plan: Alinhamento de Concorrência entre Nós LangGraph e Client Instructor

**Branch**: `014-align-instructor-nodes` | **Date**: 2026-10-30 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/014-align-instructor-nodes/spec.md`

## Summary

O `agent-clipper` adota o padrão arquitetural *Single-Model Cognitive Routing* (Nó Pensador seguido de Nó Extrator) para geração de clipes verticais. Para assegurar estabilidade operacional sob limites físicos severos de hardware (WSL2 com 8GB RAM e 12GB VRAM), esta feature formaliza e blinda o **Cenário A (Padrão de Execução Síncrono Estrito)**:

1. **Assinaturas Síncronas Convencionais**: 100% dos nós registrados no `StateGraph` do LangGraph são definidos estritamente como funções síncronas (`def`), proibindo o uso de `async def`.
2. **Fábrica de Cliente LLM Síncrono**: `create_llm_client()` instancia e retorna estritamente o cliente síncrono `openai.OpenAI`, anotado com tipagem estrita de retorno, proibindo o retorno de `openai.AsyncOpenAI`.
3. **Instructor Síncrono**: O nó Extrator utiliza o wrapper síncrono `instructor.from_openai(raw_client, mode=instructor.Mode.JSON_SCHEMA)` sobre o cliente base síncrono, operando de forma bloqueante na thread corrente sem depender de laço de eventos assíncrono.
4. **Descarte Determinístico de Conexões**: Tanto o `thinker_node` quanto o `extractor_node` encerram explicitamente o transporte HTTP via `raw_client.close()` em bloco `finally`, prevenindo vazamentos de soquetes (*socket descriptor leaks*).
5. **Suíte de Testes de Contrato Arquitetural**: Implementação de `tests/test_instructor_sync_contract.py` para inspecionar reflexivamente o grafo, validar o tipo das instâncias e garantir ausência de corrotinas ou avisos assíncronos.

## Technical Context

**Language/Version**: Python 3.12+ (tested on Python 3.12 - 3.14)  
**Primary Dependencies**: langgraph, instructor, openai, pydantic, moviepy==1.0.3, faster-whisper  
**Storage**: SQLite (`/app/output/estado.db` via `SqliteSaver`)  
**Testing**: unittest (`PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"`)  
**Target Platform**: Linux (Docker Debian-slim sobre WSL2 Ubuntu), 8GB RAM, RTX 3060 12GB VRAM  
**Project Type**: Single project Python (CLI pipeline)  
**Performance Goals**: Execução sequencial determinística sem overhead de event loop assíncrono, zero vazamento de descritores de arquivo ou conexões de rede  
**Constraints**: Sem telemetria externa (§9 AGENTS.md), sem async loop nos nós, liberação determinística de sockets via close() em finally, padrões de nomenclatura em inglês (§8 AGENTS.md)  
**Scale/Scope**: 8 nós no StateGraph, 2 nós de LLM (pensador e extrator), 1 factory de cliente (`create_llm_client`), cobertura 100% de testes contratuais

## Constitution Check

*GATE: Verificado contra AGENTS.md antes do design e reavaliado pós-design.*

| Regra AGENTS.md | Status | Observação |
|---|---|---|
| Sem regex/json.loads manual para limpar saída de IA (§5) | ✅ Cumprido | Uso estrito de Instructor acoplado ao schema Pydantic `CortesResponse` via `Mode.JSON_SCHEMA` |
| MoviePy: dimensões pares, yuv420p, Liberation Sans (§6) | ✅ Não alterado | Submódulo de renderização de vídeo preservado sem alterações |
| Transcrição: CPU/int8 (Ollama) ou CUDA/float16 (Gemini) (§1) | ✅ Não alterado | Ingestão e transcrição Whisper mantidas intactas |
| Unload de modelo + GC após chunk (§1, §2) | ✅ Preservado | Limpeza de CTranslate2 e NVML VRAM mantida |
| Sem telemetria externa (§9) | ✅ Cumprido | Nenhum coletor de telemetria adicionado; observabilidade via logging padrão |
| LangGraph StateGraph + interrupt() HITL (§3) | ✅ Blindado | Grafo preservado como StateGraph sequencial, executado via `app.invoke()` sem dependência de laço assíncrono |
| Nomenclatura em inglês (§8) | ✅ Cumprido | Funções, classes, variáveis e novos testes nomeados estritamente em inglês |
| Sem hardcode de URL/parâmetro (§7) | ✅ Cumprido | Configurações lidas de variáveis de ambiente através de `config.py` |
| Checkpoints incluem identidade completa (§7) | ✅ Preservado | Identidade determinística do thread_id mantida |
| Doc Sync ao finalizar (§10) | 🔲 Pendente | Atualização do `GEMINI.md` via script de contexto do agente |

**Resultado:** ✅ Sem violações. Nenhuma entrada na tabela Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/014-align-instructor-nodes/
├── plan.md              # Este documento de plano de implementação
├── research.md          # Pesquisa técnica e justificativas de concorrência síncrona
├── data-model.md        # Entidades, contratos funcionais e diagramas de sequência
├── quickstart.md        # Guia de validação e comandos de teste
├── contracts/           # Contratos de interface
│   └── llm-node-sync-contract.md
└── tasks.md             # Tarefas de implementação geradas na próxima etapa
```

### Source Code Layout

```text
src/
└── clipper/
    ├── core/
    │   ├── orchestrator.py    # create_graph, create_llm_client, thinker_node, extractor_node
    │   └── ingestion.py       # download, fatiamento, transcrição
    ├── runtime/
    │   ├── config.py          # validações e resoluções de perfil (ollama/gemini)
    │   └── cuda_runtime.py    # liberação de VRAM CUDA
    ├── video/
    │   ├── editor.py          # renderização MoviePy
    │   └── pause_editing.py   # encurtamento de pausas
    └── review/
        └── review.py          # servidor e persistência de revisão humana

tests/
├── test_instructor_sync_contract.py  # Nova suíte de testes de contrato arquitetural (FR-001 a FR-008)
├── test_llm_api.py                   # Testes de integração de API LLM existentes
├── test_review.py                    # Testes HITL e persistência
└── test_transcription.py             # Testes de ingestão e transcrição
```

## Complexity Tracking

> **Nenhuma violação identificada contra as diretrizes do AGENTS.md.**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| *Nenhuma* | — | — |

---

## Phase 0: Outline & Research

Consolidado em [research.md](research.md):
- **Finding 1 (Paradigma de Concorrência)**: Adoção estrita de funções síncronas convencionais (`def`) e invocação síncrona (`app.invoke`), eliminando riscos de bloqueio de Event Loop e incompatibilidade com o checkpointer SQLite síncrono.
- **Finding 2 (Fábrica `create_llm_client`)**: Instanciação estrita de `openai.OpenAI` com tipagem explícita de retorno, timeout de 180s e retries limitados a 2. Proibido retornar `openai.AsyncOpenAI`.
- **Finding 3 (Instructor Síncrono)**: Encapsulamento com `instructor.from_openai(raw_client, mode=instructor.Mode.JSON_SCHEMA)`, resultando em uma instância síncrona `instructor.Instructor`.
- **Finding 4 (Liberação Determinística de Sockets)**: Cláusulas `finally` explícitas em `thinker_node` e `extractor_node` invocando `raw_client.close()`, cobrindo tanto execuções bem-sucedidas quanto exceções (timeout, HTTP error, schema validation error).
- **Finding 5 (Estratégia de Testes)**: Criação de testes de contrato reflexivos em `tests/test_instructor_sync_contract.py` utilizando `inspect.iscoroutinefunction` e asserções de classe para garantir conformidade contínua.

---

## Phase 1: Design & Contracts

Consolidado em [data-model.md](data-model.md), [contracts/llm-node-sync-contract.md](contracts/llm-node-sync-contract.md) e [quickstart.md](quickstart.md):
- **Modelo de Dados**: `VideoState` blindado como repositório de dados serializáveis, contratos formais para `NodeCallable`, `SyncLLMClient` e `SyncInstructorClient`.
- **Diagramas de Sequência**: Fluxo determinístico de requisição e fechamento de conexões para o nó Pensador e nó Extrator.
- **Contratos de Interface**: Especificações pré/pós-condições para `create_llm_client()`, `thinker_node()`, `extractor_node()` e `create_graph()`.
- **Atualização de Contexto de Agente**: Sincronização executada via script automatizado.
