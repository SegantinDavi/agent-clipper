# Quickstart: Validação do Alinhamento Síncrono dos Nós LangGraph e Instructor

**Branch**: `014-align-instructor-nodes` | **Date**: 2026-10-30 | **Spec**: [spec.md](spec.md)

---

## 1. Visão Geral

Este guia orienta a execução dos testes de conformidade arquitetural da feature `014-align-instructor-nodes`, validando que:
1. Todos os nós do grafo de orquestração são estritamente funções síncronas convencionais.
2. O cliente OpenAI retornado pela fábrica é síncrono e não possui herança assíncrona.
3. O cliente Instructor é o wrapper síncrono `instructor.Instructor`.
4. Os recursos de rede e sockets são encerrados determinísticamente via `close()` em blocos `finally`.
5. A execução do pipeline não emite avisos de corrotinas não aguardadas.

---

## 2. Executando os Testes de Contrato Arquitetural

Execute a suíte de testes dedicada que audita programaticamente as funções do grafo, os clientes de LLM e o encerramento de conexões:

```bash
# Executar a nova suíte de testes de contrato arquitetural
PYTHONPATH=src venv/bin/python -m unittest tests/test_instructor_sync_contract.py -v
```

Saída esperada:
```text
test_thinker_node_sync_execution_returns_raciocinio_bruto ... ok
test_extractor_node_sync_execution_returns_cortes_finais ... ok
test_graph_invocation_emits_zero_coroutine_warnings ... ok
test_all_graph_nodes_are_synchronous_functions ... ok
test_create_llm_client_returns_strict_sync_openai_instance ... ok
test_extractor_node_uses_sync_instructor_instance ... ok
test_thinker_node_deterministic_cleanup_on_success_and_error ... ok
test_extractor_node_deterministic_cleanup_on_success_and_error ... ok

----------------------------------------------------------------------
Ran 8 tests in ...s

OK
```

---

## 3. Executando a Regressão Completa do Projeto

Valide que todos os testes existentes do projeto continuam passando sem regressões:

```bash
# Execução da suíte completa de testes unitários e de integração
PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"
```

---

## 4. Verificação Rápida via Python Interativo

Você pode verificar manualmente a assinatura dos nós e o tipo do cliente no terminal:

```bash
PYTHONPATH=src venv/bin/python -c "
import inspect
from clipper.core.orchestrator import create_graph, create_llm_client, thinker_node, extractor_node
import openai
import instructor

# 1. Validar nós
graph = create_graph()
for name, node in graph.nodes.items():
    fn = node.runnable.func if hasattr(node, 'runnable') else node
    assert not inspect.iscoroutinefunction(fn), f'Node {name} is async!'
print('✓ Todos os nós do grafo são síncronos.')

# 2. Validar cliente base
client = create_llm_client()
assert isinstance(client, openai.OpenAI)
assert not isinstance(client, openai.AsyncOpenAI)
client.close()
print('✓ create_llm_client() retorna openai.OpenAI síncrono.')

# 3. Validar Instructor
inst_client = instructor.from_openai(openai.OpenAI(api_key='mock', base_url='http://localhost:11434/v1'))
assert isinstance(inst_client, instructor.Instructor)
assert not isinstance(inst_client, getattr(instructor, 'AsyncInstructor', type(None)))
print('✓ instructor.from_openai() retorna instructor.Instructor síncrono.')
"
```
