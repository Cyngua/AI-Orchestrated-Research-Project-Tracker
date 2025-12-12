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
    
    This function is called lazily (when needed), so st.secrets will be available.
    """
    value = None
    
    # Try Streamlit secrets first (only available when running in Streamlit)
    try:
        import streamlit as st
        # Check if st.secrets is available and has the key
        if hasattr(st, 'secrets'):
            try:
                # Access st.secrets
                secrets_dict = st.secrets
                if key in secrets_dict:
                    value = secrets_dict[key]
            except (AttributeError, KeyError, TypeError, Exception):
                # st.secrets might not be fully initialized or key doesn't exist
                pass
    except (ImportError, RuntimeError, AttributeError):
        # Not running in Streamlit or secrets not available
        pass
    
    # Fall back to environment variables if not found in secrets
    if value is None:
        value = os.getenv(key, default)
    
    return value

def _get_config_list(key: str, default: str = "") -> List[str]:
    """Get configuration value as a list (comma-separated string)."""
    value = _get_config_value(key, default)
    if isinstance(value, list):
        return [item.strip().lower() for item in value if item.strip()]
    if isinstance(value, str):
        return [email.strip().lower() for email in value.split(",") if email.strip()]
    return []

def is_gpt_enabled() -> bool:
    """Check if GPT services are enabled."""
    return _get_config_value("GPT_SERVICES_ENABLED", "false").lower() == "true"

def get_auth_enabled() -> bool:
    """Get authentication enabled status."""
    return _get_config_value("AUTH_ENABLED", "true").lower() == "true"

def get_allowed_emails() -> List[str]:
    """Get list of allowed email addresses."""
    return _get_config_list("ALLOWED_EMAILS", "")

def is_email_allowed(email: str) -> bool:
    """Check if an email address is allowed to access the app."""
    if not get_auth_enabled():
        return True  # If auth is disabled, allow all
    if not email:
        return False
    allowed_emails = get_allowed_emails()
    return email.strip().lower() in allowed_emails

def __getattr__(name: str):
    if name == "GPT_SERVICES_ENABLED":
        return is_gpt_enabled()
    elif name == "AUTH_ENABLED":
        return get_auth_enabled()
    elif name == "ALLOWED_EMAILS":
        return get_allowed_emails()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

