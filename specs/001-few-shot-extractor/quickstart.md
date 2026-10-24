# Quickstart: Few-Shot Prompting no Extractor Node

**Feature**: `001-few-shot-extractor`  
**Date**: 2026-10-23  

---

## 1. Verificação de Isolamento do Módulo de Prompts

Execute o comando abaixo para confirmar que `prompts.py` está na raiz do projeto, não possui dependências circulares e exporta todas as constantes no formato correto:

```bash
python -c "
from prompts import (
    THINKER_SYSTEM_PROMPT,
    EXTRACTOR_SYSTEM_PROMPT_TEMPLATE,
    EXTRACTOR_FEW_SHOT_EXAMPLES,
)

assert isinstance(THINKER_SYSTEM_PROMPT, str) and len(THINKER_SYSTEM_PROMPT) > 50
assert isinstance(EXTRACTOR_SYSTEM_PROMPT_TEMPLATE, str) and len(EXTRACTOR_SYSTEM_PROMPT_TEMPLATE) > 50
assert isinstance(EXTRACTOR_FEW_SHOT_EXAMPLES, list) and len(EXTRACTOR_FEW_SHOT_EXAMPLES) >= 2
assert all('role' in m and 'content' in m for m in EXTRACTOR_FEW_SHOT_EXAMPLES)
print('✓ prompts.py validado com sucesso!')
"
```

---

## 2. Verificação de Compilação do Grafo LangGraph

Confirme que a refatoração do `orchestrator.py` não quebrou a estrutura do DAG:

```bash
python -c "
from orchestrator import create_graph

workflow = create_graph()
graph = workflow.compile()
nodes = list(workflow.nodes.keys())
expected = ['download', 'fatiamento', 'transcricao', 'pensador', 'extrator', 'editor']
assert all(n in nodes for n in expected), f'Nós ausentes: {set(expected) - set(nodes)}'
print('✓ Grafo LangGraph compilado com os 6 nós esperados!')
"
```

---

## 3. Teste Isolado do Extrator (Mock State)

Para testar o `extractor_node` com Ollama rodando localmente (`qwen2.5:14b`):

```bash
python -c "
from orchestrator import extractor_node
from schemas import CorteVideo

mock_state = {
    'transcript_grouped': (
        '[10.00 - 45.00] A inteligência artificial não vai substituir os programadores, '
        'mas os programadores que usam inteligência artificial vão substituir os que não usam. '
        'Essa é a regra mais importante da nova década da tecnologia.'
    ),
    'raciocinio_bruto': (
        'O trecho entre 10s e 45s tem um contraste marcante e frase de impacto viral sobre o futuro '
        'da programação. Ótimo gancho de retenção de 35 segundos.'
    ),
}

result = extractor_node(mock_state)
cortes = result.get('cortes_finais', [])
assert len(cortes) > 0, 'Nenhum corte retornado'
assert all(isinstance(c, CorteVideo) for c in cortes), 'Item não é CorteVideo'
print(f'✓ Extrator validado com sucesso! {len(cortes)} cortes extraídos:')
for c in cortes:
    print(f'  - {c.title} ({c.start_time}s - {c.end_time}s)')
"
```
