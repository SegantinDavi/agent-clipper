# Contracts: Inserts Animados de Motion Design

**Feature**: `021-animated-motion-inserts`  
**Date**: 2026-11-02  
**Status**: APPROVED  

---

## 1. Contrato: `AssetResolver`

Localização: `src/clipper/video/asset_resolver.py`

### 1.1 Assinatura da Classe e Métodos

```python
class AssetResolver:
    """Carrega o manifest de assets e resolve mapeamentos semânticos para cenas de corte."""

    def __init__(self, assets_dir: Optional[str] = None):
        """
        Inicializa o resolvedor carregando e validando assets/manifest.json.
        Se assets_dir for None, busca no caminho padrão do projeto (PROJECT_ROOT / 'assets').
        Se o diretório ou manifest não existirem, opera em modo degradação graciosa (fallback apenas).
        """
        ...

    def resolve_insert_for_scene(
        self,
        scene: Scene,
        scene_index: int,
        scene_start_time: float,
        scene_duration: float,
        visual_identity: Optional[dict] = None,
    ) -> Optional[ResolvedInsert]:
        """
        Avalia visual_metaphor e animation_trigger da Scene e produz um ResolvedInsert.

        Regras:
        1. Se visual_metaphor for vazia ou "-", retorna None (sem insert para esta cena).
        2. Normaliza o texto da metáfora (remove pontuação e acentos).
        3. Compara com as tags dos assets catalogados.
        4. Se encontrar match: seleciona o asset correspondente (WebM ou PNG/card).
        5. Se NÃO encontrar match: gera um ResolvedInsert procedural baseado em card/pill dinâmico.
        6. A duração do insert é limitada a min(scene_duration, asset.max_duration or 3.0).
        7. Retorna ResolvedInsert com coordenadas pares e zona segura calculada.
        """
        ...
```

---

## 2. Contrato: Renderização e Composição do Insert

Localização: `src/clipper/video/motion_engine.py`

### 2.1 Assinatura de `create_animated_insert_clip`

```python
def create_animated_insert_clip(
    resolved_insert: ResolvedInsert,
    video_size: Tuple[int, int],
    visual_identity: Optional[dict] = None,
) -> VideoClip:
    """
    Constrói um MoviePy VideoClip animado com canal alfa transparente para o insert.

    Entrada:
    - resolved_insert: Dados do insert (caminho do asset, texto, dimensões, posições, curva)
    - video_size: Dimensões (largura, altura) do vídeo base (ex: 1080, 1920)
    - visual_identity: Dicionário de cores e estilos de estilo.json

    Saída:
    - VideoClip com mask habilitada (has_mask=True), duração igual a resolved_insert.duration,
      e offset temporal set_start(resolved_insert.start_time).

    Garantias:
    - Dimensões do clipe são estritamente pares.
    - Se asset for WebM: carrega VideoFileClip com transparência e aplica scale/position.
    - Se asset for PNG ou Procedural: renderiza frame Pillow e aplica animação de pop-in
      elástico (ease_out_back) + micro-flutuação + fade-out.
    - O posicionamento nunca ultrapassa y_max = 0.72 * video_height.
    """
    ...
```

### 2.2 Assinatura de `mix_audio_sfx`

```python
def mix_audio_sfx(
    original_audio: AudioClip,
    inserts: List[ResolvedInsert],
) -> AudioClip:
    """
    Mixa de forma não-destrutiva os efeitos sonoros dos inserts na trilha de áudio original.

    Regras:
    1. Se nenhum insert tiver sfx_path válido, retorna original_audio intacto.
    2. Para cada insert com sfx_path existente:
       - Carrega AudioFileClip.
       - Aplica ganho reduzido (-14 dB / volume 0.35x).
       - Posiciona no tempo com set_start(insert.start_time).
    3. Retorna CompositeAudioClip([original_audio, *sfx_clips]).
    4. Em caso de qualquer exceção ao decodificar SFX, faz log de aviso e retorna original_audio.
    """
    ...
```

---

## 3. Contrato da CLI: `clipper.tools.asset_tool`

Localização: `src/clipper/tools/asset_tool.py`

### 3.1 Comandos Suportados

```bash
# Validar todos os assets existentes em /assets
python -m clipper.tools.asset_tool validate [--assets-dir DIR]

# Saída esperada (stdout):
# [OK] animations/business/chart_up.webm: 512x512, VP9 alpha (yuva420p), 2.50s
# [OK] icons/finance/dollar.png: 512x512, RGBA alpha
# [OK] sfx/whooshes/quick_whoosh.wav: 0.35s, 44100Hz
# [ERROR] animations/test_broken.webm: dimensions 501x500 are not even (width is odd)!
# Summary: 3 valid, 1 invalid.

# Sincronizar / Criar stubs no manifest.json para arquivos novos
python -m clipper.tools.asset_tool sync-manifest [--assets-dir DIR]

# Saída esperada (stdout):
# Discovered 2 new files in assets/
# Added stub for 'animations/tech/ai_brain.webm' (type: animated_video)
# Added stub for 'icons/general/shield.png' (type: icon_with_card)
# assets/manifest.json successfully updated! (Total registered: 12 assets)
```

### 3.2 Código de Saída da CLI
- `0`: Validação bem-sucedida (todos os assets válidos) ou sincronização concluída com sucesso.
- `1`: Erro técnico de validação (existem arquivos com dimensões ímpares, sem canal alfa ou corrompidos).
