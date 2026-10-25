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

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_caption_font() -> ImageFont.FreeTypeFont:
    result = subprocess.run(
        ["fc-match", "-f", "%{file}", "Liberation Sans:style=Bold"],
        capture_output=True, text=True, check=True,
    )
    font_path = result.stdout.strip()
    if os.path.basename(font_path) != "LiberationSans-Bold.ttf":
        raise RuntimeError("Liberation Sans Bold is required. Install fonts-liberation.")
    return ImageFont.truetype(font_path, size=70)


def create_caption_clip(text: str) -> ImageClip:
    # Pillow avoids TextClip's indirect @file reads blocked by ImageMagick policy.
    font = load_caption_font()
    stroke_width = 3
    padding = 4
    left, top, right, bottom = font.getbbox(text, stroke_width=stroke_width)
    image = Image.new(
        "RGBA", (max(1, right - left + 2 * padding), max(1, bottom - top + 2 * padding)),
        (0, 0, 0, 0),
    )
    ImageDraw.Draw(image).text(
        (padding - left, padding - top), text, font=font, fill="yellow",
        stroke_fill="black", stroke_width=stroke_width,
    )
    return ImageClip(np.array(image))


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

        local_word_timestamps = [
            {
                "word": word["word"],
                "start": word["start"] - corte.start_time,
                "end": word["end"] - corte.start_time,
            }
            for word in word_timestamps
            if corte.start_time <= word["start"] <= corte.end_time
        ]

        text_clips = []
        for word in local_word_timestamps:
            if not word["word"].strip():
                continue
            text_clip = (
                create_caption_clip(word["word"])
                .set_position(("center", "center"))
                .set_start(word["start"])
                .set_end(word["end"])
            )
            text_clips.append(text_clip)

        final_clip = CompositeVideoClip([clip] + text_clips)
        final_clip.write_videofile(
            filepath,
            codec="libx264",
            audio_codec="aac",
            ffmpeg_params=["-pix_fmt", "yuv420p", "-profile:v", "main"],
            logger=None,
        )
        logger.info("Saved clip to %s", filepath)
        generated_files.append(filepath)

    video.close()
    return generated_files
