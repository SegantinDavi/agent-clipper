# Quickstart: Inserts Animados de Motion Design

**Feature**: `021-animated-motion-inserts`  
**Date**: 2026-11-02  

---

## 1. Visão Geral

A funcionalidade **021** introduz inserts animados de motion design baseados no pipeline híbrido:
1. **Catálogo de Assets (`/assets`)**: Biblioteca de clipes WebM transparentes (canal alfa), ícones PNG/SVG e efeitos sonoros WAV, mapeados pelo `assets/manifest.json`.
2. **Resolução Semântica (`AssetResolver`)**: Mapeia automaticamente as metáforas das cenas para o asset mais adequado, com fallback para cards procedurais dinâmicos com física elástica.
3. **Animação com Easing (`motion_engine.py`)**: Entradas com curvas de aceleração *ease-out-back* (pop-in elástico), micro-flutuação e fade-out, sem cobrir as legendas.
4. **Mixagem de Áudio SFX**: Efeitos sonoros sutis mixados na entrada dos inserts visuais.
5. **Ferramenta Auxiliar CLI (`asset_tool.py`)**: Valida canal alfa, dimensões pares e sincroniza o `manifest.json`.

---

## 2. Comandos de Validação e Testes

### 2.1 Executar Testes Unitários e de Integração

```bash
# Executar testes do resolvedor de assets e catálogo
PYTHONPATH=src venv/bin/python -m unittest tests/test_asset_resolver.py

# Executar testes da ferramenta CLI de validação de assets
PYTHONPATH=src venv/bin/python -m unittest tests/test_asset_tool.py

# Executar testes do motor de composição de inserts animados e SFX
PYTHONPATH=src venv/bin/python -m unittest tests/test_motion_inserts.py

# Executar suíte completa de regressão do projeto
PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"
```

---

## 3. Uso da Ferramenta Auxiliar CLI

### 3.1 Validar integridade dos assets existentes

```bash
PYTHONPATH=src venv/bin/python -m clipper.tools.asset_tool validate
```
*Garante que todos os vídeos possuem canal alfa real, dimensões estritamente pares e áudios com duração controlada.*

### 3.2 Sincronizar novos arquivos no `manifest.json`

Após salvar novos arquivos `.webm` ou `.png` nas pastas de `/assets`:

```bash
PYTHONPATH=src venv/bin/python -m clipper.tools.asset_tool sync-manifest
```
*Gera stubs automáticos no `assets/manifest.json` prontos para preenchimento de palavras-chave.*

---

## 4. Execução do Pipeline com Motion Inserts

Execute normalmente o pipeline via Docker ou shell local:

```bash
# Execução local com perfil Ollama (Qwen2.5 local)
bash run_pipeline.sh --provider ollama --url "https://www.youtube.com/watch?v=SEU_VIDEO"

# Execução com perfil Gemini API
bash run_pipeline.sh --provider gemini --model gemini-2.5-flash --url "https://www.youtube.com/watch?v=SEU_VIDEO"
```

Durante o nó de edição (`editor_node`), os cortes aprovados terão os inserts animados e mixagem de SFX aplicados de forma determinística, com auditoria em `pipeline.log` e descarte automático de memória intermediária.
