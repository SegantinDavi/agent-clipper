import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"), override=False)

OUTPUT_DIR = os.getenv(
    "OUTPUT_DIR", "/app/output" if os.path.exists("/app") else "output"
)
DOWNLOADS_DIR = os.getenv("DOWNLOADS_DIR", os.path.join(OUTPUT_DIR, "downloads"))
DB_PATH = os.getenv("DB_PATH", os.path.join(OUTPUT_DIR, "estado.db"))
LOG_FILE = os.getenv("LOG_FILE", os.path.join(OUTPUT_DIR, "pipeline.log"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_BASE_URL = os.getenv(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
MODEL_NAME = (
    os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
    if LLM_PROVIDER == "ollama"
    else os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
)
LLM_BASE_URL = OLLAMA_BASE_URL if LLM_PROVIDER == "ollama" else GEMINI_BASE_URL
LLM_API_KEY = "ollama" if LLM_PROVIDER == "ollama" else GEMINI_API_KEY
LLM_MAX_COMPLETION_TOKENS = int(os.getenv("LLM_MAX_COMPLETION_TOKENS", "8192"))
WHISPER_DEVICE = "cpu" if LLM_PROVIDER == "ollama" else "cuda"
WHISPER_COMPUTE_TYPE = "int8" if LLM_PROVIDER == "ollama" else "float16"
YOUTUBE_URL = os.getenv("YOUTUBE_URL", "")
SILENCE_CUT_ENABLED = os.getenv("SILENCE_CUT_ENABLED", "1").lower() in {"1", "true", "yes"}
SILENCE_MIN_PAUSE = float(os.getenv("SILENCE_MIN_PAUSE", "0.6"))
SILENCE_KEEP_PAUSE = float(os.getenv("SILENCE_KEEP_PAUSE", "0.2"))
SILENCE_SPEECH_PADDING = float(os.getenv("SILENCE_SPEECH_PADDING", "0.1"))
SILENCE_THRESHOLD_DB = float(os.getenv("SILENCE_THRESHOLD_DB", "-35"))
CAPTION_COLOR = os.getenv("CAPTION_COLOR", "#25E600")
CAPTION_STROKE_COLOR = os.getenv("CAPTION_STROKE_COLOR", "#000000")
CAPTION_FONT_SIZE = int(os.getenv("CAPTION_FONT_SIZE", "80"))
CAPTION_STROKE_WIDTH = int(os.getenv("CAPTION_STROKE_WIDTH", "8"))
CAPTION_REFERENCE_WIDTH = int(os.getenv("CAPTION_REFERENCE_WIDTH", "1080"))
CAPTION_CENTER_X_RATIO = float(os.getenv("CAPTION_CENTER_X_RATIO", "0.5"))
CAPTION_CENTER_Y_RATIO = float(os.getenv("CAPTION_CENTER_Y_RATIO", "0.79"))
CAPTION_SAFE_WIDTH_RATIO = float(os.getenv("CAPTION_SAFE_WIDTH_RATIO", "0.9"))
CAPTION_MAX_WORDS = int(os.getenv("CAPTION_MAX_WORDS", "3"))
CAPTION_MAX_GAP = float(os.getenv("CAPTION_MAX_GAP", "0.5"))
CAPTION_MAX_DURATION = float(os.getenv("CAPTION_MAX_DURATION", "2.0"))
SPEAKER_FOCUS_ENABLED = os.getenv("SPEAKER_FOCUS_ENABLED", "1").lower() in {"1", "true", "yes"}
SPEAKER_FOCUS_MODEL_DIR = os.getenv(
    "SPEAKER_FOCUS_MODEL_DIR", os.path.join(os.path.dirname(__file__), "assets", "speaker_focus")
)
SPEAKER_FOCUS_THREADS = int(os.getenv("SPEAKER_FOCUS_THREADS", "2"))
SPEAKER_FOCUS_DETECTION_WIDTH = int(os.getenv("SPEAKER_FOCUS_DETECTION_WIDTH", "640"))
SPEAKER_FOCUS_DETECTION_INTERVAL = int(os.getenv("SPEAKER_FOCUS_DETECTION_INTERVAL", "5"))
SPEAKER_FOCUS_WINDOW_SECONDS = float(os.getenv("SPEAKER_FOCUS_WINDOW_SECONDS", "4"))
SPEAKER_FOCUS_MAX_FACES = int(os.getenv("SPEAKER_FOCUS_MAX_FACES", "4"))
SPEAKER_FOCUS_THRESHOLD = float(os.getenv("SPEAKER_FOCUS_THRESHOLD", "0"))
SPEAKER_FOCUS_SWITCH_MARGIN = float(os.getenv("SPEAKER_FOCUS_SWITCH_MARGIN", "0.5"))
SPEAKER_FOCUS_SWITCH_HOLD = float(os.getenv("SPEAKER_FOCUS_SWITCH_HOLD", "0.32"))
SPEAKER_FOCUS_TRACK_GAP = float(os.getenv("SPEAKER_FOCUS_TRACK_GAP", "0.4"))
SPEAKER_FOCUS_TRACK_IOU = float(os.getenv("SPEAKER_FOCUS_TRACK_IOU", "0.15"))
SPEAKER_FOCUS_DETECTION_THRESHOLD = float(os.getenv("SPEAKER_FOCUS_DETECTION_THRESHOLD", "0.8"))
SPEAKER_FOCUS_FACE_VERTICAL_POSITION = float(os.getenv("SPEAKER_FOCUS_FACE_VERTICAL_POSITION", "0.35"))
SPEAKER_FOCUS_SCENE_THRESHOLD = float(os.getenv("SPEAKER_FOCUS_SCENE_THRESHOLD", "0.18"))
SPEAKER_FOCUS_FACE_HEIGHT_RATIO = float(os.getenv("SPEAKER_FOCUS_FACE_HEIGHT_RATIO", "0.38"))
SPEAKER_FOCUS_MAX_ZOOM = float(os.getenv("SPEAKER_FOCUS_MAX_ZOOM", "2.5"))

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)


def validate_llm_config() -> None:
    if LLM_PROVIDER not in {"gemini", "ollama"}:
        raise ValueError("LLM_PROVIDER must be 'gemini' or 'ollama'.")
    if LLM_PROVIDER == "gemini" and (
        not GEMINI_API_KEY.strip() or GEMINI_API_KEY == "COLE_SUA_API_KEY_AQUI"
    ):
        raise ValueError("Set GEMINI_API_KEY in the environment or .env before running the pipeline.")
    if not MODEL_NAME.strip():
        raise ValueError("The selected provider's model must not be empty.")
    if not LLM_BASE_URL.strip():
        raise ValueError("The selected provider's base URL must not be empty.")
    if LLM_MAX_COMPLETION_TOKENS <= 0:
        raise ValueError("LLM_MAX_COMPLETION_TOKENS must be positive.")
