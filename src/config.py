"""Configuration management using environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

GOOGLE_CREDENTIALS_PATH = os.getenv(
    "GOOGLE_CREDENTIALS_PATH",
    str(BASE_DIR / "credentials.json")
)

GMAIL_USER_EMAIL = os.getenv("GMAIL_USER_EMAIL", "")

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    str(BASE_DIR / "data" / "gmail_cleaner.db")
)

LOG_PATH = os.getenv("LOG_PATH", str(BASE_DIR / "logs"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
]


def validate_config() -> list[str]:
    """Validate configuration and return list of errors."""
    errors = []

    if not GMAIL_USER_EMAIL:
        errors.append("GMAIL_USER_EMAIL is not set in .env")

    if not Path(GOOGLE_CREDENTIALS_PATH).exists():
        errors.append(f"Credentials file not found: {GOOGLE_CREDENTIALS_PATH}")

    return errors
