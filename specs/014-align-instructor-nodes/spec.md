# Feature Specification: Alinhamento de Concorrência entre Nós LangGraph e Client Instructor

**Feature Branch**: `014-align-instructor-nodes`  
**Created**: 2026-10-30  
**Status**: Draft  
**Input**: User description: "Issue 014: [Arquitetura] Alinhar declaração de nós LangGraph com o client do Instructor"

## Contexto & Visão Geral

Misturar paradigmas de concorrência em pipelines de processamento (por exemplo, misturar funções assíncronas com bibliotecas de comunicação síncronas bloqueantes) acarreta sérios riscos operacionais, incluindo o travamento do *Event Loop*, congelamento de execuções, enfileiramento indevido de requisições e falhas silenciosas decorrentes de corrotinas não aguardadas (*unawaited coroutines*).

No contexto deste projeto — projetado para operar sob restrições físicas severas de hardware (WSL2 com 8GB de RAM e 12GB de VRAM) com processamento em lote e execução sequencial baseada no padrão *Single-Model Cognitive Routing* (Pensador seguido de Extrator) —, a orquestração via máquina de estados baseia-se em um fluxo de execução síncrono, persistido via checkpointer relacional em disco.

Esta especificação formaliza a adoção e blindagem definitiva do **Cenário A (Padrão de Execução Síncrono Estrito)**:
1. Todos os nós da máquina de estados são declarados estritamente como funções síncronas convencionais.
2. O cliente de comunicação com os modelos de linguagem opera em modo síncrono.
3. A camada de decodificação restrita com schemas estruturados (*Instructor*) utiliza exclusivamente a interface síncrona sobre o cliente base.
4. A execução do fluxo é realizada de ponta a ponta sem dependência de laço assíncrono para esses nós, com contratos de testes automatizados impedindo regressões.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Execução Contínua e Previsível do Pipeline (Priority: P1)

Como operador do sistema de geração de clipes, desejo que o processamento das etapas de raciocínio editorial (Pensador) e estruturação de cortes (Extrator) ocorra de maneira determinística e sequencial, garantindo que as requisições ao modelo de linguagem não travem a thread de execução nem congelem o pipeline por conflitos de concorrência.

**Why this priority**: É a funcionalidade central do pipeline de inteligência artificial. Se houver divergência entre a assinatura das funções do grafo e o cliente de comunicação, a execução é interrompida ou bloqueada indefinidamente, impedindo a geração dos vídeos curtos.

**Independent Test**: Pode ser validado de forma isolada executando sequencialmente os nós de pensamento e de extração com um dublê de transporte de rede, confirmando que os dados retornam diretamente como dicionários de estado válidos sem retornar objetos corrotina pendentes.

**Acceptance Scenarios**:

1. **Given** uma transcrição agrupada presente no estado inicial do fluxo, **When** o nó Pensador é executado, **Then** ele processa a análise editorial e retorna imediatamente o raciocínio gerado em formato de dicionário, sem iniciar nem bloquear um laço de eventos assíncrono.
2. **Given** o raciocínio bruto presente no estado do fluxo, **When** o nó Extrator é executado, **Then** ele invoca a camada de decodificação estruturada e retorna a lista de decisões editoriais validadas, liberando a conexão de rede ao término da etapa.
3. **Given** o grafo de orquestração completo compilado, **When** o pipeline é acionado pela chamada de invocação sequencial, **Then** a transição entre todos os estágios ocorre de ponta a ponta sem gerar avisos de corrotinas não aguardadas (*coroutine was never awaited*).

---

### User Story 2 - Blindagem e Verificação de Conformidade Arquitetural (Priority: P2)

Como engenheiro de software e mantenedor do projeto, desejo dispor de validações automatizadas que garantam que nenhum nó do fluxo seja acidentalmente declarado com sintaxe assíncrona e que o cliente de integração não seja substituído por uma variante assíncrona incompatível.

**Why this priority**: Evita regressões arquiteturais silenciosas durante futuras manutenções, refatorações ou adições de novos nós ao grafo.

**Independent Test**: Pode ser testado através de suíte de testes de inspeção estática e reflexiva que audita programaticamente as funções registradas no fluxo de orquestração e a instância de cliente gerada pela fábrica de conexões.

**Acceptance Scenarios**:

1. **Given** os nós registrados no fluxo de orquestração (`download`, `fatiamento`, `transcricao`, `pensador`, `extrator`, `preview`, `approval`, `editor`), **When** auditados via reflexão de funções, **Then** todas as funções retornam confirmação de que são funções síncronas convencionais (não-corrotinas).
2. **Given** a fábrica de clientes de comunicação com o modelo de linguagem, **When** ela é instanciada em qualquer perfil suportado (local ou nuvem), **Then** o objeto gerado pertence estritamente à classe cliente síncrona e não à classe assíncrona.
3. **Given** o encapsulamento de decodificação restrita (*Instructor*), **When** inicializado no nó Extrator, **Then** ele opera sobre o cliente síncrono gerando chamadas bloqueantes diretas na thread de execução.

---

### User Story 3 - Liberação Confiável de Recursos e Conexões de Rede (Priority: P3)

Como operador do sistema em hardware limitado (8GB RAM), desejo que todas as conexões de rede e descritores associados às requisições do modelo de linguagem sejam limpos e fechados imediatamente após o término de cada etapa, mesmo quando ocorrerem falhas de comunicação ou respostas malformadas.

**Why this priority**: Vazamentos de descritores de soquete ou conexões abertas acumuladas degradam a memória do sistema operacional hospedeiro e do container, provocando esgotamento de recursos (*OOM*).

**Independent Test**: Pode ser testado simulando interrupções ou exceções intencionais durante o processamento do modelo e verificando se o método de encerramento da conexão é invocado com sucesso em todos os cenários.

**Acceptance Scenarios**:

1. **Given** uma falha de comunicação ou rejeição de resposta durante a execução do nó Pensador, **When** a exceção é capturada, **Then** a conexão do cliente é fechada determinísticamente antes da propagação do erro.
2. **Given** uma falha de validação de schema estruturado no nó Extrator, **When** o erro é acionado, **Then** a conexão do cliente é fechada determinísticamente no bloco de finalização.
3. **Given** a execução bem-sucedida do nó Pensador ou do nó Extrator, **When** a resposta editorial ou os cortes estruturados são gerados, **Then** a conexão do cliente LLM é encerrada determinísticamente no bloco de finalização (`finally`) antes do retorno dos dados ao fluxo.

---

### Edge Cases

- O que acontece se uma dependência externa instanciar acidentalmente um cliente assíncrono para o *Instructor*? A camada de validação e tipagem estrita rejeita a inicialização, impedindo a atribuição de corrotinas ao estado.
- O que acontece se um nó do grafo for definido com sintaxe assíncrona (`async def`) e executado pela chamada síncrona do grafo? A validação automatizada de integridade acusa a falha antes da entrada em produção, evitando que um objeto corrotina passe sem execução pelo fluxo.
- O que acontece durante a retomada de sessão de revisão humana após um *restart*? O estado do grafo é recuperado do banco de persistência de forma puramente síncrona, retomando a execução do próximo estágio sem dependência de estado de laço assíncrono.
- O que acontece em caso de tempo limite (*timeout*) na resposta do modelo? O cliente síncrono dispara a exceção padrão de timeout após o período configurado (180s), acionando o fechamento da conexão no bloco de finalização e registrando o log apropriado.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE declarar todos os nós registrados na máquina de estados da orquestração estritamente como funções síncronas convencionais (`def`), proibindo o uso de definições assíncronas (`async def`).
- **FR-002**: A fábrica de clientes de comunicação com o modelo de linguagem (`create_llm_client`) DEVE instanciar e retornar exclusivamente uma instância do cliente síncrono padrão (`openai.OpenAI`), com tipagem de retorno explicitamente anotada.
- **FR-003**: O nó Extrator DEVE encapsular o cliente síncrono utilizando o modo de esquema estruturado da biblioteca *Instructor* (`instructor.from_openai`), assegurando que a extração de dados ocorra de forma síncrona e bloqueante na thread corrente.
- **FR-004**: O nó Pensador DEVE invocar a geração de recomendações editoriais diretamente através da interface síncrona do cliente de linguagem.
- **FR-005**: Tanto o nó Pensador quanto o nó Extrator DEVEM garantir o encerramento determinístico das conexões de rede através da invocação explícita do encerramento do cliente (`close()`) em cláusula de finalização garantida (`finally`).
- **FR-006**: A orquestração do grafo DEVE executar o fluxo através da interface de invocação síncrona (`app.invoke`), mantendo alinhamento estrito com os mecanismos de persistência em disco (*checkpointer* SQLite).
- **FR-007**: A suíte de testes do projeto DEVE conter testes de contrato arquitetural que inspecionem reflexivamente as funções do grafo e garantam a ausência de corrotinas na árvore de nós.
- **FR-008**: A suíte de testes DEVE validar que o cliente instanciado é estritamente síncrono e não possui herança ou comportamento de cliente assíncrono.

### Non-Functional Requirements

- **NFR-001 (Consistência de Concorrência)**: Toda a cadeia de execução de inteligência artificial deve operar no paradigma de execução síncrona sequencial, eliminando overhead de laços assíncronos e impedindo travamento de threads.
- **NFR-002 (Preservação de Memória)**: A inicialização e destruição imediata de conexões com o provedor de linguagem não deve manter referências cíclicas ou acumuladores de soquetes abertos, preservando os limites de 8GB de RAM.
- **NFR-003 (Determinismo de Estado)**: O estado compartilhado da máquina de estados (`VideoState`) deve receber apenas estruturas de dados serializáveis e valores primitivos, nunca armazenando objetos temporários de execução assíncrona (como tarefas pendentes ou corrotinas).

### Key Entities

- **Nó Pensador (`thinker_node`)**: Função síncrona responsável pela análise editorial livre da transcrição, gerando raciocínio textual não estruturado.
- **Nó Extrator (`extractor_node`)**: Função síncrona responsável por converter o raciocínio editorial em cortes válidos estruturados sob esquema rígido via decodificação restrita síncrona.
- **Cliente LLM Base**: Objeto de transporte HTTP síncrono configurado com credenciais, tempo limite e endereço do endpoint para o perfil ativo (Ollama local ou API remota).
- **Cliente Instructor**: Camada de adaptação síncrona que força o modelo de linguagem a responder rigorosamente em conformidade com o esquema de dados especificado.
- **Grafo de Estados (`StateGraph`)**: Máquina de estados finita que define a ordem das transições entre os nós do pipeline do início até o término.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% dos nós registrados no grafo de orquestração são confirmados como funções síncronas convencionais via inspeção reflexiva automatizada, sem nenhuma exceção.
- **SC-002**: 0 ocorrências de corrotinas não aguardadas ou avisos de execução assíncrona imperfeita (*RuntimeWarning: coroutine was never awaited*) durante a execução integral dos testes unitários e de integração.
- **SC-003**: 100% dos testes de contrato arquitetural executam com sucesso na suíte de testes automatizada.
- **SC-004**: Em 100% dos cenários de teste (tanto execuções bem-sucedidas quanto execuções com erro proposital injetado), o cliente de comunicação é encerrado determinísticamente sem vazamento de recursos.
