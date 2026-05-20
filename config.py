import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_EMBED_BASE = "https://openrouter.ai/api/v1/embeddings"
VISION_MODEL = os.getenv("VISION_MODEL", "google/gemini-3.1-flash-lite-preview")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "8"))
PORT = int(os.getenv("PORT", "8000"))
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
EXTRACTIONS_DIR = os.path.join(DATA_DIR, "extractions")

# Ensure runtime dirs exist (fresh cloud volumes may be empty → FileNotFoundError)
for _d in (DATA_DIR, UPLOADS_DIR, EXTRACTIONS_DIR, os.path.join(DATA_DIR, "chroma")):
    os.makedirs(_d, exist_ok=True)
