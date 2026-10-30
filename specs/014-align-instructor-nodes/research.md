# Phase 0 Research: Alinhamento de Concorrência entre Nós LangGraph e Client Instructor

**Branch**: `014-align-instructor-nodes` | **Date**: 2026-10-30 | **Spec**: [spec.md](spec.md)

---

## 1. Context & Problem Statement

O `agent-clipper` opera sob restrições físicas de hardware severas (WSL2 Ubuntu com 8GB de RAM física e placa NVIDIA GeForce RTX 3060 com 12GB de VRAM). O pipeline converte vídeos longos em cortes verticais em lote de forma determinística e sequencial através de um grafo de estados (`StateGraph`) orquestrado pelo LangGraph e persistido em SQLite via `SqliteSaver`.

No padrão arquitetural de *Cognitive Routing* adotado pelo projeto, a etapa de inteligência artificial é dividida em dois nós sequenciais:
1. **Nó Pensador (`thinker_node`)**: Análise editorial livre da transcrição para identificar trechos virais e estratégias de retenção.
2. **Nó Extrator (`extractor_node`)**: Leitura do raciocínio e aplicação de decodificação restrita (*Constrained Decoding*) via `instructor` acoplado ao schema Pydantic `CortesResponse`.

A mistura acidental de paradigmas síncronos e assíncronos (por exemplo, declaração de nós com `async def`, retorno de corrotinas não aguardadas ou uso de variantes assíncronas do cliente de LLM ou Instructor) pode acarretar sérios problemas:
- Bloqueio e congelamento do *Event Loop* em decorrência de chamadas I/O bloqueantes.
- Emissão de avisos críticos de execução imperfeita (`RuntimeWarning: coroutine was never awaited`).
- Retenção indevida de conexões HTTP e descritores de soquete (*socket descriptor leak*), provocando esgotamento de memória (OOM).
- Incompatibilidade com o checkpointer síncrono do SQLite no disco.

Esta pesquisa detalha as decisões técnicas para blindar o **Cenário A (Padrão de Execução Síncrono Estrito)** de ponta a ponta.

---

## 2. Research Decisions & Analysis

### Topic 1: Concurrency Paradigm in LangGraph for Constrained Hardware

- **Question**: Por que o pipeline deve operar no paradigma puramente síncrono em vez de adotar corrotinas e laço assíncrono (`async def` / `ainvoke`)?
- **Decision**: Adotar exclusivamente execução síncrona sequencial (`def` para todos os nós do grafo e `app.invoke()` para orquestração).
- **Rationale**:
  - O pipeline do `agent-clipper` é inerentemente sequencial e em lote (*batch processing*): Download -> Fatiamento -> Transcrição -> Pensador -> Extrator -> Preview -> Aprovação HITL -> Edição. Não há requisições concorrentes paralelas de múltiplos usuários competindo pelo runtime.
  - Várias das etapas mais pesadas do pipeline são bibliotecas nativas C/C++ ou subprocessos síncronos bloqueantes: FFmpeg (`subprocess.run`), CTranslate2/faster-whisper, e MoviePy v1.0.3. Introduzir um laço assíncrono (`asyncio`) para os nós de IA exigiria despachar operações CPU-bound e C-bound em pools de threads (`run_in_executor`), aumentando a complexidade de debug e o overhead de memória sem ganho real de throughput.
  - A persistência via `SqliteSaver` opera nativamente com conexões SQLite síncronas.
  - O padrão síncrono garante que cada nó receba o `VideoState`, execute até a conclusão ou interrupção (`interrupt()`), e entregue um dicionário puro para transição de estado.
- **Alternatives Considered**:
  - *Pipeline Totalmente Assíncrono (`async def` + `app.ainvoke`)*: Rejeitado. Exigiria reescrever ou envolver nós bloqueantes pesados em executores, aumentaria consumo de memória no WSL2 e traria riscos de race condition no banco de checkpoints SQLite.
  - *Modelo Híbrido (nós síncronos para áudio/vídeo e nós assíncronos para LLM)*: Rejeitado. Misturar nós síncronos e assíncronos no mesmo grafo StateGraph confunde a semântica de invocação do LangGraph e pode gerar corrotinas não resolvidas se o orquestrador invocar via `app.invoke()`.

---

### Topic 2: LLM Client Instantiation & Lifecycle (`create_llm_client`)

- **Question**: Como a fábrica `create_llm_client` deve ser tipada, configurada e instanciada para assegurar execução síncrona e isolamento de recursos?
- **Decision**:
  - A função `create_llm_client() -> openai.OpenAI` deve instanciar exclusivamente o cliente síncrono `openai.OpenAI`.
  - Configuração: `timeout=180.0`, `max_retries=2`, lendo `LLM_API_KEY` e `LLM_BASE_URL` resolvidos por `validate_llm_config()`.
  - A anotação de tipo de retorno deve ser explicitamente `openai.OpenAI`.
  - É expressamente proibido retornar instâncias de `openai.AsyncOpenAI`.
- **Rationale**:
  - O SDK `openai` fornece tanto o cliente síncrono (`OpenAI`) quanto o assíncrono (`AsyncOpenAI`). O cliente síncrono utiliza internamente um pool de conexões HTTP síncrono via `httpx.Client`.
  - O timeout explícito de 180 segundos impede que travamentos de rede no Ollama local ou na API Gemini congelem indefinidamente a thread do pipeline.
  - O cliente é compatível com os dois perfis (`ollama` e `gemini`), respeitando a regra de Single-Model Cognitive Routing do `AGENTS.md`.
- **Alternatives Considered**:
  - *Manter um cliente global compartilhado*: Rejeitado. Em ambientes com memória restrita (8GB) sujeitos a longos períodos ociosos entre processamento de chunks e renderização de vídeo, manter pools de conexão HTTP abertos de forma perpétua gera consumo desnecessário de descritores de arquivo e soquetes. Instanciar e encerrar explicitamente por nó garante liberação imediata.
  - *Retornar `openai.AsyncOpenAI`*: Rejeitado por violar FR-001 e NFR-001.

---

### Topic 3: Structured Decoding via Instructor (`instructor.from_openai`)

- **Question**: Como o cliente Instructor deve ser configurado no nó Extrator para preservar o sincronismo estrito e garantir decodificação restrita?
- **Decision**:
  - Utilizar `instructor.from_openai(raw_client, mode=instructor.Mode.JSON_SCHEMA)`.
  - Passar como argumento base a instância síncrona de `openai.OpenAI`.
  - Invocar a decodificação através de `instructor_client.chat.completions.create(..., response_model=CortesResponse)`.
- **Rationale**:
  - Quando a função `instructor.from_openai` recebe uma instância de `openai.OpenAI`, ela retorna um objeto `instructor.Instructor` (síncrono), cujo método `chat.completions.create` bloqueia síncronamente a thread até receber e validar a resposta contra o schema Pydantic.
  - Se recebesse `openai.AsyncOpenAI`, retornaria `instructor.AsyncInstructor`, exigindo `await` e retornando uma corrotina não aguardada caso chamada síncronamente.
  - O modo `instructor.Mode.JSON_SCHEMA` com `extra_body` contendo `response_format` garante adesão estrita ao schema JSON do Gemini e Ollama, eliminando alucinações e parsing manual (em conformidade com §5 do `AGENTS.md`).
- **Alternatives Considered**:
  - *Utilizar `instructor.patch()`*: Desaconselhado pelas versões modernas do Instructor em favor de `instructor.from_openai()`, que preserva o cliente original e encapsula a camada de validação limpa.
  - *Regex ou json.loads manual*: Estritamente proibido pela Regra 5 do `AGENTS.md`.

---

### Topic 4: Guaranteed Socket/Connection Teardown in `finally` Blocks

- **Question**: Como garantir que todas as conexões HTTP subjacentes sejam fechadas sem vazamento de descritores de soquete, mesmo em cenários de erro ou timeout?
- **Decision**:
  - Tanto no `thinker_node` quanto no `extractor_node`, o cliente LLM base (`raw_client`) deve ser criado imediatamente antes da requisição e encerrado em uma cláusula `finally`:
    ```python
    raw_client = create_llm_client()
    try:
        # requisição ao LLM / Instructor
        ...
    finally:
        raw_client.close()
    ```
- **Rationale**:
  - O método `raw_client.close()` fecha o transporte HTTP subjacente (`httpx.Client.close()`), liberando os sockets TCP e limpando descritores de conexão.
  - O bloco `finally` garante que o encerramento seja executado em todas as situações:
    1. Execução bem-sucedida.
    2. Erro de timeout de rede (`httpx.TimeoutException` / `openai.APITimeoutError`).
    3. Erro de API remota ou serviço local fora do ar (`openai.APIConnectionError`, status 500, etc.).
    4. Erro de validação de schema do Pydantic (`pydantic.ValidationError` ou `instructor.exceptions.InstructorRetryException`).
    5. Exceção inesperada ou interrupção de execução.
- **Alternatives Considered**:
  - *Uso de context manager `with create_llm_client() as raw_client:`*: Funciona no `thinker_node`, mas no `extractor_node` o cliente é repassado ao `instructor.from_openai(raw_client)`. O padrão explícito `raw_client = create_llm_client(); try: ... finally: raw_client.close()` é transparente, inequívoco e garante fechamento uniforme em ambos os nós.

---

### Topic 5: Architectural Contract & Regression Testing Strategy

- **Question**: Como assegurar programaticamente e permanentemente que nenhuma regressão de concorrência ou corrotina passe despercebida?
- **Decision**:
  - Criar uma suíte de testes de contrato dedicada: `tests/test_llm_sync_contract.py`.
  - A suíte deve validar 4 eixos contratuais:
    1. **Auditoria Reflexiva dos Nós do Grafo (FR-001, FR-007, SC-001)**:
       Inspecionar todas as funções registradas em `create_graph()` usando `inspect.iscoroutinefunction()` e `asyncio.iscoroutinefunction()`, assegurando que 100% dos nós sejam funções convencionais síncronas.
    2. **Conformidade da Fábrica do Cliente LLM (FR-002, FR-008)**:
       Verificar que `create_llm_client()` retorna estritamente uma instância de `openai.OpenAI`, que não herda nem pertence a `openai.AsyncOpenAI`, e possui anotação de tipo estrita.
    3. **Conformidade do Cliente Instructor (FR-003)**:
       Verificar que o cliente gerado para o `extractor_node` é uma instância de `instructor.Instructor` (síncrona) e não `instructor.AsyncInstructor`.
    4. **Fechamento Garantido de Recursos em Sucesso e Falha (FR-005, SC-004)**:
       Validar com dublês de transporte que `raw_client.close()` é chamado exatamente 1 vez tanto em execuções normais quanto em falhas provocadas (respostas inválidas, timeouts ou erros de validação).
    5. **Ausência de Corrotinas Não Aguardadas (SC-002)**:
       Executar ciclo de invocação síncrono com captura de warnings, assegurando zero emissões de `RuntimeWarning: coroutine was never awaited`.
- **Rationale**:
  - Testes reflexivos e de contrato previnem que futuros desenvolvedores alterem acidentalmente assinaturas para `async def` ou usem clientes assíncronos.
- **Alternatives Considered**:
  - *Depender apenas de linters estáticos (mypy/flake8)*: Não impede em tempo de execução falhas dinâmicas de instanciação ou de encerramento em blocos `finally`. A auditoria em tempo de teste via `unittest` oferece feedback imediato e determinístico.
