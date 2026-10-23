import os
import re
import gc
import requests
from yt_dlp import YoutubeDL
from faster_whisper import WhisperModel


def download_video(url: str, output_dir: str = "downloads") -> dict:
    try:
        video_id = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
        if not video_id:
            return {"status": "error", "message": "URL inválida."}
        video_id = video_id.group(1)

        os.makedirs(output_dir, exist_ok=True)
        ydl_opts = {
            "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
            "outtmpl": f"{output_dir}/%(id)s.%(ext)s",
            "quiet": False,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            video_path = ydl.prepare_filename(info_dict)
            title = info_dict.get("title", "Desconhecido")

        return {
            "status": "success",
            "video_id": video_id,
            "video_path": video_path,
            "title": title,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def transcribe_audio_chunk(audio_path: str) -> dict:
    try:
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio_path, beam_size=5, word_timestamps=True)

        word_timestamps_list = []
        transcript_string = ""

        for segment in segments:
            transcript_string += (
                f"[{segment.start:.2f} - {segment.end:.2f}] {segment.text} "
            )
            if segment.words:
                for word in segment.words:
                    word_timestamps_list.append(
                        {"word": word.word, "start": word.start, "end": word.end}
                    )

        del model
        import gc

        gc.collect()

        return {
            "status": "success",
            "transcript": transcript_string,
            "word_timestamps": word_timestamps_list,
        }
    except Exception as e:
        if "model" in locals():
            del model
            import gc

            gc.collect()
        return {"status": "error", "message": str(e)}


def download_video_and_transcript(url: str, output_dir: str = "downloads") -> dict:
    video_res = download_video(url, output_dir)
    if video_res.get("status") == "error":
        return video_res

    transcribe_res = transcribe_audio_chunk(video_res["video_path"])
    if transcribe_res.get("status") == "error":
        return transcribe_res

    return {
        "status": "success",
        "video_id": video_res["video_id"],
        "video_path": video_res["video_path"],
        "title": video_res["title"],
        "transcript": transcribe_res["transcript"],
        "word_timestamps": transcribe_res["word_timestamps"],
    }


if __name__ == "__main__":
    test_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    result = download_video_and_transcript(test_url)
    print(f"Status: {result.get('status')}")
    if result.get("status") == "success":
        print(f"Video ID: {result.get('video_id')}")
        print(f"Video Path: {result.get('video_path')}")
        print(f"Title: {result.get('title')}")
        print(f"Transcript (first 500 chars): {result.get('transcript', '')[:500]}")
    else:
        print(f"Message: {result.get('message')}")
