"""Motor determinístico de motion design para agent-clipper.

Mapeia as cenas (Scene) de cada corte e aplica variações dinâmicas de enquadramento,
escala (punch-in, zoom suave) e alternância de ângulo via MoviePy 1.0.3 e Pillow.
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, VideoClip, concatenate_videoclips

from clipper.core.schemas import CorteVideo, Scene

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
