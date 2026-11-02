# Research: Restauração do Motor Determinístico de Renderização com Motion Design Nativo

**Feature Branch**: `020-deterministic-motion-engine`  
**Date**: 2026-11-02  
**Status**: Completed  
**Spec**: [spec.md](./spec.md)

---

## 1. Problema e Diagnóstico Técnico

### 1.1 Por que a geração estocástica de código (`coder_node`) falhou?
1. **Falha de Formatação no Modelo Local (Ollama / Qwen2.5:14b)**:
   - LLMs frequentemente retornam código Python delimitado por blocos Markdown (````python ... ````) mesmo dentro de campos de schemas estruturados.
   - O orquestrador gravava `payload.script_code` diretamente em `render_script.py`, gerando `SyntaxError: invalid syntax` na primeira linha.
2. **Estouro de Tokens e Truncamento de Legendas**:
   - Para evitar estourar a janela de contexto do LLM, o prompt limitava arbitrariamente as palavras em `cut_words[:100]`.
   - Em vídeos com mais de ~25 segundos (>100 palavras), as legendas sumiam abruptamente no meio do vídeo.
   - Em cortes mais longos, o código gerado pelo modelo excedia o limite de tokens de saída da API remota (`finish_reason="length"`), gerando `IncompleteOutputException`.
3. **Instabilidade de Cota e Indisponibilidade de API (Gemini Free Tier)**:
   - Três tentativas de geração no loop de auto-cura esgotavam rapidamente a cota de 5 requisições por minuto (erro 429) ou enfrentavam erros 503, abortando cortes aprovados.
4. **Omissão Completa de Elementos de Vídeo**:
   - O LLM gerava scripts sem legendas (como no corte 3) ou ignorava solenemente as cenas planejadas, pois gerar motion design do zero via MoviePy procedural em um script ad-hoc é excessivamente complexo e não determinístico.

---

## 2. Decisões Arquiteturais e Pesquisa de Tecnologias

### Decisão 1: Restauração do Nó Determinístico (`editor_node`) no Grafo LangGraph
- **Decisão**: Substituir o ciclo estocástico `coder_node -> execution_node -> abort_node` pelo nó síncrono determinístico `editor_node`, chamando diretamente a biblioteca interna `src/clipper/video/editor.py` (`cut_and_format_video`).
- **Rationale**:
  - Elimina 100% dos erros de sintaxe Python, timeouts de compilação, cotas de API e truncamento de tokens.
  - O código de renderização é testado, reproduzível e previsível.
  - Alinhamento total com as regras de AGENTS.md (nós síncronos, DAG bem definido, persistência com SQLite, liberação de VRAM/RAM).
- **Alternativas descartadas**:
  - *Manter `coder_node` corrigindo o prompt e limpando Markdown*: Ainda estaria vulnerável a limites de tokens de saída, truncamento `[:100]`, instabilidade de API remota e falta de determinismo na aplicação de efeitos.

### Decisão 2: Arquitetura do Motor Determinístico de Motion Design (`MotionPlan`)
- **Decisão**: Criar um módulo determinístico de planejamento e aplicação de efeitos de movimento (`motion_engine.py` ou integrado a `src/clipper/video/editor.py`), que analisa as cenas (`Scene`) de cada corte e aplica variações dinâmicas de enquadramento e escala via MoviePy 1.0.3.
- **Mapeamento de Cenas para Tempo Absoluto/Relativo**:
  - Cada cena possui `start_word` e `end_word`. O motor localiza essas palavras na lista de `word_timestamps` do corte para obter os timestamps $(t_{start}, t_{end})$.
  - Se uma palavra não for encontrada de forma exata (ex.: variações de pontuação ou capitalização), utiliza-se comparação normalizada (`unicodedata` / minúsculas sem pontuação) ou interpolação temporal proporcional dentro da duração do corte.
- **Implementação dos Gatilhos de Animação**:
  1. **`impact` (Punch-in / Zoom de Ênfase)**:
     - Aplica uma escala de 1.12x com enquadramento centralizado no locutor ativo durante o intervalo da cena, criando o corte de ênfase visual típico de vídeos curtos modernos.
  2. **`zoom_in` / `slow_zoom` (Aproximação Suave)**:
     - Aplica uma aproximação progressiva suave ao longo do segmento ou enquadramento focado, orientando a atenção do espectador para a fala de revelação.
  3. **`cut_transition` / `whip_pan` (Corte de Alternância)**:
     - Realiza uma alternância de enquadramento (ex.: leve deslocamento lateral do recorte no frame do vídeo original mantendo proporção 9:16), simulando uma troca de câmera dinâmica.
  4. **Metáforas Visuais (`visual_metaphor`)**:
     - Renderiza um pill / lower-third elegante e discreto gerado via Pillow na margem superior do vídeo com o tema da metáfora durante os primeiros 2,5 segundos da cena, sem colidir com as legendas (que ficam na parte inferior a 79% da altura).
- **Rationale**: Concatenação MoviePy via `method="chain"` garante baixo consumo de RAM, sem decodificação redundante de frames na memória.

### Decisão 3: Integridade Total de Legendas Sincronizadas
- **Decisão**: Eliminar qualquer truncamento `[:100]`. O motor determinístico recebe todas as palavras do corte transcritas pelo Whisper (`word_timestamps`) e agrupa-as usando `remap_word_groups` e o plano de corte de pausas (`pause_plans`).
- **Renderização**:
  - Texto renderizado via Pillow (`ImageFont`, `ImageDraw`) com a fonte `Liberation-Sans-Bold`.
  - Cores, stroke e alinhamento extraídos de `visual_identity` (com fallback nos defaults de `config.py`).
  - Posicionamento seguro a 79% da altura com largura máxima de 90% da tela.
- **Rationale**: Pillow evita chamadas externas ao ImageMagick que sofrem com bloqueios de segurança (`@file` policies) e garante que o texto fique 100% nítido e sincronizado.

### Decisão 4: Gerenciamento Rigoroso de Memória (RAM < 2GB e VRAM)
- **Decisão**:
  - Fechar explicitamente cada clip MoviePy intermediário e composto (`clip.close()`).
  - Chamar `del clip` e `gc.collect()` no bloco `finally:` de cada corte.
  - No perfil CUDA, invocar incondicionalmente `release_cuda_memory(cut_id=cut_id)` no término de cada corte no `editor_node`, registrando telemetria em `pipeline.log`.
- **Rationale**: Cumpre rigorosamente a regra 1 e 6 de AGENTS.md, garantindo que WSL2 com 8GB RAM e GPU 12GB operem dentro da capacidade física.

---

## 3. Resumo de Compatibilidade e Sem Quebra de Contratos

| Componente | Estado Anterior (017-019) | Novo Estado (020) | Compatibilidade |
|---|---|---|---|
| LangGraph DAG | `approval -> coder -> execution -> abort/advance` | `approval -> editor_node -> END` | Rota direta e síncrona; `route_approval_outcome` mantido para saída rápida se vazio |
| Aprovação HITL | `approved_cut_ids` / `decision.json` | `approved_cut_ids` / `decision.json` | 100% compatível (0% de renderização para rejeitados) |
| Renderização | Subprocesso com `render_script.py` | Função pura `cut_and_format_video` em `editor_node` | Elimina arquivos ad-hoc quebrados, gera `cut_<id>.mp4` |
| Legendas | Truncadas em 100 palavras ou omitidas | 100% das palavras do corte via Pillow | Restaura funcionamento confiável |
| Motion Design | Inexistente na renderização | Nativo determinístico com `scenes` | Implementa punch-in, zoom e pills visuais |
| Memória VRAM/RAM | `finally:` no execution_node | `finally:` no `editor_node` | Garante desalocação e `release_cuda_memory()` |
