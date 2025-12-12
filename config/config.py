"""
Configuration management for the ARCC Tracker application.
Handles feature flags and settings that can be toggled without code changes.
Reads from both .env files and Streamlit secrets (st.secrets).
"""
import os
from pathlib import Path
from typing import List, Optional, Any
from dotenv import load_dotenv

# Load environment variables
CONFIG_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = CONFIG_DIR.parent
load_dotenv(CONFIG_DIR / ".env")

def _get_config_value(key: str, default: Any = None) -> Any:
    """
    Get configuration value from Streamlit secrets first, then environment variables.
    Falls back to default if neither is available.
    
    Priority:
    1. st.secrets (Streamlit Cloud/local secrets.toml)
    2. os.getenv (environment variables/.env file)
    3. default value
    """
    # Try Streamlit secrets first (only available when running in Streamlit)
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and key in st.secrets:
            return st.secrets[key]
    except (ImportError, RuntimeError, AttributeError):
        # Not running in Streamlit or secrets not available
        pass
    
    # Fall back to environment variables
    return os.getenv(key, default)

def _get_config_list(key: str, default: str = "") -> List[str]:
    """Get configuration value as a list (comma-separated string)."""
    value = _get_config_value(key, default)
    if isinstance(value, list):
        return [item.strip().lower() for item in value if item.strip()]
    if isinstance(value, str):
        return [email.strip().lower() for email in value.split(",") if email.strip()]
    return []

# GPT Service Configuration
GPT_SERVICES_ENABLED = _get_config_value("GPT_SERVICES_ENABLED", "false").lower() == "true"

# Authentication Configuration
ALLOWED_EMAILS = _get_config_list("ALLOWED_EMAILS", "")

# Authentication enabled/disabled
AUTH_ENABLED = _get_config_value("AUTH_ENABLED", "true").lower() == "true"

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

