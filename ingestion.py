import os
import re
import gc
import requests
from yt_dlp import YoutubeDL
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled
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

        # Extração da transcrição
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['pt', 'pt-BR', 'en'])
            transcript = "\n".join([f"[{entry['start']:.2f} - {entry['start'] + entry['duration']:.2f}] {entry['text']}" for entry in transcript_list])
        except (TranscriptsDisabled, Exception):
            print("[Ingestion] Legendas não encontradas na API. Iniciando faster-whisper local...")
            try:
                requests.post("http://127.0.0.1:11434/api/generate", json={"model": "qwen2.5:14b", "keep_alive": 0})
            except Exception:
                pass
            model = WhisperModel("small", device="cuda", compute_type="float16")
            segments, info = model.transcribe(video_path, beam_size=5)
            transcript = "\n".join([f"[{segment.start:.2f} - {segment.end:.2f}] {segment.text}" for segment in segments])
            print("[Ingestion] Transcrição concluída. Liberando VRAM.")
            del model
            gc.collect()

        return {
            "status": "success",
            "video_id": video_id,
            "video_path": video_path,
            "transcript": transcript,
            "title": title
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
