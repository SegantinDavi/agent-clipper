"""Motor determinístico de motion design para agent-clipper.

Mapeia as cenas (Scene) de cada corte e aplica variações dinâmicas de enquadramento,
escala (punch-in, zoom suave) e alternância de ângulo via MoviePy 1.0.3 e Pillow.
"""

from __future__ import annotations

import logging
import math
import os
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    AudioClip,
    AudioFileClip,
    CompositeAudioClip,
    ImageClip,
    VideoClip,
    VideoFileClip,
    concatenate_videoclips,
)

from clipper.core.schemas import AssetType, CorteVideo, Scene
from clipper.video.asset_resolver import EasingProfile, ResolvedInsert

logger = logging.getLogger(__name__)

# Fatores padrão de escala para os gatilhos de animação
SCALE_FACTORS = {
    "impact": 1.12,         # Punch-in / Zoom de impacto
    "zoom_in": 1.08,        # Aproximação suave
    "slow_zoom": 1.08,      # Aproximação contínua
    "cut_transition": 1.05, # Troca sutil de ângulo
    "whip_pan": 1.05,       # Transição dinâmica
    "standard": 1.0,        # Enquadramento neutro
}

OFFSET_FACTORS = {
    "cut_transition": 0.04, # Alternância leve no eixo X
    "whip_pan": 0.04,
}


@dataclass
class SceneInterval:
    scene_index: int
    start_time: float      # Timestamp absoluto de início no vídeo original (s)
    end_time: float        # Timestamp absoluto de término no vídeo original (s)
    rel_start: float       # Início relativo ao começo do corte (s)
    rel_end: float         # Fim relativo ao começo do corte (s)
    duration: float        # Duração deste intervalo (s)
    animation_trigger: str # Gatilho normalizado ('impact', 'zoom_in', etc.)
    visual_metaphor: str   # Metáfora visual descrita para a cena
    scale_factor: float = 1.0
    crop_offset_x: float = 0.0


@dataclass
class MotionPlan:
    cut_id: int | str | None
    cut_start: float
    cut_end: float
    duration: float
    intervals: list[SceneInterval] = field(default_factory=list)


def normalize_word(text: str) -> str:
    """Remove pontuação e acentos, retornando palavra em minúsculas para matching resiliente."""
    if not text:
        return ""
    # Decompõe acentos e caracteres especiais
    decomposed = unicodedata.normalize("NFKD", text)
    clean = "".join(
        c.lower() for c in decomposed
        if not unicodedata.combining(c) and (c.isalnum() or c.isspace())
    )
    return clean.strip()


def _find_word_timestamp(
    target_word: str,
    words: list[dict],
    default_time: float,
    prefer_end: bool = False,
) -> float:
    """Busca timestamp de palavra alvo dentro da lista de palavras transcritas."""
    target_clean = normalize_word(target_word)
    if not target_clean or not words:
        return default_time

    best_match = None
    for w in words:
        w_clean = normalize_word(w.get("word", ""))
        if w_clean == target_clean or target_clean in w_clean or w_clean in target_clean:
            best_match = w
            break

    if best_match is not None:
        return float(best_match.get("end" if prefer_end else "start", default_time))

    return default_time


def build_motion_plan(
    corte: CorteVideo | dict,
    words: list[dict],
    duration: float,
) -> MotionPlan:
    """Constrói um plano contíguo de motion design cobrindo 100% da duração do corte."""
    if duration <= 0:
        raise ValueError(f"Cut duration must be strictly positive, got {duration}")

    if isinstance(corte, dict):
        cut_id = corte.get("id")
        cut_start = float(corte.get("start_time", 0.0))
        cut_end = float(corte.get("end_time", cut_start + duration))
        scenes_raw = corte.get("scenes") or []
    else:
        cut_id = getattr(corte, "id", None)
        cut_start = float(corte.start_time)
        cut_end = float(corte.end_time)
        scenes_raw = getattr(corte, "scenes", []) or []

    # Se não houver cenas, retorna plano padrão
    if not scenes_raw:
        default_interval = SceneInterval(
            scene_index=0,
            start_time=cut_start,
            end_time=cut_end,
            rel_start=0.0,
            rel_end=duration,
            duration=duration,
            animation_trigger="standard",
            visual_metaphor="",
            scale_factor=1.0,
            crop_offset_x=0.0,
        )
        return MotionPlan(
            cut_id=cut_id,
            cut_start=cut_start,
            cut_end=cut_end,
            duration=duration,
            intervals=[default_interval],
        )

    # Filtra palavras pertencentes ao corte
    cut_words = [
        w for w in words
        if isinstance(w, dict) and cut_start <= w.get("start", 0.0) <= cut_end + 0.5
    ]

    raw_intervals: list[SceneInterval] = []
    num_scenes = len(scenes_raw)
    proportional_duration = duration / num_scenes

    for idx, scene in enumerate(scenes_raw):
        if isinstance(scene, dict):
            s_word = scene.get("start_word", "")
            e_word = scene.get("end_word", "")
            trigger = (scene.get("animation_trigger") or "standard").strip().lower()
            metaphor = scene.get("visual_metaphor", "")
        else:
            s_word = getattr(scene, "start_word", "")
            e_word = getattr(scene, "end_word", "")
            trigger = (getattr(scene, "animation_trigger", "") or "standard").strip().lower()
            metaphor = getattr(scene, "visual_metaphor", "")

        default_start = cut_start + (idx * proportional_duration)
        default_end = cut_start + ((idx + 1) * proportional_duration)

        abs_start = _find_word_timestamp(s_word, cut_words, default_start, prefer_end=False)
        abs_end = _find_word_timestamp(e_word, cut_words, default_end, prefer_end=True)

        if abs_end <= abs_start:
            abs_end = abs_start + proportional_duration

        rel_start = max(0.0, min(duration, abs_start - cut_start))
        rel_end = max(rel_start + 0.1, min(duration, abs_end - cut_start))

        # Determina parâmetros de escala e offset
        scale = SCALE_FACTORS.get(trigger, 1.0)
        offset_x = OFFSET_FACTORS.get(trigger, 0.0)
        if offset_x != 0.0 and idx % 2 != 0:
            offset_x = -offset_x

        raw_intervals.append(
            SceneInterval(
                scene_index=idx,
                start_time=abs_start,
                end_time=abs_end,
                rel_start=rel_start,
                rel_end=rel_end,
                duration=rel_end - rel_start,
                animation_trigger=trigger,
                visual_metaphor=metaphor,
                scale_factor=scale,
                crop_offset_x=offset_x,
            )
        )

    # Ordena intervalos por início relativo
    raw_intervals.sort(key=lambda s: s.rel_start)

    # Assegura contiguidade e cobertura 100% de 0.0 até duration
    clean_intervals: list[SceneInterval] = []
    current_time = 0.0

    for i, interval in enumerate(raw_intervals):
        interval.rel_start = current_time

        if i == len(raw_intervals) - 1:
            interval.rel_end = duration
        else:
            next_start = raw_intervals[i + 1].rel_start
            if next_start <= current_time + 0.2:
                # Evita cena com duração nula
                interval.rel_end = current_time + max(1.0, (duration - current_time) / (len(raw_intervals) - i))
            else:
                interval.rel_end = min(duration, next_start)

        interval.duration = max(0.1, interval.rel_end - interval.rel_start)
        interval.start_time = cut_start + interval.rel_start
        interval.end_time = cut_start + interval.rel_end
        current_time = interval.rel_end
        clean_intervals.append(interval)

    # Garante que o último termina em duration
    if clean_intervals:
        clean_intervals[-1].rel_end = duration
        clean_intervals[-1].duration = duration - clean_intervals[-1].rel_start
        clean_intervals[-1].end_time = cut_end

    return MotionPlan(
        cut_id=cut_id,
        cut_start=cut_start,
        cut_end=cut_end,
        duration=duration,
        intervals=clean_intervals,
    )


def apply_motion_design(
    clip: VideoClip,
    motion_plan: MotionPlan,
    visual_identity: dict | None = None,
) -> VideoClip:
    """Aplica transformações de escala e enquadramento aos subclips correspondentes a cada cena."""
    if not motion_plan or not motion_plan.intervals:
        return clip

    # Se for uma única cena estática sem efeitos, retorna o clip diretamente
    if (
        len(motion_plan.intervals) == 1
        and motion_plan.intervals[0].scale_factor == 1.0
        and motion_plan.intervals[0].crop_offset_x == 0.0
    ):
        return clip

    w, h = clip.size
    subclips = []

    for interval in motion_plan.intervals:
        # Extrai subclip relativo
        sub_start = max(0.0, min(clip.duration, interval.rel_start))
        sub_end = max(sub_start, min(clip.duration, interval.rel_end))

        if sub_end <= sub_start:
            continue

        scene_clip = clip.subclip(sub_start, sub_end)

        scale = interval.scale_factor
        offset_x = interval.crop_offset_x

        if scale != 1.0 or offset_x != 0.0:
            # Calcula recorte de zoom mantendo aspecto 9:16 e dimensões pares
            crop_w = int(w / scale)
            crop_h = int(h / scale)
            if crop_w % 2 != 0:
                crop_w -= 1
            if crop_h % 2 != 0:
                crop_h -= 1

            # Ponto central com deslocamento lateral se houver
            x_center = (w / 2.0) + (w * offset_x)
            y_center = h / 2.0

            x1 = int(x_center - crop_w / 2.0)
            y1 = int(y_center - crop_h / 2.0)

            # Limita dentro do quadro
            x1 = max(0, min(w - crop_w, x1))
            y1 = max(0, min(h - crop_h, y1))
            if x1 % 2 != 0:
                x1 -= 1
            if y1 % 2 != 0:
                y1 -= 1

            # Recorta e redimensiona de volta para (w, h)
            cropped = scene_clip.crop(x1=x1, y1=y1, width=crop_w, height=crop_h)
            transformed = cropped.resize(newsize=(w, h))
            subclips.append(transformed)
        else:
            subclips.append(scene_clip)

    if not subclips:
        return clip

    composed = concatenate_videoclips(subclips, method="chain")
    if hasattr(clip, "audio") and clip.audio is not None:
        composed.audio = clip.audio
    return composed


def create_metaphor_badge_clip(
    metaphor: str,
    frame_width: int = 1080,
    visual_identity: dict | None = None,
) -> ImageClip | None:
    """Renderiza uma cartela/badge sutil (Pill) contendo o tema ou metáfora visual da cena via Pillow."""
    if not metaphor or not metaphor.strip():
        return None

    from clipper.video.editor import load_caption_font

    clean_text = metaphor.strip()
    if len(clean_text) > 45:
        clean_text = clean_text[:42] + "..."

    font_size = max(18, round(frame_width * 0.026))
    font = load_caption_font(font_size)

    padding_x = max(12, round(frame_width * 0.025))
    padding_y = max(8, round(frame_width * 0.012))

    left, top, right, bottom = font.getbbox(clean_text)
    text_w = right - left
    text_h = bottom - top

    badge_w = text_w + 2 * padding_x
    badge_h = text_h + 2 * padding_y
    if badge_w % 2 != 0:
        badge_w += 1
    if badge_h % 2 != 0:
        badge_h += 1

    image = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Fundo do pill arredondado semi-transparente
    radius = max(6, badge_h // 2)
    draw.rounded_rectangle(
        [(0, 0), (badge_w, badge_h)],
        radius=radius,
        fill=(15, 15, 15, 190),
        outline=(255, 255, 255, 60),
        width=2,
    )

    # Texto centralizado
    text_x = padding_x - left
    text_y = padding_y - top
    draw.text((text_x, text_y), clean_text, font=font, fill=(245, 245, 245, 255))

    return ImageClip(np.array(image))


def ease_out_back(t: float, overshoot: float = 1.70158) -> float:
    """Calcula a curva de aceleração ease_out_back para pop-in elástico."""
    t_clamped = min(max(t, 0.0), 1.0)
    t_sub = t_clamped - 1.0
    return 1.0 + (overshoot + 1.0) * (t_sub ** 3) + overshoot * (t_sub ** 2)


def sine_float(t: float, amplitude: float = 4.0, frequency: float = 0.8) -> float:
    """Calcula micro-deslocamento vertical senoidal em pixels para flutuação contínua."""
    return amplitude * math.sin(2.0 * math.pi * frequency * t)


def smooth_fade(t: float, total_duration: float, fade_duration: float = 0.25) -> float:
    """Calcula opacidade de 1.0 a 0.0 durante os últimos fade_duration segundos."""
    if total_duration <= fade_duration:
        return max(0.0, min(1.0, (total_duration - t) / max(0.01, total_duration)))
    if t >= total_duration - fade_duration:
        remaining = max(0.0, total_duration - t)
        return remaining / fade_duration
    return 1.0


def create_procedural_card_image(
    label_text: str,
    target_width: int = 480,
    target_height: int = 120,
    visual_identity: dict | None = None,
    icon_path: str | None = None,
) -> Image.Image:
    """Renderiza imagem RGBA de card procedural com tipografia Liberation e bordas arredondadas."""
    from clipper.video.editor import load_caption_font

    # Força dimensões estritamente pares
    if target_width % 2 != 0:
        target_width -= 1
    if target_height % 2 != 0:
        target_height -= 1

    clean_text = label_text.strip()
    if len(clean_text) > 40:
        clean_text = clean_text[:37] + "..."

    font_size = max(16, round(target_height * 0.28))
    font = load_caption_font(font_size)

    image = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Cores
    accent_color = "#FFD700"  # Gold padrão
    if visual_identity and "caption_color" in visual_identity:
        accent_color = visual_identity["caption_color"]

    accent_rgb = (255, 215, 0)
    if isinstance(accent_color, str) and accent_color.startswith("#") and len(accent_color) == 7:
        try:
            accent_rgb = (
                int(accent_color[1:3], 16),
                int(accent_color[3:5], 16),
                int(accent_color[5:7], 16),
            )
        except Exception:
            pass

    # Fundo do card
    radius = max(8, target_height // 4)
    draw.rounded_rectangle(
        [(0, 0), (target_width - 1, target_height - 1)],
        radius=radius,
        fill=(18, 18, 22, 220),
        outline=(255, 255, 255, 75),
        width=2,
    )

    # Barra lateral de acento visual (accent pill)
    bar_w = 6
    bar_pad_y = max(8, target_height // 4)
    bar_x = max(12, target_width // 24)
    draw.rounded_rectangle(
        [(bar_x, bar_pad_y), (bar_x + bar_w, target_height - bar_pad_y)],
        radius=3,
        fill=accent_rgb + (255,),
    )

    cur_x = bar_x + bar_w + 14

    # Se houver ícone válido (ex: PNG com canal alfa), desenha no card
    if icon_path and os.path.exists(icon_path):
        try:
            with Image.open(icon_path) as icon_img:
                icon_img = icon_img.convert("RGBA")
                icon_dim = max(16, target_height - 24)
                icon_resized = icon_img.resize((icon_dim, icon_dim), Image.Resampling.LANCZOS)
                icon_y = (target_height - icon_dim) // 2
                image.paste(icon_resized, (cur_x, icon_y), icon_resized)
                cur_x += icon_dim + 12
        except Exception:
            pass

    # Texto com ajuste para não ultrapassar a largura do card
    max_text_w = max(50, target_width - cur_x - 16)
    while clean_text and (font.getbbox(clean_text)[2] - font.getbbox(clean_text)[0]) > max_text_w:
        clean_text = clean_text[:-1]
    if len(clean_text) < len(label_text.strip()):
        clean_text = clean_text.rstrip()
        if len(clean_text) > 3:
            clean_text = clean_text[:-3] + "..."

    left, top, right, bottom = font.getbbox(clean_text)
    text_w = right - left
    text_h = bottom - top

    text_x = cur_x - left
    text_y = (target_height - text_h) // 2 - top
    draw.text((text_x, text_y), clean_text, font=font, fill=(245, 245, 245, 255))

    return image


def create_animated_insert_clip(
    resolved_insert: ResolvedInsert,
    video_size: tuple[int, int],
    visual_identity: dict | None = None,
) -> VideoClip | None:
    """Constrói clipe animado transparente para sobreposição do insert no vídeo vertical."""
    if not resolved_insert or resolved_insert.duration <= 0.1:
        return None

    vw, vh = video_size
    tw, th = resolved_insert.target_width, resolved_insert.target_height

    # Garante dimensões pares
    if tw % 2 != 0:
        tw -= 1
    if th % 2 != 0:
        th -= 1

    # Calcula coordenadas centrais garantindo zona de segurança (y <= 0.70 * vh)
    pos_x = int(vw * resolved_insert.center_x_ratio - tw / 2.0)
    pos_y = int(vh * resolved_insert.center_y_ratio - th / 2.0)

    # Garante que não ultrapasse a margem das legendas
    if pos_y + th > vh * 0.72:
        pos_y = int(vh * 0.72 - th)
    pos_x = max(10, min(vw - tw - 10, pos_x))
    pos_y = max(10, pos_y)

    # Caso A: Clipes de vídeo WebM pré-renderizados com canal alfa
    if (
        resolved_insert.asset_path
        and os.path.exists(resolved_insert.asset_path)
        and resolved_insert.asset_type == AssetType.ANIMATED_VIDEO
    ):
        try:
            anim_clip = VideoFileClip(resolved_insert.asset_path, has_mask=True)
            scaled = anim_clip.resize(newsize=(tw, th))
            if scaled.duration < resolved_insert.duration:
                from moviepy.editor import vfx
                scaled = scaled.fx(vfx.loop, duration=resolved_insert.duration)
            else:
                scaled = scaled.subclip(0, resolved_insert.duration)

            return (
                scaled.set_start(resolved_insert.start_time)
                .set_duration(resolved_insert.duration)
                .set_position((pos_x, pos_y))
            )
        except Exception as exc:
            logger.warning(
                "Failed to load WebM insert '%s': %s. Falling back to procedural card.",
                resolved_insert.asset_path,
                exc,
            )

    # Caso B: Card Procedural com animação elástica e flutuação
    card_img = create_procedural_card_image(
        label_text=resolved_insert.label_text,
        target_width=tw,
        target_height=th,
        visual_identity=visual_identity,
        icon_path=resolved_insert.asset_path if (resolved_insert.asset_path and os.path.exists(resolved_insert.asset_path)) else None,
    )
    img_arr = np.array(card_img)

    easing = resolved_insert.easing
    total_dur = resolved_insert.duration
    pop_dur = easing.pop_duration

    def scale_func(t: float) -> float:
        if t < pop_dur:
            progress = t / max(0.01, pop_dur)
            return max(0.01, ease_out_back(progress, easing.overshoot_factor))
        return 1.0

    def pos_func(t: float) -> tuple[int, int]:
        y_offset = sine_float(t, easing.float_amplitude, easing.float_frequency)
        if t > total_dur - easing.fade_duration:
            fade_prog = (t - (total_dur - easing.fade_duration)) / max(0.01, easing.fade_duration)
            y_offset -= 10.0 * fade_prog
        return (pos_x, int(pos_y + y_offset))

    card_clip = ImageClip(img_arr, transparent=True)
    animated = (
        card_clip.set_start(resolved_insert.start_time)
        .set_duration(total_dur)
        .resize(scale_func)
        .set_position(pos_func)
    )
    return animated


def mix_audio_sfx(
    original_audio: AudioClip | None,
    inserts: list[ResolvedInsert],
) -> AudioClip | None:
    """Mixa efeitos sonoros dos inserts na trilha principal de áudio atenuando volume."""
    if original_audio is None or not inserts:
        return original_audio

    valid_sfx_inserts = [
        ins for ins in inserts
        if ins.sfx_path and os.path.exists(ins.sfx_path)
    ]
    if not valid_sfx_inserts:
        return original_audio

    try:
        sfx_clips = []
        for ins in valid_sfx_inserts:
            try:
                sfx_clip = AudioFileClip(ins.sfx_path)
                sfx_clip = sfx_clip.volumex(0.35)
                sfx_clip = sfx_clip.set_start(ins.start_time)
                sfx_clips.append(sfx_clip)
            except Exception as sfx_err:
                logger.warning("Failed to load audio SFX from '%s': %s", ins.sfx_path, sfx_err)

        if not sfx_clips:
            return original_audio

        composite_audio = CompositeAudioClip([original_audio] + sfx_clips)
        composite_audio.duration = original_audio.duration
        return composite_audio
    except Exception as exc:
        logger.warning("mix_audio_sfx failed, preserving original audio: %s", exc)
        return original_audio
