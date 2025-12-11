"""
Configuration management for the ARCC Tracker application.
Handles feature flags and settings that can be toggled without code changes.
"""
import os
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables
CONFIG_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = CONFIG_DIR.parent
load_dotenv(CONFIG_DIR / ".env")

# GPT Service Configuration
GPT_SERVICES_ENABLED = os.getenv("GPT_SERVICES_ENABLED", "false").lower() == "true"

# Authentication Configuration
ALLOWED_EMAILS = os.getenv("ALLOWED_EMAILS", "").split(",")
ALLOWED_EMAILS = [email.strip().lower() for email in ALLOWED_EMAILS if email.strip()]

# Authentication enabled/disabled
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() == "true"

def is_gpt_enabled() -> bool:
    """Check if GPT services are enabled."""
    return GPT_SERVICES_ENABLED

def is_email_allowed(email: str) -> bool:
    """Check if an email address is allowed to access the app."""
    if not AUTH_ENABLED:
        return True  # If auth is disabled, allow all
    if not email:
        return False
    return email.strip().lower() in ALLOWED_EMAILS

def get_allowed_emails() -> List[str]:
    """Get list of allowed email addresses."""
    return ALLOWED_EMAILS.copy()

