# Quickstart: Restauração do Motor Determinístico com Motion Design Nativo

**Branch**: `020-deterministic-motion-engine` | **Date**: 2026-11-02 | **Spec**: [spec.md](./spec.md)

---

## 1. Visão Geral

Esta funcionalidade restaura a renderização determinística via `editor_node` e introduz o motor de motion design nativo (`clipper.video.motion_engine`), eliminando a geração estocástica de código por LLM.

Benefícios imediatos:
- **Zero erros de sintaxe:** Nada de falhas de compilação ou Markdown ````python`.
- **Zero cortes de legenda:** Legendas completas cobrindo 100% da duração do vídeo via Pillow.
- **Motion design real:** Gatilhos de animação (`impact`, `zoom_in`, `cut_transition`) geram punch-in, aproximações e cortes de câmera reais nos vídeos.
- **Independência de cotas de LLM:** O processo de renderização não faz chamadas remotas de API.

---

## 2. Execução dos Testes Automatizados

### Rodar testes do motor de motion design e editor:
```bash
PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"
```

### Rodar testes específicos de motion design e sincronização:
```bash
PYTHONPATH=src venv/bin/python -m unittest tests/test_motion_engine.py tests/test_editor.py
```

---

## 3. Execução do Pipeline

### Modo Gemini (Cloud API):
```bash
bash run_pipeline.sh --url "https://www.youtube.com/watch?v=0xbQ0Pq_ssM&t=20s" --provider gemini --model gemini-2.5-flash
```

### Modo Local (Ollama):
```bash
bash run_pipeline.sh --url "https://www.youtube.com/watch?v=0xbQ0Pq_ssM&t=20s" --provider ollama --model qwen2.5:14b
```
