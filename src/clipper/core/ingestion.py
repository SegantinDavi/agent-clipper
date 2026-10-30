import os
import re
import gc
import logging
from yt_dlp import YoutubeDL
from faster_whisper import WhisperModel

from clipper.runtime.config import WHISPER_DEVICE, WHISPER_COMPUTE_TYPE
from clipper.runtime.cuda_runtime import get_gpu_memory_info, release_cuda_memory

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
        before_mb = None
        if WHISPER_DEVICE == "cuda":
            try:
                gpu_info = get_gpu_memory_info()
                if gpu_info is not None:
                    before_mb = gpu_info[0]
            except Exception:
                pass

        if segments is not None:
            try:
                if hasattr(segments, "close"):
                    segments.close()
            except Exception as close_err:
                logger.debug("Iterator close failed: %s", close_err)

        if model is not None:
            try:
                ct2_model = getattr(model, "model", None)
                if ct2_model is not None and hasattr(ct2_model, "unload_model"):
                    ct2_model.unload_model()
            except Exception as unload_err:
                logger.warning("Failed to unload CTranslate2 model: %s", unload_err)

        del segments
        del model
        gc.collect()

        if WHISPER_DEVICE == "cuda":
            try:
                release_cuda_memory(before_mb=before_mb)
            except Exception as cleanup_err:
                logger.warning("GPU memory cleanup encountered an error: %s", cleanup_err)


def apply_chunk_offset(
    words: list[dict],
    offset: float,
    chunk_index: int,
) -> list[dict]:
    """Shift start and end timestamps of words by offset seconds.

    Converts chunk-relative timestamps from Whisper into absolute timeline
    coordinates of the original video. Logs offset details and returns a
    new list without mutating the input.

    Args:
        words: List of dicts, each with 'word', 'start', and 'end'.
        offset: Absolute start time (in seconds) of the chunk (>= 0.0).
        chunk_index: 0-based index of the chunk, used for structured logging.

    Returns:
        A new list of dicts with 'start' and 'end' remapped to absolute time.

    Raises:
        ValueError: If offset is negative (< 0.0).
    """
    if offset < 0.0:
        raise ValueError(f"Chunk offset cannot be negative: {offset}")

    remapped_words = []
    for word_info in words:
        remapped_words.append(
            {
                **word_info,
                "start": round(float(word_info["start"]) + offset, 2),
                "end": round(float(word_info["end"]) + offset, 2),
            }
        )

    logger.info(
        "Chunk %d offset applied: +%.2fs → %d words remapped",
        chunk_index,
        offset,
        len(remapped_words),
    )
    return remapped_words


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
