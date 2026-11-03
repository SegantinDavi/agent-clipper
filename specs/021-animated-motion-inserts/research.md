# Technical Research: Inserts Animados de Motion Design (Pipeline Híbrido)

**Feature**: `021-animated-motion-inserts`  
**Date**: 2026-11-02  
**Status**: APPROVED  

---

## 1. Pesquisa e Decisões Técnicas

### Decisão 1: Formato de Vídeo para Animações com Fundo Transparente
- **Decisão**: Adotar **WebM com codec VP9 e canal alfa (yuva420p / yuva444p)** como formato primário, mantendo suporte secundário a **MOV com codec ProRes 4444 ou PNG**.
- **Justificativa**:
  - WebM VP9 com alfa gera arquivos com tamanho entre 100 KB e 600 KB para animações de 2 a 3 segundos (versus 10 MB a 30 MB de ProRes 4444).
  - É suportado nativamente pelo MoviePy 1.0.3 e FFmpeg (`-pix_fmt yuva420p` ou `has_mask=True`).
  - É o formato de exportação padrão de plataformas como LottieFiles, Jitter, After Effects e Canva para web/mobile.
- **Alternativas consideradas**:
  - *GIF*: Rejeitado devido à limitação de 256 cores, bordas serrilhadas (sem gradiente de transparência alfa de 8 bits) e arquivos desproporcionalmente pesados.
  - *Sequência de frames PNG soltos*: Rejeitado por gerar centenas de arquivos na árvore e overhead de leitura I/O no disco.
  - *APNG*: Rejeitado por suporte inconsistente em codecs de vídeo no MoviePy 1.0.3.

---

### Decisão 2: Estrutura do Catálogo e Mapeamento Semântico (`manifest.json`)
- **Decisão**: Utilizar um arquivo central `assets/manifest.json` com schema Pydantic (`AssetManifest`), indexando assets por `id`, tipo (`animated_video`, `icon_with_card`, `sfx`), caminho relativo, lista de `tags` em português normalizadas (sem acentos e minúsculas) e metadados de posicionamento (`upper_third`, `middle_third`).
- **Justificativa**:
  - A busca semântica determinística compara as palavras de `Scene.visual_metaphor` (normalizadas via `normalize_word` do `motion_engine.py`) com as tags do manifest.
  - O cálculo de correspondência dá prioridade a match exato de tag > substring match > match parcial de palavras-chave.
  - Se nenhum asset atingir a pontuação mínima, ocorre **fallback determinístico** para Card Procedural dinâmico, garantindo 100% de estabilidade sem quebras.
- **Alternativas consideradas**:
  - *Embeddings vetoriais / Vector DB local*: Rejeitado por violar o limite de RAM de 8 GB (carregar modelos de embedding como SentenceTransformers adicionaria 500 MB a 1 GB desnecessário na inicialização). A correspondência léxica com sinônimos no manifest é determinística, consome 0 MB adicionais e roda em < 1 ms.

---

### Decisão 3: Motor de Easing Procedural (Física de Animação em Python)
- **Decisão**: Implementar funções matemáticas puras de interpolação temporal no `motion_engine.py` (`ease_out_back`, `spring_overshoot`, `sine_float` e `smooth_fade`), gerando transformações de escala e posição aplicadas via MoviePy (`clip.resize(lambda t: scale_at(t))` e `clip.set_position(lambda t: pos_at(t))`).
- **Curva de Easing Padrão para Pop-in**:
  - Fórmula `ease_out_back(t, s=1.70158)`:
    $$f(t) = 1 + (s + 1) \cdot (t - 1)^3 + s \cdot (t - 1)^2$$
  - Nos primeiros 0.3s, a escala vai de 0.0 até ~1.15 (overshoot sutil) e acomoda em 1.0.
  - Entre 0.3s e `duracao - 0.25s`, aplica micro-flutuação senoidal: $\Delta y = 3 \cdot \sin(2\pi \cdot t \cdot 0.8)$.
  - Nos últimos 0.25s, aplica fade-out com leve subida (*slide up* de 15px).
- **Justificativa**:
  - Reproduz visualmente o estilo de edição dinâmica moderna de criadores de ponta sem exigir dependências externas ou renderizadores de navegador.
  - Código leve, matemático, determinístico e executado em CPU/Pillow com uso mínimo de memória.

---

### Decisão 4: Sincronização e Mixagem de Efeitos Sonoros (SFX)
- **Decisão**: Realizar a mixagem não-destrutiva via MoviePy `CompositeAudioClip` combinando o áudio original do corte com o clipe de áudio do efeito sonoro (`AudioFileClip`), ajustando o ganho (`fx.all.volumex(0.35)` correspondente a ~ -14 dB) e definindo o offset temporal com `.set_start(insert_start_time)`.
- **Justificativa**:
  - Mantém a sincronização de lábios intacta, pois o áudio original é preservado como faixa base contínua.
  - O volume atenuado garante que o efeito sonoro não dispute atenção com a fala do orador.
  - Tratamento de erro gracioso: se o `.wav` não existir ou falhar, o áudio original segue inalterado.

---

### Decisão 5: Arquitetura da Ferramenta Auxiliar (`clipper.tools.asset_tool`)
- **Decisão**: Criar um módulo CLI auto-contido em `src/clipper/tools/asset_tool.py` que utiliza `ffprobe` (via subprocess ou PyAV) e `Pillow` para auditar a pasta `/assets`.
- **Funcionalidades**:
  1. `validate`:
     - Inspeciona se WebM possui codec `vp9`/`vp8` com stream de alfa (`pix_fmt` com 'a', ex: `yuva420p`).
     - Inspeciona dimensões e emite erro se forem ímpares (`w % 2 != 0` ou `h % 2 != 0`).
     - Inspeciona PNG se possui modo `RGBA` ou transparência.
     - Inspeciona WAV se taxa de amostragem é compatível (44.1kHz / 48kHz) e duração < 1.5s.
  2. `sync-manifest`:
     - Escaneia a árvore de arquivos de `/assets`, compara com o `manifest.json` existente e insere stubs para novos arquivos sem apagar tags já editadas.
- **Justificativa**:
  - Resolve a dor de cabeça do usuário ao baixar assets da web, garantindo fail-fast antes de iniciar pipelines de renderização longos.
