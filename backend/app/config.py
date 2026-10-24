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

# Vision AI Configuration (Google GenAI)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-1.5-flash").strip()
USE_TROCR = os.getenv("USE_TROCR", "false").lower() in ("true", "1", "yes")

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

if DATABASE_URL.startswith("sqlite:///"):
    sqlite_rel_or_abs = DATABASE_URL.replace("sqlite:///", "")
    # If path starts with ./, resolve relative to BACKEND_DIR
    if sqlite_rel_or_abs.startswith("./") or sqlite_rel_or_abs.startswith(".\\"):
        DB_PATH = (BACKEND_DIR / sqlite_rel_or_abs[2:]).resolve()
    else:
        DB_PATH = Path(sqlite_rel_or_abs).resolve()
else:
    DB_PATH = DATA_DIR / "medmatch.db"

# Server Network Configuration
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "127.0.0.1")

# Security & Upload Configuration
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}

# CORS Trusted Origins
_origins_env = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"
)
ALLOWED_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()]

# RxNorm REST API Configuration
RXNORM_API_BASE = os.getenv("RXNORM_API_BASE", "https://rxnav.nlm.nih.gov/REST").rstrip("/")
RXNORM_REQUEST_TIMEOUT = float(os.getenv("RXNORM_REQUEST_TIMEOUT", "8.0"))
RXNORM_CACHE_TTL_SECONDS = int(os.getenv("RXNORM_CACHE_TTL_SECONDS", "3600"))

# Clinical Catalog Paths
DRUGS_CSV_PATH = DATA_DIR / "drugs.csv"
LOOKALIKES_CSV_PATH = DATA_DIR / "lookalikes.csv"
UPLOADS_DIR = DATA_DIR / "uploads"
CROPS_DIR = UPLOADS_DIR / "crops"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
CROPS_DIR.mkdir(parents=True, exist_ok=True)

# Authentication & Security Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
if not JWT_SECRET or len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET must be at least 32 characters long. Check .env configuration.")

LOGIN_OTP_REQUIRED = os.getenv("LOGIN_OTP_REQUIRED", "false").lower() in ("true", "1", "yes")
DEV_MODE = os.getenv("DEV_MODE", "false").lower() in ("true", "1", "yes")

# SMTP Email Configuration (STARTTLS port 587)
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@medmatch.com").strip()

