# Implementation Plan: Few-Shot Prompting no Extractor Node

**Branch**: `001-few-shot-extractor` | **Date**: 2026-10-23 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/001-few-shot-extractor/spec.md`

---

## Summary

Sob estresse contextual de podcasts longos (> 60 min, > 3000 tokens), o modelo local Qwen2.5:14b sofre degradação de atenção e falha na emissão de saídas aderentes ao schema Pydantic `CorteVideo` no `extractor_node`. 

A abordagem técnica consiste em aplicar **Few-Shot Prompting estruturado** através da alternância de turnos (`user` / `assistant` mock) diretamente no array de mensagens enviado ao `instructor_client`, além de desacoplar e centralizar todos os prompts em `prompts.py` na raiz do projeto. Isso ancora cognitivamente o LLM antes da ingestão dos dados reais, sem introduzir regex, retries externos ou novos modelos.

---

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: `langgraph`, `instructor`, `pydantic`, `openai`  
**Storage**: SQLite (`SqliteSaver` checkpointer apontando para `/app/output/estado.db`)  
**Testing**: Python inline validation / `pytest` / isolamento de importações  
**Target Platform**: Linux (Debian-slim em Docker sobre WSL2, 8GB RAM, 8GB Swap, RTX 3060 12GB VRAM)  
**Project Type**: Single project / Autonomous pipeline DAG  
**Performance Goals**: Overhead de latência no `extractor_node` < 5%; zero vazamento de memória; tempo de resposta proporcional ao tamanho da transcrição  
**Constraints**: 
- Modelo único: `Qwen2.5:14b` em `OLLAMA_BASE_URL` (`localhost`)
- Zero regex (`re.search`) ou `json.loads` manual (decodificação 100% via `instructor` + `pydantic`)
- Zero telemetria pesada externa (Langfuse, Phoenix)
- Nomes em inglês e comentários restritos ao "porquê"
**Scale/Scope**: 2 arquivos de código impactados (`prompts.py` criado na raiz, `orchestrator.py` refatorado)

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Regra Arquitetural (AGENTS.md) | Status | Avaliação / Justificativa |
|---|---|---|
| **1. Gerenciamento de Memória (WSL 8GB / RTX 3060 12GB)** | **PASS** | Few-Shot consome apenas ~250 tokens adicionais de prompt (< 1.5% do contexto). Zero alocação extra de VRAM. Sem novos modelos. |
| **2. Ingestão & Fatiamento Preventivo** | **PASS** | Mantido intacto nos nós 1 a 3. Transcrição enviada ao nó pensador/extrator continua resumida por frases com timestamps agrupados. |
| **3. Orquestração Obrigatória (LangGraph)** | **PASS** | O DAG no `orchestrator.py` permanece com os 6 nós sequenciais. `VideoState` permanece inalterado (`TypedDict`). |
| **4. Cognitive Routing (Single-Model)** | **PASS** | Pensador (CoT livre) e Extrator (estruturado) continuam operando sequencialmente sobre a mesma instância do Qwen2.5:14b. |
| **5. Constrained Decoding (Sem Regex)** | **PASS** | Resolução da falha estritamente via Few-Shot in-context learning e Pydantic schema no Instructor. Nenhuma regex ou parser manual adicionado. |
| **6. Manipulação de Vídeo (MoviePy/ImageMagick)** | **PASS** | Nós de fatiamento e edição não são modificados. |
| **7. Containerização e Variáveis** | **PASS** | `prompts.py` e `orchestrator.py` respeitam variáveis de ambiente via `config.py`. |
| **8. Padrões de Código (Clean Code & English)** | **PASS** | Variáveis, funções e constantes em inglês (`THINKER_SYSTEM_PROMPT`, `EXTRACTOR_FEW_SHOT_EXAMPLES`, etc.). Comentários apenas explicativos de restrições de domínio. |
| **9. SDD e Observabilidade Restrita** | **PASS** | SDD gerado via speckit antes da codificação. Logs limitados a `logging` padrão em `pipeline.log`. Nenhuma dependência pesada de telemetria adicionada. |

---

## Project Structure

### Documentation (this feature)

```text
specs/001-few-shot-extractor/
├── spec.md              # Especificação de requisitos funcionais e critérios
├── plan.md              # Este plano de implementação
├── research.md          # Pesquisa técnica da Fase 0 (decisão multi-turn, token budget)
├── data-model.md        # Entidades, schemas Pydantic e mocks da Fase 1
├── quickstart.md        # Procedimento de teste e validação da Fase 1
├── contracts/           # Contratos e esquemas JSON da Fase 1
│   ├── prompts-interface.json
│   └── extractor-payload.json
└── checklists/
    └── requirements.md  # Checklist de qualidade da especificação
```

### Source Code (repository root)

```text
/home/davig/agents-workspace/agent-clipper/
├── prompts.py           # [NOVO] Constantes de prompt, templates e exemplos Few-Shot
├── orchestrator.py      # [REFATORADO] extractor_node e thinker_node integrados a prompts.py
├── schemas.py           # [INTOCADO] CorteVideo Pydantic schema
├── config.py            # [INTOCADO] Variáveis de ambiente e caminhos
├── ingestion.py         # [INTOCADO] Download e transcrição
├── node_0.py            # [INTOCADO] Fatiamento preventivo
├── editor.py            # [INTOCADO] MoviePy renderização
├── requirements.txt     # [INTOCADO] Dependências fixadas
└── dockerfile           # [INTOCADO] Ambiente isolado
```

**Structure Decision**: Single project layout na raiz do repositório, em conformidade estrita com o ambiente de execução Docker do projeto.

---

## Complexity Tracking

> **Nenhuma violação às regras arquiteturais do `AGENTS.md`. Nenhuma exceção necessária.**

| Regra / Limite | Complexidade Adicionada | Justificativa | Alternativa Mais Simples Rejeitada |
|---|---|---|---|
| Injeção Multi-Turn | 2 mensagens adicionais na lista `messages` | Qwen2.5 exige ancoragem cognitiva para evitar alucinação em prompts longos | Concatenação direta no system prompt (falha em transcrições >3k tokens) |
| Novo módulo `prompts.py` | 1 novo arquivo na raiz | Isola artefatos textuais da lógica de fluxo do LangGraph | Manter strings literais em `orchestrator.py` (polui orquestrador e dificulta manutenção) |

---

## Planned Phases

### Phase 0: Outline & Research *(Concluída)*
- Análise de comportamento do Instructor em `Mode.JSON` sob turnos múltiplos: confirmado que preserva histórico e valida apenas o término do assistente.
- Avaliação de impacto de tokens: ~250 tokens adicionais (< 1.5% da janela), perfeitamente compatível com RTX 3060 12GB VRAM e WSL 8GB RAM.
- Saída: `research.md`.

### Phase 1: Design & Contracts *(Concluída)*
- Modelagem das entidades e dados de mock: `data-model.md`.
- Contratos de interface e payloads: `contracts/prompts-interface.json` e `contracts/extractor-payload.json`.
- Guia de execução rápida e validação: `quickstart.md`.

### Phase 2: Implementation Sequence (Próximo comando: `/speckit.tasks`)
1. **Task 1: Criação de `prompts.py`**
   - Definir `THINKER_SYSTEM_PROMPT` (migrado de `orchestrator.py:181-189`).
   - Definir `EXTRACTOR_SYSTEM_PROMPT_TEMPLATE` (migrado de `orchestrator.py:228-236`).
   - Definir `EXTRACTOR_FEW_SHOT_EXAMPLES: list[dict[str, str]]` com o par `user` (mock transcript + reasoning) e `assistant` (JSON array com schema `CorteVideo`).
2. **Task 2: Refatoração de `orchestrator.py`**
   - Importar `THINKER_SYSTEM_PROMPT`, `EXTRACTOR_SYSTEM_PROMPT_TEMPLATE` e `EXTRACTOR_FEW_SHOT_EXAMPLES` de `prompts.py`.
   - Substituir `system_prompt` inline de `thinker_node` por `THINKER_SYSTEM_PROMPT`.
   - Refatorar `extractor_node` para construir o array `messages` concatenando `[{"role": "system", ...}] + EXTRACTOR_FEW_SHOT_EXAMPLES + [{"role": "user", ...}]`.
   - Garantir que `temperature=0.1`, `MODEL_NAME` e `OLLAMA_BASE_URL` permaneçam inalterados.
3. **Task 3: Verificação & Teste**
   - Executar os 3 passos de teste descritos em `quickstart.md`.
   - Garantir que todos os critérios de aceitação da `spec.md` foram atingidos.
