import os
from pathlib import Path
from dotenv import load_dotenv

# Search for .env in project root or backend root
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

if (PROJECT_ROOT / ".env").exists():
    load_dotenv(PROJECT_ROOT / ".env")
elif (BACKEND_DIR / ".env").exists():
    load_dotenv(BACKEND_DIR / ".env")
else:
    load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
# Current Gemini model for multimodal reading: gemini-3.8-flash
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'data' / 'medmatch.db'}")

PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")

DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DRUGS_CSV_PATH = DATA_DIR / "drugs.csv"
LOOKALIKES_CSV_PATH = DATA_DIR / "lookalikes.csv"
DB_PATH = DATA_DIR / "medmatch.db"
CROPS_DIR = DATA_DIR / "uploads" / "crops"
CROPS_DIR.mkdir(parents=True, exist_ok=True)
