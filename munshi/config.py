import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

HINDSIGHT_URL = os.getenv("HINDSIGHT_URL", "https://api.hindsight.vectorize.io")
HINDSIGHT_API_KEY = os.getenv("HINDSIGHT_API_KEY") or None
BANK_ID = os.getenv("MUNSHI_BANK_ID", "munshi-ap-kaveri")

# Any OpenAI-compatible endpoint. Defaults to Groq.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

DATA_DIR = ROOT / "data"
BOOK_PATH = DATA_DIR / "ap_book.json"
STATE_PATH = DATA_DIR / "state.json"
