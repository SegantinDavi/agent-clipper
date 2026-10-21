import os
import re
import gc
import requests
from yt_dlp import YoutubeDL
from faster_whisper import WhisperModel

def download_video_and_transcript(url: str, output_dir: str = "downloads") -> dict:
    try:
        # Extração do video_id
        video_id = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
        if not video_id:
            return {"status": "error", "message": "URL inválida."}
        video_id = video_id.group(1)

        # Configuração do yt-dlp
        os.makedirs(output_dir, exist_ok=True)
        ydl_opts = {
            'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best',
            'outtmpl': f'{output_dir}/%(id)s.%(ext)s',
            'quiet': False,
        }

        # Download do vídeo
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            video_path = ydl.prepare_filename(info_dict)
            title = info_dict.get('title', 'Desconhecido')

        # Iniciar faster-whisper diretamente
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, info = model.transcribe(video_path, beam_size=5, word_timestamps=True)
        
        word_timestamps_list = []
        transcript_string = ""
        
        for segment in segments:
            for word in segment.words:
                word_timestamps_list.append({
                    "word": word.word,
                    "start": word.start,
                    "end": word.end
                })
                transcript_string += f"[{word.start:.2f} - {word.end:.2f}] {word.word} "
        
        return {
            "status": "success",
            "video_id": video_id,
            "video_path": video_path,
            "title": title,
            "transcript": transcript_string,
            "word_timestamps": word_timestamps_list
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    test_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    result = download_video_and_transcript(test_url)
    print(f"Status: {result['status']}")
    print(f"Video ID: {result['video_id']}")
    print(f"Video Path: {result['video_path']}")
    print(f"Title: {result['title']}")
    print(f"Transcript (first 500 chars): {result['transcript'][:500]}")
