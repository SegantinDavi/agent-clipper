# Feature Specification: Few-Shot Prompting no Extractor Node

**Feature Branch**: `001-few-shot-extractor`
**Created**: 2026-10-23
**Status**: Draft
**Input**: User description: "Few-Shot Prompting no `extractor_node` para ancoragem cognitiva do Qwen2.5:14b via exemplos injetados no `system_prompt`, resolvendo falhas de formatação em transcrições longas de podcasts."

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Extração robusta de cortes em podcasts longos (Priority: P1)

O sistema processa a transcrição agrupada de um podcast longo (>60 min) e, ao chegar no nó extrator, retorna a lista de cortes devidamente preenchida sem abortar o pipeline. O Qwen2.5 "lembra" do formato correto de saída porque o `system_prompt` inclui um exemplo concreto (entrada → saída JSON) antes de receber os dados reais.

**Why this priority**: É o problema raiz que causa falha total do pipeline. Sem isso, nenhum Reels/Short é gerado.

**Independent Test**: Pode ser testado isoladamente fornecendo um `VideoState` com `transcript_grouped` e `raciocinio_bruto` populados manualmente, verificando se `cortes_finais` retorna uma lista válida de `CorteVideo` sem exceção.

**Acceptance Scenarios**:

1. **Given** um `VideoState` com `raciocinio_bruto` e `transcript_grouped` populados com conteúdo de podcast longo (>3000 tokens), **When** o `extractor_node` é invocado, **Then** retorna `cortes_finais` com pelo menos 1 `CorteVideo` válido e a execução não lança exceção.
2. **Given** a lista `messages` montada no `extractor_node`, **When** inspecionada em runtime, **Then** contém a mensagem de sistema seguida pelos turnos de ancoragem Few-Shot (`user`/`assistant`) antes do prompt do usuário real.
3. **Given** os exemplos Few-Shot injetados no payload de `messages` (entrada mock e saída JSON esperada), **When** o modelo processa a requisição, **Then** a saída gerada é diretamente deserializável pelo `instructor` sem fallback manual.

---

### User Story 2 — Centralização e manutenibilidade dos prompts (Priority: P2)

Todos os templates de prompt e os exemplos Few-Shot residem no módulo `prompts.py` na raiz do projeto. Um engenheiro pode evoluir os exemplos ou ajustar os templates sem tocar na lógica de orquestração em `orchestrator.py`.

**Why this priority**: Separação de responsabilidades. Templates de prompt são artefatos de domínio, não lógica de controle de fluxo.

**Independent Test**: Pode ser testado importando `prompts.py` isoladamente e verificando que `EXTRACTOR_FEW_SHOT_EXAMPLES`, `EXTRACTOR_SYSTEM_PROMPT_TEMPLATE` e `THINKER_SYSTEM_PROMPT` existem e são estruturas não-vazias (`str` para templates e `list[dict]` para exemplos).

**Acceptance Scenarios**:

1. **Given** o arquivo `prompts.py` na raiz do projeto, **When** `from prompts import EXTRACTOR_FEW_SHOT_EXAMPLES` é executado, **Then** importa sem erro e a variável é uma lista com pelo menos 1 par de turnos de exemplo (`user` e `assistant`).
2. **Given** `orchestrator.py`, **When** inspecionado, **Then** não contém nenhuma string literal de prompt; todos os prompts são referências a constantes de `prompts.py`.
3. **Given** que a constante `EXTRACTOR_FEW_SHOT_EXAMPLES` é modificada em `prompts.py`, **When** o pipeline é executado, **Then** o novo conteúdo é injetado na lista de `messages` sem qualquer alteração na lógica de `orchestrator.py`.

---

### User Story 3 — Estabilidade do pipeline pós-refatoração (Priority: P3)

Após a refatoração, o pipeline completo (`download → fatiamento → transcricao → pensador → extrator → editor`) continua funcionando de ponta a ponta sem regressões na configuração da API local (Ollama, modelo, temperatura) e na estrutura do `VideoState`.

**Why this priority**: Validar que a refatoração não quebrou nenhum nó ou parâmetro de conexão existente.

**Independent Test**: Pode ser verificado executando o grafo completo com um vídeo curto de teste e confirmando que todos os nós completam e os arquivos de saída são gerados em `/app/output`.

**Acceptance Scenarios**:

1. **Given** `orchestrator.py` refatorado, **When** `create_graph()` é chamado, **Then** o grafo compila sem erro e todos os 6 nós estão presentes.
2. **Given** os parâmetros de API (`OLLAMA_BASE_URL`, `MODEL_NAME`, `temperature`), **When** comparados antes e depois da refatoração, **Then** são idênticos — nenhum valor é alterado.
3. **Given** o `VideoState`, **When** comparado antes e depois da refatoração, **Then** o `TypedDict` é idêntico — nenhum campo novo é adicionado ou removido.

---

### Edge Cases

- O que acontece se `EXTRACTOR_FEW_SHOT_EXAMPLES` for uma lista vazia (`[]`)? O nó deve continuar funcionando (degradando graciosamente para zero-shot), sem lançar exceção.
- O que acontece se o exemplo Few-Shot contiver timestamps que colidem com a transcrição real? O modelo deve ignorar os timestamps do exemplo e usar apenas os da transcrição real no `user_prompt`.
- O que acontece se `raciocinio_bruto` for uma string muito curta (< 50 chars)? O nó já valida isso e levanta `ValueError` antes de chamar o LLM.
- O que acontece se o Qwen2.5 retornar uma lista vazia de cortes (schema válido, mas sem elementos)? O `editor_node` emite um `logger.warning` e retorna `{}` sem renderizar nada — comportamento já existente e não alterado.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE criar o arquivo `prompts.py` na raiz do projeto, contendo:
  - A constante `THINKER_SYSTEM_PROMPT: str` com o prompt completo do nó pensador (migrado de `orchestrator.py`).
  - A constante `EXTRACTOR_SYSTEM_PROMPT_TEMPLATE: str` com o prompt do nó extrator (migrado de `orchestrator.py`), definindo as regras inegociáveis de corte e schema sem interpolação de strings.
  - A constante `EXTRACTOR_FEW_SHOT_EXAMPLES: list[dict]` contendo turnos conversacionais mock de entrada de transcrição/raciocínio (`user`) e a saída JSON esperada no formato do schema `CorteVideo` (`assistant`).

- **FR-002**: A constante `EXTRACTOR_FEW_SHOT_EXAMPLES` DEVE seguir o padrão de "alternância de turnos" (User/Assistant turns) compatível com o formato de `messages` da API OpenAI-compatible do Ollama, de forma que os exemplos sejam injetados como mensagens adicionais (não concatenados na string do `system_prompt`).

- **FR-003**: O `extractor_node` em `orchestrator.py` DEVE ser refatorado para importar `prompts.py` e montar a lista `messages` com a sequência: `[system_message] + few_shot_messages + [user_message]`, onde `few_shot_messages` é derivado de `EXTRACTOR_FEW_SHOT_EXAMPLES`.

- **FR-004**: O `thinker_node` em `orchestrator.py` DEVE ter seu `system_prompt` inline substituído pela referência `THINKER_SYSTEM_PROMPT` importada de `prompts.py`.

- **FR-005**: Os parâmetros de API (`base_url=OLLAMA_BASE_URL`, `api_key="ollama"`, `model=MODEL_NAME`, `temperature=0.1`) usados no `extractor_node` NÃO DEVEM ser alterados.

- **FR-006**: Nenhuma lógica de retry, fallback de exceção ou validação via `re` (Regex) DEVE ser adicionada ao `extractor_node`. A robustez é obtida exclusivamente via Few-Shot no prompt.

- **FR-007**: O `VideoState` (`TypedDict` em `orchestrator.py`) NÃO DEVE ser modificado — nenhum campo novo é necessário para esta feature.

### Key Entities

- **`prompts.py`**: Módulo de constantes de prompt. Contém os 3 artefatos textuais do domínio LLM: `THINKER_SYSTEM_PROMPT`, `EXTRACTOR_SYSTEM_PROMPT_TEMPLATE` e `EXTRACTOR_FEW_SHOT_EXAMPLES`. Não importa nenhum módulo do projeto (sem dependências circulares).
- **`EXTRACTOR_FEW_SHOT_EXAMPLES`**: Variável do tipo `list[dict]` contendo dicionários `{"role": "user"|"assistant", "content": str}` prontos para serem inseridos na lista de `messages` da chamada ao LLM. Cada par User/Assistant simula uma entrada de transcrição curta e a saída JSON correspondente ao schema `CorteVideo`.
- **`CorteVideo`**: Schema Pydantic existente em `schemas.py` (campos: `title: str`, `start_time: float`, `end_time: float`). NÃO DEVE ser alterado.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O pipeline processa com sucesso uma transcrição de podcast de 60+ minutos e gera pelo menos 1 arquivo de vídeo Shorts em `/app/output` sem abortar com exceção no `extractor_node`.
- **SC-002**: O `extractor_node` retorna uma lista com pelo menos 1 `CorteVideo` válido (campos `title`, `start_time`, `end_time` preenchidos e `end_time > start_time`) em 100% das execuções de teste com `raciocinio_bruto` não-vazio.
- **SC-003**: A inspeção do log `pipeline.log` após uma execução bem-sucedida NÃO contém nenhuma linha de erro com nível `ERROR` ou `CRITICAL` originada do `extractor_node`.
- **SC-004**: O arquivo `prompts.py` pode ser importado de forma isolada (sem dependências do projeto) e todas as 3 constantes são strings/listas não-vazias verificáveis com um simples `assert`.
- **SC-005**: O tempo de execução do `extractor_node` não aumenta em mais de 5% em relação à implementação anterior (o overhead é apenas o tamanho extra do prompt com os exemplos).

---

## Assumptions

1. O formato de `messages` com múltiplos turnos `user`/`assistant` é suportado pelo endpoint `/api/chat` do Ollama local em `OLLAMA_BASE_URL`. Esta é a forma padrão da API OpenAI-compatible e não requer configuração adicional.
2. Os exemplos Few-Shot usam timestamps fictícios (e.g., `120.0s` - `175.0s`) que NÃO existem na transcrição real. O modelo deve entender que os exemplos são demonstrações de formato, não dados reais.
3. A temperatura do `extractor_node` permanece em `0.1` (já definida) para minimizar a criatividade e maximizar a adesão ao formato demonstrado pelos exemplos.
4. O `instructor` com `mode=instructor.Mode.JSON` é totalmente compatível com o fluxo de `messages` multi-turno — a injeção ocorre sobre a lista de mensagens antes do `instructor` interceptar a chamada.
