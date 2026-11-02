# Feature Specification: Inserts Animados de Motion Design (Pipeline Híbrido)

**Feature Branch**: `021-animated-motion-inserts`  
**Created**: 2026-11-02  
**Status**: Draft  
**Input**: User description: "vamos com a opção A então, pode começar a gerar as especificações com o número 021 e crie uma nova branch." (Opção A: Pipeline Híbrido com diretório /assets, clipes transparentes com canal alfa, cards/ícones procedurais com curvas de easing e sincronização sonora).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Catálogo de Assets Estruturado e Resolução Semântica (Priority: P1) 🎯 MVP

Como criador de conteúdo, quero que o pipeline busque automaticamente no diretório `/assets` elementos visuais e sonoros compatíveis com o roteiro de cada cena (`Scene.visual_metaphor`), para que cada corte tenha elementos visuais relevantes ao assunto abordado sem intervenção manual.

**Why this priority**: É o alicerce do recurso. Sem uma estrutura padronizada de assets (`assets/manifest.json`) e uma lógica determinística de resolução semântica, o motor de vídeo não sabe quais arquivos carregar ou como mapear as metáforas sugeridas pelo LLM.

**Independent Test**: Executar o resolvedor de assets passando diferentes termos de metáfora visual (ex: `"lucro"`, `"alerta"`, `"ideia"`, `"termo_desconhecido"`) e verificar que os metadados do asset correto são retornados com fallback consistente para card procedural quando não houver clipe pré-renderizado.

**Acceptance Scenarios**:

1. **Given** um catálogo em `/assets` com `manifest.json` contendo tags para finanças, **When** o extrator gerar uma cena com `visual_metaphor: "investimento e ações"`, **Then** o sistema deve resolver o asset correspondente (ex: `animations/business/chart_growth.webm`) com caminho válido e metadados de posicionamento.
2. **Given** uma metáfora visual que não possui correspondência direta nem por tag no catálogo, **When** o resolvedor processar a cena, **Then** o sistema deve realizar fallback para um card procedural dinâmico (com ícone genérico ou badge estilizada) sem quebrar o pipeline.
3. **Given** a ausência do arquivo físico referenciado no `manifest.json`, **When** o resolvedor tentar carregá-lo, **Then** o sistema deve registrar um warning no log e utilizar o fallback procedural de forma graciosa.

---

### User Story 2 - Composição de Inserts com Curvas de Easing e Transparência Alfa (Priority: P2)

Como espectador de vídeos curtos, quero que os inserts visuais surjam na tela com animações fluidas de aceleração (pop-in elástico, flutuação e fade-out) ou em clipes com fundo transparente, para que o vídeo tenha padrão profissional de retenção sem cobrir as legendas nem o rosto do orador.

**Why this priority**: O apelo visual de vídeos curtos depende de dinâmica e fluidez. Elementos estáticos que aparecem de forma abrupta geram desinteresse; animações com aceleração e posicionamento seguro garantem acabamento estético e retenção de público.

**Independent Test**: Renderizar um corte contendo 2 cenas com gatilhos de insert e verificar que os elementos entram com aceleração suave, permanecem pelo tempo configurado da cena sem bloquear a zona segura das legendas (y > 75%), e respeitam dimensões pares.

**Acceptance Scenarios**:

1. **Given** um asset de vídeo transparente em formato WebM (VP9 + alpha) associado a uma cena, **When** o editor renderizar o corte, **Then** o clipe deve ser sobreposto mantendo canal alfa (transparência real) no quadrante seguro superior/médio do vídeo.
2. **Given** um insert procedural (ícone PNG + texto do roteiro), **When** a cena iniciar, **Then** o elemento deve realizar animação de pop-in com curva de elasticidade/easing (escala de 0.0 para ~1.15 estabilizando em 1.0 em ~0.3s) e saída suave ao final do intervalo da cena.
3. **Given** qualquer resolução de vídeo vertical (ex: 1080x1920), **When** os inserts forem gerados e compostos, **Then** as dimensões de largura e altura de cada camada e subclip devem ser estritamente pares para prevenir falhas de codec H.264.

---

### User Story 3 - Sincronização Não-Destrutiva de Efeitos Sonoros (SFX) (Priority: P3)

Como criador de conteúdo, quero que a entrada dos inserts visuais seja acompanhada por efeitos sonoros sutis (`pop.wav`, `whoosh.wav`), para que a transição visual ganhe impacto sensorial e retenha a atenção do espectador.

**Why this priority**: A associação visual-auditiva eleva drasticamente a percepção de valor do conteúdo. No entanto, é P3 porque o vídeo ainda é plenamente assistível sem o áudio auxiliar.

**Independent Test**: Processar um corte com insert animado e verificar que a faixa de áudio final contém o áudio original da fala perfeitamente mixado com o efeito sonoro no timestamp exato da entrada visual, sem distorção ou dessincronização de lábios.

**Acceptance Scenarios**:

1. **Given** um insert com efeito sonoro associado no `manifest.json` (ex: `sfx/whooshes/quick_whoosh.wav`), **When** o vídeo for composto, **Then** o áudio do SFX deve ser mixado na trilha principal exatamente no segundo de início do insert visual.
2. **Given** um corte com múltiplas cenas e inserts, **When** os SFX forem mixados, **Then** o volume do efeito deve ser normalizado e sutil (ex: -12dB a -18dB abaixo da fala principal) para não ofuscar a clareza da voz.
3. **Given** a ausência do arquivo de áudio SFX ou falha na sua leitura, **When** o editor compor a faixa de som, **Then** o vídeo deve continuar com a trilha de voz intacta sem interromper a renderização.

---

### User Story 4 - Governança de Recursos e Fallback Resiliente (Priority: P4)

Como operador do sistema em hardware restrito (WSL2 8GB RAM / RTX 3060 12GB VRAM), quero que o processamento de inserts animados desaloque recursos intermediários de memória de forma contínua e mantenha o consumo sob controle rigoroso, para que vídeos de até 3 minutos rodem sem estourar a memória.

**Why this priority**: O sistema opera próximo ao limite físico de hardware. Se a sobreposição de múltiplas camadas de vídeo e animação acumular frames não coletados na memória RAM, o container sofrerá Out Of Memory (OOM).

**Independent Test**: Renderizar corte de 60 segundos com 4 inserts animados e verificar que o pico de memória RAM do processo permanece < 2 GB e que o flush de VRAM (`release_cuda_memory()`) ocorre no bloco `finally:` de cada corte.

**Acceptance Scenarios**:

1. **Given** a renderização de um corte vertical com inserts alfa e áudio mixado, **When** a exportação finalizar (ou falhar), **Then** todos os clips e compósitos intermediários devem ser fechados (`.close()`) e desalocados da RAM.
2. **Given** o perfil de execução CUDA, **When** cada corte finalizar a renderização, **Then** a memória VRAM deve ser liberada incondicionalmente via `release_cuda_memory()`.

---

### Edge Cases

- **Ausência total da pasta `/assets`**: O sistema detecta a ausência, emite aviso no log e utiliza o fallback procedural de pills simples já existente no `motion_engine.py`.
- **Duração do insert maior que a duração da cena**: Se um clipe animado WebM tiver 4 segundos e a cena durar apenas 2 segundos, o sistema recorta a animação ou acelera suavemente para caber no intervalo sem estourar a cena seguinte.
- **Sobreposição com legendas**: O posicionamento vertical do insert nunca deve ultrapassar a coordenada `y = 72%` da altura do vídeo vertical (onde residem as legendas a 79%).
- **Arquivos de vídeo WebM corrompidos**: Se um arquivo de asset falhar durante a decodificação pelo MoviePy/FFmpeg, o sistema captura a exceção, registra erro no log e prossegue renderizando a cena sem o insert visual corrompido.
- **Inserções simultâneas ou muito próximas (< 1.5s)**: Se duas cenas consecutivas tiverem gatilhos de insert, o sistema aplica um intervalo mínimo de respiro ou suprime o segundo insert para evitar poluição visual na tela.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE disponibilizar uma estrutura de diretórios padronizada em `/assets` contendo pastas para `animations/`, `icons/`, `sfx/` e um arquivo de metadados `manifest.json`.
- **FR-002**: O sistema DEVE fornecer um resolvedor semântico (`AssetResolver`) capaz de selecionar o arquivo de asset mais compatível com base nas propriedades `visual_metaphor` e `animation_trigger` de cada `Scene`.
- **FR-003**: O resolvedor de assets DEVE implementar fallback determinístico para card procedural (Pill/Badge estilizado com ícone genérico e texto do roteiro) caso nenhum asset específico seja encontrado.
- **FR-004**: O sistema DEVE suportar sobreposição de clipes de vídeo transparentes com canal alfa (formato WebM com codec VP9/VP8 alfa ou MOV ProRes 4444 com alpha).
- **FR-005**: O sistema DEVE fornecer gerador de animação procedural em Python aplicando curvas matemáticas de *easing* (ex: *ease-out-back* para efeito de pop-in elástico, flutuação senoidal suave e fade-out) para ícones e cards estáticos.
- **FR-006**: O sistema DEVE garantir que todas as camadas compostas possuam dimensões pares de largura e altura antes da codificação H.264 pelo FFmpeg.
- **FR-007**: O sistema DEVE posicionar os inserts em zonas seguras de enquadramento vertical 9:16 (terço superior entre 12% e 35% da altura), sem colidir com as legendas (localizadas entre 75% e 85%).
- **FR-008**: O sistema DEVE mixar efeitos sonoros auxiliares (`.wav` curto) no timestamp exato de entrada de cada insert visual, com volume balanceado e respeitando a faixa principal de fala.
- **FR-009**: O sistema DEVE encerrar explicitamente instâncias de `VideoClip`, `AudioClip` e arrays intermediários após a geração de cada corte, mantendo pico de memória RAM < 2 GB.
- **FR-010**: O sistema DEVE manter o disparo incondicional de `release_cuda_memory()` ao término de cada corte no perfil CUDA dentro do bloco `finally:`.

### Key Entities

- **AssetMetadata**: Representa a entrada catalogada no `manifest.json` com campos como `id`, `file`, `type` (`animated_video`, `icon_with_card`, `sfx`), `tags` (lista de palavras-chave para busca semântica), `default_position` (`upper_third`, `middle_third`, `lower_third`) e `default_sfx` (caminho relativo do áudio opcional).
- **ResolvedInsert**: Entidade que encapsula o plano de execução do insert para uma cena específica, contendo: `scene_index`, `start_time`, `duration`, `asset_path`, `asset_type`, `position_coordinates`, `sfx_path` e `animation_curve`.
- **EasingProfile**: Configuração matemática da curva de aceleração temporal para animação procedural (parâmetros de escala inicial, pico de overshoot, tempo de estabilização e amortecimento).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% dos cortes aprovados que possuam cenas com metáforas visuais mapeadas recebem inserts animados (pré-renderizados ou procedurais) sem falhas de decodificação ou travamentos.
- **SC-002**: A resolução de assets a partir da metáfora visual da cena ocorre em tempo de execução de forma determinística em menos de 10 milissegundos por cena.
- **SC-003**: 100% dos inserts animados respeitam a zona segura vertical 9:16, apresentando zero sobreposição com a caixa delimitadora das legendas transcritas.
- **SC-004**: A renderização com inserts animados e mixagem de SFX adiciona menos de 25% de tempo extra ao processamento total de cada corte em comparação com a renderização base.
- **SC-005**: O consumo máximo de memória RAM durante a composição de vídeo com múltiplas camadas permanece estritamente inferior a 2 GB.
- **SC-006**: A suíte completa de testes de regressão do projeto mantém 100% de taxa de aprovação com zero regressões em todas as suítes existentes.
