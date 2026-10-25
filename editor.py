import os
import re
import logging
import subprocess
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
from moviepy.video.fx.all import crop
from schemas import CorteVideo
from config import (
    CAPTION_CENTER_X_RATIO, CAPTION_CENTER_Y_RATIO, CAPTION_COLOR,
    CAPTION_FONT_SIZE, CAPTION_MAX_DURATION, CAPTION_MAX_GAP, CAPTION_MAX_WORDS,
    CAPTION_REFERENCE_WIDTH, CAPTION_SAFE_WIDTH_RATIO, CAPTION_STROKE_COLOR,
    CAPTION_STROKE_WIDTH,
)

logger = logging.getLogger(__name__)


@lru_cache(maxsize=16)
def load_caption_font(size: int = CAPTION_FONT_SIZE) -> ImageFont.FreeTypeFont:
    result = subprocess.run(
        ["fc-match", "-f", "%{file}", "Liberation Sans:style=Bold"],
        capture_output=True, text=True, check=True,
    )
    font_path = result.stdout.strip()
    if os.path.basename(font_path) != "LiberationSans-Bold.ttf":
        raise RuntimeError("Liberation Sans Bold is required. Install fonts-liberation.")
    return ImageFont.truetype(font_path, size=size)


def create_caption_clip(text: str, frame_width: int = CAPTION_REFERENCE_WIDTH) -> ImageClip:
    # Pillow avoids TextClip's indirect @file reads blocked by ImageMagick policy.
    font_size = max(1, round(CAPTION_FONT_SIZE * frame_width / CAPTION_REFERENCE_WIDTH))
    padding = max(1, round(4 * frame_width / CAPTION_REFERENCE_WIDTH))
    max_width = max(1, int(frame_width * CAPTION_SAFE_WIDTH_RATIO))
    while True:
        font = load_caption_font(font_size)
        stroke_width = max(1, round(CAPTION_STROKE_WIDTH * font_size / CAPTION_FONT_SIZE))
        left, top, right, bottom = font.getbbox(text, stroke_width=stroke_width)
        text_width = right - left + 2 * padding
        if text_width <= max_width or font_size == 1:
            break
        font_size = max(1, min(font_size - 1, int(font_size * max_width / text_width)))
    image = Image.new(
        "RGBA", (max(1, right - left + 2 * padding), max(1, bottom - top + 2 * padding)),
        (0, 0, 0, 0),
    )
    ImageDraw.Draw(image).text(
        (padding - left, padding - top), text, font=font, fill=CAPTION_COLOR,
        stroke_fill=CAPTION_STROKE_COLOR, stroke_width=stroke_width,
    )
    return ImageClip(np.array(image))


def position_caption_clip(caption: ImageClip, frame_size: tuple[int, int]) -> ImageClip:
    frame_width, frame_height = frame_size
    x = round(frame_width * CAPTION_CENTER_X_RATIO - caption.w / 2)
    y = round(frame_height * CAPTION_CENTER_Y_RATIO - caption.h / 2)
    x = max(0, min(x, frame_width - caption.w))
    y = max(0, min(y, frame_height - caption.h))
    return caption.set_position((x, y))


def group_caption_words(
    word_timestamps: list, start_time: float, end_time: float,
) -> list[dict]:
    groups = []
    current_words = []

    def flush_group() -> None:
        if current_words:
            groups.append({
                "text": " ".join(word["word"] for word in current_words),
                "start": current_words[0]["start"] - start_time,
                "end": max(word["end"] for word in current_words) - start_time,
            })
            current_words.clear()

    for word in word_timestamps:
        text = word["word"].strip()
        word_start = max(start_time, word["start"])
        word_end = min(end_time, word["end"])
        if not text or word_end <= word_start:
            continue
        if current_words and (
            len(current_words) >= CAPTION_MAX_WORDS
            or word_start - current_words[-1]["end"] > CAPTION_MAX_GAP
            or word_end - current_words[0]["start"] > CAPTION_MAX_DURATION
        ):
            flush_group()
        current_words.append({"word": text, "start": word_start, "end": word_end})
        if text.endswith((".", "!", "?", "…")):
            flush_group()
    flush_group()
    return groups


def cut_and_format_video(
    video_path: str,
    cortes_validados: list[CorteVideo],
    word_timestamps: list,
    output_dir: str = "output",
) -> list:
    os.makedirs(output_dir, exist_ok=True)
    video = VideoFileClip(video_path)

    target_ratio = 9 / 16
    if video.w / video.h > target_ratio:
        new_width = int(video.h * target_ratio)

        if new_width % 2 != 0:
            new_width -= 1

        new_height = video.h
        if new_height % 2 != 0:
            new_height -= 1

        x_center = video.w / 2
        video = crop(video, width=new_width, height=new_height, x_center=x_center)

    generated_files = []
    for corte in cortes_validados:
        titulo_limpo = re.sub(r"[^\w\s]", "", corte.title).replace(" ", "_")[:50]

        logger.info(
            "Rendering clip: %s (%.2fs - %.2fs)",
            titulo_limpo,
            corte.start_time,
            corte.end_time,
        )
        clip = video.subclip(corte.start_time, corte.end_time)
        filepath = os.path.join(output_dir, f"{titulo_limpo}.mp4")

        caption_groups = group_caption_words(
            word_timestamps, corte.start_time, corte.end_time,
        )

        text_clips = []
        for group in caption_groups:
            caption = create_caption_clip(group["text"], frame_width=clip.w)
            text_clip = (
                position_caption_clip(caption, tuple(clip.size))
                .set_start(group["start"])
                .set_end(group["end"])
            )
            text_clips.append(text_clip)

        final_clip = CompositeVideoClip([clip] + text_clips)
        try:
            final_clip.write_videofile(
                filepath,
                codec="libx264",
                audio_codec="aac",
                ffmpeg_params=["-pix_fmt", "yuv420p", "-profile:v", "main"],
                logger=None,
            )
        finally:
            final_clip.close()
            for text_clip in text_clips:
                text_clip.close()
        logger.info("Saved clip to %s", filepath)
        generated_files.append(filepath)

    video.close()
    return generated_files
