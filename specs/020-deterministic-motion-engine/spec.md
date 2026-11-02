# Feature Specification: Restauração do Motor Determinístico de Renderização com Motion Design Nativo

**Feature Branch**: `020-deterministic-motion-engine`  
**Created**: 2026-11-02  
**Status**: Draft  
**Input**: User description: "Restauração do motor deterministico e implementar os gatilhos de motion design."

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Renderização Determinística e Confiável de Cortes Aprovados (Priority: P1)

O operador aprova um ou mais cortes na interface de revisão humana (HITL). Em vez de delegar a criação de scripts Python a cada execução para um LLM (que sofre com alucinações de formatação Markdown, limites de tokens de contexto e instabilidade de cotas remotas), o pipeline utiliza o motor de renderização determinístico (`editor_node` acoplado ao `cut_and_format_video`). Cada corte aprovado é processado de ponta a ponta com 100% de previsibilidade, gerando o arquivo MP4 final no formato vertical 9:16 com dimensões pares, codec H.264 e perfil de áudio compatível.

**Why this priority**: É a funcionalidade central e o objetivo crítico do pipeline. Sem uma renderização determinística e estável, os vídeos falham na geração, corrompem sintaxe ou são abortados por timeouts/erros de API.

**Independent Test**: Pode ser testado injetando um `VideoState` contendo cortes aprovados e palavras transcritas, verificando que o nó de edição gera os arquivos de vídeo correspondentes sem acionar prompts de LLM nem gerar arquivos temporários `render_script.py` malformados.

**Acceptance Scenarios**:
1. **Given** um corte aprovado pelo operador no HITL, **When** o nó de edição determinística processa o corte, **Then** o arquivo final `cut_<id>.mp4` é gerado em `/app/output/<id>/` (ou `/app/output/`) com formato 9:16 (ex: 1080x1920) e dimensões estritamente pares.
2. **Given** um corte rejeitado no `decision.json`, **When** o motor de renderização executa, **Then** ele não realiza renderização para o corte rejeitado (0% de processamento para cortes não aprovados), registrando log informativo da exclusão.
3. **Given** que todos os cortes foram rejeitados ("Rejeitar todos"), **When** a rota pós-aprovação é avaliada, **Then** o pipeline transiciona diretamente para o encerramento em menos de 5 segundos sem tentar renderizar nenhum arquivo.

---

### User Story 2 — Legendas Sincronizadas e Contínuas do Início ao Fim (Priority: P2)

O espectador assiste ao corte vertical gerado e observa legendas estilizadas que acompanham a fala de forma ininterrupta do primeiro ao último segundo do vídeo. Nenhuma palavra é cortada arbitrariamente por limites de tokens de prompt (`[:100]`), e a renderização tipográfica é feita com Pillow e a fonte `Liberation-Sans-Bold`, respeitando as cores e tamanhos definidos na identidade visual (`visual_identity`).

**Why this priority**: Legendas dinâmicas são fundamentais para retenção em vídeos curtos (Shorts/TikTok/Reels). O truncamento ou desaparecimento das legendas no meio do vídeo quebra totalmente o produto final.

**Independent Test**: Pode ser testado executando a renderização de um corte de duração superior a 40 segundos (>150 palavras) e verificando que existem legendas geradas tanto no primeiro quarto quanto no último segundo do corte.

**Acceptance Scenarios**:
1. **Given** um corte longo com mais de 100 palavras (ex: 172 palavras em 43s), **When** o motor determinístico renderiza o vídeo, **Then** 100% das palavras do corte são mapeadas e exibidas nas legendas, sem sumir aos 25 segundos.
2. **Given** uma configuração de pausas ativada (`shorten_pauses`), **When** as pausas são encurtadas, **Then** as legendas são remapeadas estritamente com base no plano de pausas (`remap_word_groups`), mantendo o sincronismo labial.
3. **Given** a identidade visual carregada (`visual_identity`), **When** as legendas são desenhadas, **Then** os parâmetros de cor primária, contorno (stroke) e posição relativa (center_x, center_y) são aplicados com exatidão matemática via Pillow.

---

### User Story 3 — Execução de Gatilhos de Motion Design por Cena (Priority: P3)

Durante a reprodução do corte, o vídeo responde dinamicamente aos momentos-chave da narrativa mapeados nas cenas (`Scene`). Quando um gatilho de animação está associado a uma cena (como `zoom_in`, `slow_zoom`, `impact` ou `cut_transition`), o motor determinístico aplica o efeito visual correspondente no vídeo base durante o intervalo de tempo exato da cena, aumentando a retenção sem alucinações e sem estourar os limites de memória da máquina.

**Why this priority**: O motion design enriquece o dinamismo visual dos cortes e transforma o produto em um vídeo curto de alta retenção, aproveitando a inteligência de roteirização já implementada no nó Extrator.

**Independent Test**: Pode ser testado fornecendo um corte com cenas contendo gatilhos específicos (`impact`, `zoom_in`) e verificando que os filtros visuais de enquadramento e escala são aplicados determinísticamente nos intervalos de tempo de cada cena.

**Acceptance Scenarios**:
1. **Given** uma cena com gatilho `impact`, **When** o corte é renderizado, **Then** um enquadramento aproximado tipo punch-in (escala de ênfase de 1.1x a 1.15x) é aplicado no trecho correspondente à cena.
2. **Given** uma cena com gatilho `zoom_in` ou `slow_zoom`, **When** o corte é renderizado, **Then** uma aproximação progressiva suave ou enquadramento focado é mantido durante o intervalo da cena.
3. **Given** uma cena com gatilho `cut_transition` ou `whip_pan`, **When** o corte é renderizado, **Then** ocorre uma alternância de enquadramento (corte seco de ângulo/escala) que marca a virada de tema entre as cenas.
4. **Given** uma cena com metáfora visual planejada (`visual_metaphor`), **When** configurada a exibição visual de contexto, **Then** uma cartela ou lower-third sutil e estilizada pode ser sobreposta no início da cena, respeitando as margens de segurança e a identidade visual.

---

### User Story 4 — Preservação Estrita de Memória RAM e VRAM (Priority: P4)

O operador executa o pipeline em ambiente com restrição de hardware (WSL2 com 8GB de RAM e placa RTX 3060 com 12GB VRAM). O motor determinístico garante que cada clipe temporário seja desalocado, invocando `.close()`, `del` e `gc.collect()`, mantendo o consumo de pico de RAM abaixo de 2GB. No perfil CUDA, a liberação de cache de VRAM (`release_cuda_memory`) é acionada incondicionalmente no encerramento de cada corte com telemetria no arquivo de log.

**Why this priority**: A máquina hospedeira falhará por OOM (Out Of Memory) se a memória de frames do MoviePy ou o cache de tensores da GPU não forem limpos deterministicamente a cada corte.

**Independent Test**: Pode ser testado medindo o uso de memória durante a renderização sequencial de múltiplos cortes, verificando que não há acúmulo contínuo de RAM e que `pipeline.log` registra as métricas de liberação.

**Acceptance Scenarios**:
1. **Given** múltiplos cortes aprovados, **When** cada corte finaliza sua renderização, **Then** os buffers de MoviePy são fechados e `gc.collect()` é executado, prevenindo memory leak.
2. **Given** o perfil de LLM Gemini com Whisper em CUDA, **When** a renderização de cada corte termina, **Then** `release_cuda_memory()` é disparado no bloco `finally:`.

---

## Edge Cases

- **Corte sem cenas definidas ou lista de cenas vazia**: O motor determinístico renderiza o corte vertical com enquadramento padrão (centralizado ou foco no locutor) e legendas integrais, emitindo aviso informativo sem abortar o corte.
- **Cena com `start_word` ou `end_word` não encontradas exatamente na transcrição**: O motor calcula a estimativa de tempo proporcional da cena dentro do corte ou utiliza o timestamp da palavra foneticamente mais próxima, garantindo que o vídeo não quebre.
- **Cenas sobrepostas ou fora de ordem temporal**: O motor ordena as cenas por tempo de início e ajusta as durações para evitar intervalos negativos ou sobreposição conflitante de efeitos de escala.
- **Vídeo de entrada com resolução não padrão ou dimensões ímpares**: O cálculo de corte 9:16 força estritamente números pares em largura e altura antes de alimentar o MoviePy (`if width % 2 != 0: width -= 1`).
- **Nenhum corte aprovado no `decision.json`**: O grafo LangGraph desvia a execução diretamente para o término (`END`), sem instanciar renderizadores nem subprocessos.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE utilizar o nó determinístico de renderização (`editor_node` / `cut_and_format_video`) para produzir os vídeos finais, desativando a geração de scripts ad-hoc via LLM (`coder_node` + `execution_node` + loop de auto-cura).
- **FR-002**: O motor de renderização DEVE processar estritamente os cortes identificados em `approved_cut_ids` / `approved_ids` de `decision.json` e do `VideoState`.
- **FR-003**: O motor de renderização DEVE alimentar o gerador de legendas com 100% da lista de `word_timestamps` do corte, sendo estritamente proibido qualquer truncamento artificial no volume de palavras (como `[:100]`).
- **FR-004**: O sistema DEVE sincronizar as legendas utilizando `remap_word_groups` e o plano de corte de pausas (`pause_plans`), desenhando os textos através de Pillow e fontes do pacote `fonts-liberation` (ex.: `Liberation-Sans-Bold`).
- **FR-005**: O motor DEVE interpretar a lista de `scenes` de cada corte aprovado e traduzir seus gatilhos de animação (`animation_trigger`) em efeitos determinísticos de edição de vídeo (ex.: `zoom_in`, `slow_zoom`, `impact`, `cut_transition`).
- **FR-006**: O gatilho `impact` DEVE aplicar um punch-in de escala (ex.: 1.1x a 1.15x centrado na área de foco) na cena correspondente.
- **FR-007**: O gatilho `zoom_in` ou `slow_zoom` DEVE aplicar uma aproximação de enquadramento dinâmica ou contínua ao longo da duração da cena.
- **FR-008**: O gatilho `cut_transition` DEVE alternar o enquadramento (corte de escala ou alternância de posição) entre as cenas adjacentes.
- **FR-009**: O motor DEVE opcionalmente renderizar um elemento visual sutil (badge / lower-third estilizado) indicando o tema da `visual_metaphor` da cena, alinhado com a identidade visual (`visual_identity`).
- **FR-010**: O sistema DEVE garantir que todas as dimensões de vídeo recortadas e redimensionadas sejam estritamente pares, com proporção 9:16 (ex.: 1080x1920) e parâmetros de exportação FFmpeg `-pix_fmt yuv420p` e `-profile:v main`.
- **FR-011**: O sistema DEVE garantir desalocação de buffers intermediários (`.close()`, `del`, `gc.collect()`) e disparo de `release_cuda_memory()` no perfil CUDA ao final de cada corte em bloco `finally:`.
- **FR-012**: O grafo LangGraph DEVE manter execução síncrona estrita (`def`), sem chamadas assíncronas no StateGraph, registrando o caminho dos arquivos gerados em `rendered_video_paths`.

---

### Key Entities

- **editor_node**: Nó síncrono do LangGraph responsável por orquestrar a renderização determinística dos cortes aprovados.
- **cut_and_format_video**: Função principal do módulo de edição (`src/clipper/video/editor.py`) que compõe o vídeo 9:16, cortes de pausa, legendas Pillow e motion design.
- **MotionDesignEngine / MotionPlan**: Camada ou estrutura responsável por mapear as `Scene` de cada corte em intervalos temporais e gerar os subclips com os efeitos visuais de escala e enquadramento.
- **Scene**: Estrutura Pydantic com `start_word`, `end_word`, `visual_metaphor` e `animation_trigger`.
- **VideoState**: Dicionário de estado do LangGraph contendo `video_path`, `cortes_finais`, `approved_cut_ids`, `word_timestamps`, `visual_identity` e `rendered_video_paths`.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% dos cortes aprovados geram arquivos MP4 válidos e reproduzíveis em `/app/output/` sem falhas de sintaxe, erros de token ou abortos por cota de LLM.
- **SC-002**: 100% das palavras faladas em cada corte aprovado possuem legendas sincronizadas desde o início até o término do corte, com zero interrupções prematuras por truncamento.
- **SC-003**: 100% dos cortes contendo `scenes` exibem variações dinâmicas de enquadramento ou escala (motion design) nos momentos definidos pelos gatilhos de animação (`impact`, `zoom_in`, `cut_transition`).
- **SC-004**: O consumo de pico de memória RAM durante a renderização permanece estritamente inferior a 2 GB por corte.
- **SC-005**: 0% de renderização ou subprocessos executados para cortes rejeitados ou quando a decisão do usuário for "Rejeitar todos" (tempo de encerramento < 5 segundos).
- **SC-006**: A suíte de testes automatizados passa com 0 regressões em relação aos contratos existentes de HITL, checkpoints SQLite e liberação de VRAM.
