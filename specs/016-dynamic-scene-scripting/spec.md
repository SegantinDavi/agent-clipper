# Feature Specification: Dynamic Scene Scripting via Constrained Decoding

**Feature Branch**: `016-dynamic-scene-scripting`  
**Created**: 2026-10-31  
**Status**: Draft  
**Input**: User description: "Fase 2: Roteirização Dinâmica via Constrained Decoding — expandir o schema Pydantic CorteVideo com cenas (Scene), refatorar prompts do Extrator para dividir falas em cenas lógicas de 2–4 segundos com metáforas visuais e gatilhos de animação."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Cortes com cenas segmentadas e enriquecidas (Priority: P1)

O operador executa o pipeline em um vídeo longo e, ao inspecionar o resultado do nó Extrator, encontra cada corte aprovado subdividido em cenas de 2 a 4 segundos. Cada cena carrega uma metáfora visual sugerida pelo LLM e um gatilho de animação (ex.: zoom, impacto), tornando o work-order de edição final autoexplicativo e reduzindo a subjetividade do editor humano.

**Why this priority**: Sem a segmentação em cenas, o nó de edição não tem informação suficiente para aplicar efeitos visuais cena a cena, o que torna a feature inteira sem valor.

**Independent Test**: Pode ser testado isoladamente executando apenas os nós Thinker → Extractor com uma transcrição mockada e verificando que o JSON resultante contém `scenes` com os campos exigidos.

**Acceptance Scenarios**:

1. **Given** uma transcrição de trecho de 30 s disponível no estado, **When** o nó Extrator processa o raciocínio do Thinker, **Then** cada `CorteVideo` retornado contém uma lista `scenes` com pelo menos 1 item.
2. **Given** um corte de 10 s de fala contínua, **When** o Extrator segmenta as cenas, **Then** cada `Scene` tem duração implícita aproximada de 2 a 4 s (calculável via `start_word` e `end_word`).
3. **Given** qualquer resposta do LLM, **When** a decodificação restrita é aplicada, **Then** todos os campos obrigatórios de `Scene` (`start_word`, `end_word`, `visual_metaphor`, `animation_trigger`) estão presentes e com tipos corretos — sem regex ou `json.loads` manual.

---

### User Story 2 — LLM recebe instruções claras para mapear falas em gatilhos visuais (Priority: P2)

O operador configura o perfil de LLM (Gemini ou Ollama) e dispara o pipeline. O nó Extrator, guiado pelo prompt refatorado, identifica autonomamente onde aplicar metáforas visuais (ex.: "cortina abrindo" ao introduzir novo tema) e gatilhos de animação (ex.: "zoom-in" em palavra-chave de impacto), sem intervenção manual de roteirização.

**Why this priority**: O valor editorial da feature depende da qualidade dos prompts. Um prompt vago produz cenas genéricas; prompts com few-shot exemplos concretos guiam o modelo de forma determinística.

**Independent Test**: Pode ser validado isoladamente executando o nó Extrator com o novo prompt e exemplos de transcrição curta, conferindo que os campos `visual_metaphor` e `animation_trigger` são semanticamente coerentes com o conteúdo da fala.

**Acceptance Scenarios**:

1. **Given** o `EXTRACTOR_SYSTEM_PROMPT_TEMPLATE` atualizado, **When** o LLM processa um raciocínio que menciona uma revelação ou dado surpreendente, **Then** ao menos uma `Scene` possui `animation_trigger` do tipo impacto ou zoom.
2. **Given** o `EXTRACTOR_FEW_SHOT_EXAMPLES` atualizado com mapeamento frase → gatilho, **When** o modelo segue os exemplos, **Then** a escolha de `visual_metaphor` é variada (não repete sempre o mesmo valor) dentro de um mesmo corte de múltiplas cenas.
3. **Given** um perfil Ollama (modelo local) e um perfil Gemini (API), **When** ambos processam a mesma transcrição com o mesmo prompt, **Then** ambos retornam estruturas `CorteVideo` válidas segundo o schema Pydantic — independentemente do backend.

---

### User Story 3 — Cenas persistidas e visíveis na revisão humana (Priority: P3)

O operador acessa a interface de revisão humana (HITL) e visualiza, para cada corte aprovado, as cenas geradas com suas metáforas e gatilhos. Ele pode aprovar o corte inteiro com as cenas propostas ou rejeitá-lo.

**Why this priority**: A visualização das cenas na revisão humana agrega valor ao operador, mas não bloqueia a funcionalidade central. O HITL existente já aceita ou rejeita cortes; as cenas são dados adicionais exibidos.

**Independent Test**: Pode ser testado verificando que o `review.json` serializado pelo nó de aprovação inclui o campo `scenes` de cada corte e que a interface de revisão não quebra ao receber a nova estrutura.

**Acceptance Scenarios**:

1. **Given** cortes com `scenes` preenchidas no estado LangGraph, **When** o `approval_node` serializa o estado para `review.json`, **Then** o arquivo inclui o campo `scenes` de cada corte sem perda de dados.
2. **Given** um `review.json` com cenas, **When** o servidor de revisão carrega o arquivo, **Then** a interface exibe as cenas (mesmo que somente como texto) sem erros de parsing.
3. **Given** uma falha no container seguida de retomada do checkpoint SQLite, **When** o estado é restaurado, **Then** o campo `scenes` de cada corte está íntegro e idêntico ao estado anterior à falha.

---

### Edge Cases

- O que acontece quando o LLM retorna zero cenas para um corte? O sistema falha explicitamente (fail-fast) com erro claro — não aceita lista vazia silenciosamente.
- O que acontece quando `start_word` ou `end_word` são strings vazias? O schema Pydantic rejeita a estrutura imediatamente na validação da resposta do LLM.
- O que acontece quando a duração implícita de uma `Scene` excede 4 s? O pipeline emite log de aviso editorial, mas não rejeita o corte — o threshold é diretriz editorial, não restrição técnica rígida.
- O que acontece quando o campo `animation_trigger` contém valor fora de um vocabulário informal esperado? O schema aceita qualquer string; vocabulário controlado pode ser formalizado em feature futura.
- O que acontece quando o LLM (Ollama) tenta escapar da decodificação restrita e retorna JSON malformado? O `instructor` força nova tentativa automática; se exceder o limite de tentativas, o pipeline falha com erro de decodificação — sem fallback silencioso.
- O que acontece quando a transcrição de entrada não possui timestamps suficientes para segmentar cenas de 2 s? O LLM recebe a transcrição agrupada por frases (conforme regra de otimização de tokens existente) e estima `start_word`/`end_word` por proximidade semântica.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE definir a entidade `Scene` com quatro campos obrigatórios do tipo string: palavra de início (`start_word`), palavra de fim (`end_word`), metáfora visual (`visual_metaphor`) e gatilho de animação (`animation_trigger`).
- **FR-002**: O sistema DEVE incluir uma lista de `Scene` como campo obrigatório em `CorteVideo`, com no mínimo um item por corte.
- **FR-003**: A decodificação restrita via `instructor` + Pydantic DEVE ser o único mecanismo de extração de estrutura do LLM — nenhum uso de regex ou `json.loads` manual é permitido na camada de extração.
- **FR-004**: O `EXTRACTOR_SYSTEM_PROMPT_TEMPLATE` DEVE instruir o LLM a dividir a fala do corte em segmentos lógicos de 2 a 4 segundos, atribuindo uma metáfora visual e um gatilho de animação a cada segmento.
- **FR-005**: O `EXTRACTOR_FEW_SHOT_EXAMPLES` DEVE conter ao menos dois exemplos completos demonstrando o mapeamento frase → `Scene` com valores distintos de `visual_metaphor` e `animation_trigger`.
- **FR-006**: O nó Extrator DEVE retornar a lista completa de `CorteVideo` com cenas preenchidas após processar o raciocínio do nó Thinker, sem alterações na assinatura síncrona dos nós nem no fluxo do grafo LangGraph.
- **FR-007**: O sistema DEVE funcionar com ambos os perfis de LLM (`LLM_PROVIDER=ollama` e `LLM_PROVIDER=gemini`) sem alteração no código de roteamento de provedor.
- **FR-008**: O estado `VideoState` DEVE serializar o campo `scenes` de cada corte de forma transparente pelo `SqliteSaver`, garantindo retomada de checkpoint sem perda de dados de cenas.
- **FR-009**: O pipeline DEVE emitir um erro explícito (não silencioso) quando o LLM retornar uma lista de cenas vazia para qualquer corte.

### Key Entities

- **Scene**: Representa um segmento visual atômico dentro de um corte. Atributos: palavra de início (`start_word`), palavra de fim (`end_word`), metáfora visual sugerida pelo LLM (`visual_metaphor`), gatilho de animação sugerido (`animation_trigger`). Relaciona-se com `CorteVideo` como filha (lista de filhos).
- **CorteVideo**: Representa um corte de vídeo aprovável. Passa a incluir a lista de `Scene` além dos campos temporais e editoriais existentes. Relaciona-se com `VideoState` como elemento da lista de cortes.
- **EXTRACTOR_SYSTEM_PROMPT_TEMPLATE**: Modelo de texto de sistema enviado ao LLM no nó Extrator. Determina o comportamento de segmentação e roteirização cena a cena.
- **EXTRACTOR_FEW_SHOT_EXAMPLES**: Exemplos de referência injetados no prompt para guiar o LLM na escolha de metáforas e gatilhos coerentes com o conteúdo da fala.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% dos cortes produzidos pelo nó Extrator contêm ao menos uma `Scene` com todos os quatro campos obrigatórios preenchidos — verificável pela suite de testes unitários e de contrato.
- **SC-002**: Zero ocorrências de regex ou `json.loads` manual para interpretar respostas do LLM na camada de extração — verificável por análise estática do código modificado.
- **SC-003**: O overhead de tempo de execução do nó Extrator não excede 20% em relação à baseline anterior à feature (medido com transcrição de referência de 5 min no perfil Gemini), dada a adição mínima de campos no schema.
- **SC-004**: A suite completa de testes unitários e de regressão (≥ 172 testes existentes + novos testes da feature) passa sem falhas após a implementação — garantindo zero regressões.
- **SC-005**: O campo `scenes` de cada corte é recuperado de forma íntegra após simulação de crash e retomada do checkpoint SQLite — verificável por teste de integração de persistência.
