import os

OUTPUT_DIR = os.getenv(
    "OUTPUT_DIR", "/app/output" if os.path.exists("/app") else "output"
)
DOWNLOADS_DIR = os.getenv("DOWNLOADS_DIR", os.path.join(OUTPUT_DIR, "downloads"))
DB_PATH = os.getenv("DB_PATH", os.path.join(OUTPUT_DIR, "estado.db"))
LOG_FILE = os.getenv("LOG_FILE", os.path.join(OUTPUT_DIR, "pipeline.log"))

GEMINI_API_KEY = "COLE_SUA_API_KEY_AQUI"
GEMINI_BASE_URL = os.getenv(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
)
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
LLM_MAX_COMPLETION_TOKENS = int(os.getenv("LLM_MAX_COMPLETION_TOKENS", "8192"))
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
YOUTUBE_URL = os.getenv("YOUTUBE_URL", "")
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

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)


def validate_llm_config() -> None:
    if not GEMINI_API_KEY.strip() or GEMINI_API_KEY == "COLE_SUA_API_KEY_AQUI":
        raise ValueError("Set GEMINI_API_KEY in config.py before running the pipeline.")
    if not MODEL_NAME.strip():
        raise ValueError("Environment variable 'GEMINI_MODEL' must not be empty.")
    if LLM_MAX_COMPLETION_TOKENS <= 0:
        raise ValueError("LLM_MAX_COMPLETION_TOKENS must be positive.")
