import os
import json
import re
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from moviepy.video.fx.all import crop

def cut_and_format_video(video_path: str, cuts_json: str, word_timestamps: list, output_dir: str = "output") -> list:
    try:
        # Extrai ABSOLUTAMENTE APENAS o bloco de array JSON [ ... ] ignorando TERMINATE ou qualquer outro texto
        match = re.search(r'\[.*\]', cuts_json, re.DOTALL)
        if match:
            clean_json = match.group(0)
        else:
            clean_json = cuts_json.replace("```json", "").replace("```", "").replace("TERMINATE", "").strip()
            
        cuts = json.loads(clean_json)
    except json.JSONDecodeError as e:
        print(f"Erro ao decodificar JSON: {e}")
        print(f"Conteúdo sujo recebido: {cuts_json}")
        return []

    os.makedirs(output_dir, exist_ok=True)
    video = VideoFileClip(video_path)

    target_ratio = 9 / 16
    if video.w / video.h > target_ratio:
        new_width = int(video.h * target_ratio)
        
        # Garante que a largura seja um número par (Exigência do libx264)
        if new_width % 2 != 0:
            new_width -= 1
            
        # Garante que a altura também seja um número par
        new_height = video.h
        if new_height % 2 != 0:
            new_height -= 1
            
        x_center = video.w / 2
        video = crop(video, width=new_width, height=new_height, x_center=x_center)

    generated_files = []
    for corte in cuts:
        # Limpa o título e limita a 50 caracteres para não quebrar o limite de caminho do sistema operacional
        titulo_limpo = re.sub(r'[^\w\s]', '', corte['title']).replace(' ', '_')[:50]
        
        print(f"[MoviePy] Cortando: {titulo_limpo} ({corte['start_time']}s - {corte['end_time']}s)")
        clip = video.subclip(corte["start_time"], corte["end_time"])
        filepath = os.path.join(output_dir, f"{titulo_limpo}.mp4")

        # Filter and adjust word timestamps
        local_word_timestamps = [
            {
                "word": word["word"],
                "start": word["start"] - corte["start_time"],
                "end": word["end"] - corte["start_time"]
            }
            for word in word_timestamps
            if corte["start_time"] <= word["start"] <= corte["end_time"]
        ]

        # Create text clips
        text_clips = []
        for word in local_word_timestamps:
            text_clip = TextClip(
                word["word"],
                fontsize=70,
                font='Liberation-Sans-Bold',
                color='yellow',
                stroke_color='black',
                stroke_width=3
            ).set_position(('center', 'center')).set_start(word["start"]).set_end(word["end"])
            text_clips.append(text_clip)

        # Compose final video
        final_clip = CompositeVideoClip([clip] + text_clips)
        final_clip.write_videofile(filepath, codec="libx264", audio_codec="aac", ffmpeg_params=["-pix_fmt", "yuv420p", "-profile:v", "main"], logger=None)
        generated_files.append(filepath)

    video.close()
    return generated_files
