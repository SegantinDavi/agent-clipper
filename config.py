import os

OUTPUT_DIR = os.getenv(
    "OUTPUT_DIR", "/app/output" if os.path.exists("/app") else "output"
)
DOWNLOADS_DIR = os.getenv("DOWNLOADS_DIR", os.path.join(OUTPUT_DIR, "downloads"))
DB_PATH = os.getenv("DB_PATH", os.path.join(OUTPUT_DIR, "estado.db"))
LOG_FILE = os.getenv("LOG_FILE", os.path.join(OUTPUT_DIR, "pipeline.log"))

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
YOUTUBE_URL = os.getenv("YOUTUBE_URL")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
