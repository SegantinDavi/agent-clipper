# Interface Contract: LangGraph Nodes & Instructor Synchronous Execution

**Branch**: `014-align-instructor-nodes` | **Date**: 2026-10-30 | **Spec**: [spec.md](../spec.md)

---

## 1. Module: `clipper.core.orchestrator`

### Contract 1: `create_llm_client() -> openai.OpenAI`

#### Description
Fábrica de instanciação do cliente base de comunicação com o LLM configurado (Ollama local ou Gemini API via endpoint compatível OpenAI).

#### Signature
```python
def create_llm_client() -> openai.OpenAI: ...
```

#### Preconditions
- `validate_llm_config()` valida a presença de credenciais e integridade das URLs.
- Variáveis de ambiente ou padrões (`LLM_API_KEY`, `LLM_BASE_URL`) devem estar carregados.

#### Postconditions
1. Retorna uma instância concreta da classe `openai.OpenAI`.
2. O objeto retornado **NUNCA** herda ou pertence à classe `openai.AsyncOpenAI`.
3. Os métodos de requisição (e.g. `client.chat.completions.create`) são chamadas bloqueantes convencionais que retornam objetos `ChatCompletion` (não corrotinas ou futures).
4. O cliente possui o método `close() -> None` para encerramento síncrono dos transportes HTTP.

---

### Contract 2: `thinker_node(state: VideoState) -> dict`

#### Description
Nó 4 do grafo LangGraph. Realiza a análise editorial livre da transcrição agregada presente no estado, produzindo raciocínio estratégico sobre momentos de retenção.

#### Signature
```python
def thinker_node(state: VideoState) -> dict: ...
```

#### Preconditions
- `state` é um dicionário compatível com `VideoState`.
- `state["transcript_grouped"]` contém string não vazia com a transcrição agregada.

#### Postconditions
1. A função é declarada estritamente com `def` convencional.
2. `inspect.iscoroutinefunction(thinker_node) is False`.
3. A chamada ao cliente LLM é realizada de forma síncrona.
4. O método `raw_client.close()` é chamado exatamente uma vez em cláusula `finally`, garantindo fechamento tanto em sucesso quanto em falhas (`Exception`).
5. Retorna dicionário contendo a chave `"raciocinio_bruto"` com valor `str` não vazio.
6. Em caso de falha ou resposta vazia, lança a exceção apropriada (`ValueError`, `RuntimeError`, `APIError`) após fechar a conexão.

---

### Contract 3: `extractor_node(state: VideoState) -> dict`

#### Description
Nó 5 do grafo LangGraph. Consome o raciocínio livre gerado pelo pensador e a transcrição, aplicando decodificação restrita síncrona com `instructor` para extrair cortes estruturados no schema `CortesResponse`.

#### Signature
```python
def extractor_node(state: VideoState) -> dict: ...
```

#### Preconditions
- `state["transcript_grouped"]` contém a transcrição agregada.
- `state["raciocinio_bruto"]` contém string não vazia gerada pelo `thinker_node`.

#### Postconditions
1. A função é declarada estritamente com `def` convencional (`inspect.iscoroutinefunction(extractor_node) is False`).
2. O cliente `raw_client` gerado por `create_llm_client()` é síncrono.
3. A instância criada por `instructor.from_openai(raw_client, mode=instructor.Mode.JSON_SCHEMA)` é estritamente do tipo `instructor.Instructor` (síncrona), e **NUNCA** `instructor.AsyncInstructor`.
4. A extração via `instructor_client.chat.completions.create` bloqueia síncronamente a thread corrente e retorna uma instância tipada de `CortesResponse`.
5. O método `raw_client.close()` é executado determinísticamente em cláusula `finally`, garantindo liberação dos recursos de rede tanto em caso de sucesso quanto em caso de erro.
6. Retorna dicionário contendo a chave `"cortes_finais"` com uma lista de dicionários correspondentes aos cortes validados (`[cut.model_dump() for cut in cortes]`).

---

### Contract 4: `create_graph() -> StateGraph`

#### Description
Constrói o grafo acíclico dirigido (`StateGraph`) sequencial do pipeline com todos os nós.

#### Signature
```python
def create_graph() -> StateGraph: ...
```

#### Verification Rules
1. Todos os nós registrados via `workflow.add_node(name, func)` devem ser funções síncronas convencionais:
   ```python
   for node_name, node_spec in workflow.nodes.items():
       fn = node_spec.runnable.func if hasattr(node_spec, "runnable") else node_spec
       assert not inspect.iscoroutinefunction(fn)
       assert not asyncio.iscoroutinefunction(fn)
   ```
2. Nenhuma transição ou invocação deve depender de corrotinas.
3. A invocação do grafo compilado (`app = workflow.compile(...)`) utiliza `app.invoke(initial_state, config=...)`, garantindo execução síncrona sem necessidade de laço `asyncio`.

---

## 2. Architectural Assertions & Test Criteria

| ID | Alvo | Invariante de Teste | Critério de Sucesso |
|---|---|---|---|
| **AC-01** | Todos os nós do grafo | `inspect.iscoroutinefunction(node) == False` | 100% dos nós síncronos |
| **AC-02** | `create_llm_client` | `isinstance(client, openai.OpenAI)` e `not isinstance(client, openai.AsyncOpenAI)` | Cliente estritamente síncrono |
| **AC-03** | Instructor wrapper | `isinstance(instructor_client, instructor.Instructor)` | Wrapper síncrono sobre OpenAI |
| **AC-04** | `thinker_node` cleanup | `client.close()` invocado no sucesso e na exceção | Chamada unitária verificada via Mock |
| **AC-05** | `extractor_node` cleanup | `client.close()` invocado no sucesso e na exceção | Chamada unitária verificada via Mock |
| **AC-06** | Execução ponta a ponta | Invocação síncrona sem emissão de `RuntimeWarning: coroutine was never awaited` | 0 warnings assíncronos |
