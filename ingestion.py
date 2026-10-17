import os
import re
from yt_dlp import YoutubeDL
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled
from faster_whisper import WhisperModel
import torch

def download_video_and_transcript(url: str, output_dir: str = "downloads") -> dict:
    """
    Baixa o vídeo do YouTube em uma resolução otimizada e extrai as legendas com os timestamps exatos.
    
    :param url: URL do vídeo do YouTube.
    :param output_dir: Diretório onde o vídeo e a transcrição serão salvos.
    :return: Dicionário com status, video_id, video_path, transcript e title.
    """
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
        except (TranscriptsDisabled, Exception) as e:
            print("[Ingestion] Legendas ausentes. Transcrição gerada localmente via Whisper.")
            model = WhisperModel("small", device="cuda", compute_type="float16")
            segments, info = model.transcribe(video_path, beam_size=5)
            transcript = "\n".join([f"[{segment.start:.2f} - {segment.end:.2f}] {segment.text}" for segment in segments])
            del model
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

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
