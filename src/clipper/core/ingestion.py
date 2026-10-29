import os
import re
import gc
import logging
from yt_dlp import YoutubeDL
from faster_whisper import WhisperModel

from clipper.runtime.config import WHISPER_DEVICE, WHISPER_COMPUTE_TYPE

logger = logging.getLogger(__name__)


def extract_video_id(url_or_id: str | None) -> str:
    """Extract YouTube 11-character video ID or preserve raw identifier."""
    if not url_or_id:
        return ""
    clean = str(url_or_id).strip()
    match = re.search(
        r"(?:youtu\.be\/|youtube\.com\/(?:embed\/|v\/|shorts\/|watch\?.*v=)|(?:[?&]v=))([0-9A-Za-z_-]{11})(?:[?&#/]|$)",
        clean,
    )
    if match:
        return match.group(1)
    return clean


def download_video(url: str, output_dir: str = "downloads") -> dict:
    try:
        video_id = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
        if not video_id:
            logger.error("Invalid YouTube URL: %s", url)
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

        logger.info("Video successfully downloaded: %s (%s)", title, video_path)
        return {
            "status": "success",
            "video_id": video_id,
            "video_path": video_path,
            "title": title,
        }
    except Exception as e:
        logger.error("Failed to download video from %s: %s", url, e, exc_info=True)
        return {"status": "error", "message": str(e)}


def transcribe_audio_chunk(audio_path: str) -> dict:
    model = None
    segments = None
    try:
        logger.info(
            "Starting Whisper transcription on %s (%s): %s",
            WHISPER_DEVICE, WHISPER_COMPUTE_TYPE, audio_path,
        )
        model = WhisperModel(
            "small", device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE
        )
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

        logger.info("Transcription completed for %s", audio_path)
        return {
            "status": "success",
            "transcript": transcript_string,
            "word_timestamps": word_timestamps_list,
        }
    except Exception as e:
        logger.error(
            "Failed to transcribe audio chunk %s: %s", audio_path, e, exc_info=True
        )
        return {"status": "error", "message": str(e)}
    finally:
        # The lazy segment iterator can retain the model after decoding fails.
        if segments is not None:
            segments.close()
        del segments
        del model
        gc.collect()


def download_video_and_transcript(url: str, output_dir: str = "downloads") -> dict:
    video_res = download_video(url, output_dir)
    if video_res.get("status") == "error":
        logger.error(
            "Download failed in download_video_and_transcript: %s",
            video_res.get("message"),
        )
        return video_res

    transcribe_res = transcribe_audio_chunk(video_res["video_path"])
    if transcribe_res.get("status") == "error":
        logger.error(
            "Transcription failed in download_video_and_transcript: %s",
            transcribe_res.get("message"),
        )
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
    from config import YOUTUBE_URL

    video_url = YOUTUBE_URL
    if not video_url:
        logger.error("Environment variable 'YOUTUBE_URL' is required.")
        raise ValueError("Environment variable 'YOUTUBE_URL' is required.")

    result = download_video_and_transcript(video_url)
    logger.info("Status: %s", result.get("status"))
    if result.get("status") == "success":
        logger.info("Video ID: %s", result.get("video_id"))
        logger.info("Video Path: %s", result.get("video_path"))
        logger.info("Title: %s", result.get("title"))
        logger.info(
            "Transcript (first 500 chars): %s", result.get("transcript", "")[:500]
        )
    else:
        logger.error("Message: %s", result.get("message"))
