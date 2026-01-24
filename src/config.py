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
LOG_MAX_SIZE = int(os.getenv("LOG_MAX_SIZE", str(5 * 1024 * 1024)))  # 5 MB default
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "3"))

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", "500"))

# Folder exclusions
EXCLUDE_TRASH = os.getenv("EXCLUDE_TRASH", "false").lower() == "true"
EXCLUDE_SPAM = os.getenv("EXCLUDE_SPAM", "false").lower() == "true"
EXCLUDE_DRAFTS = os.getenv("EXCLUDE_DRAFTS", "false").lower() == "true"
EXCLUDE_SENT = os.getenv("EXCLUDE_SENT", "false").lower() == "true"

# SMTP settings for email reports
SMTP_ENABLED = os.getenv("SMTP_ENABLED", "false").lower() == "true"
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")
SMTP_TO = os.getenv("SMTP_TO", "")
SMTP_TLS = os.getenv("SMTP_TLS", "true").lower() == "true"

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
