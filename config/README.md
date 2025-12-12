# Configuration Guide

This directory contains configuration files for the ARCC Tracker application.

The application supports **two configuration methods**:
1. **`.env` file** (for local development)
2. **Streamlit secrets** (`.streamlit/secrets.toml` for local, or Streamlit Cloud secrets)

The configuration system will check Streamlit secrets first, then fall back to `.env` files.

## Setup

### Option 1: Using .env file (Local Development)

1. **Create your `.env` file:**
   ```bash
   cp config/env.sample config/.env
   ```

2. **Edit `config/.env` with your settings:**
   - Set `GPT_SERVICES_ENABLED=true` to enable AI features (requires OpenAI API key)
   - Set `AUTH_ENABLED=true` to enable email-based authentication
   - Add allowed email addresses to `ALLOWED_EMAILS` (comma-separated)
   - Add your `OPENAI_API_KEY` if using GPT services

### Option 2: Using Streamlit Secrets (Recommended for Streamlit Cloud)

1. **For local development:**
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   # Edit .streamlit/secrets.toml with your settings
   ```

2. **For Streamlit Cloud:**
   - Go to your app's dashboard
   - Navigate to: **Settings > Secrets**
   - Add secrets in TOML format (see `.streamlit/secrets.toml.example`)

**Note:** Streamlit secrets take priority over `.env` files when both are present.

## Configuration Options

### GPT Services
- `GPT_SERVICES_ENABLED`: Enable/disable GPT-powered features (AI summaries, reports)
  - Set to `"true"` to enable (requires `OPENAI_API_KEY`)
  - Set to `"false"` to disable (useful for deployment without API keys)
  - **In .env:** `GPT_SERVICES_ENABLED=true`
  - **In secrets.toml:** `GPT_SERVICES_ENABLED = "true"`

### Authentication
- `AUTH_ENABLED`: Enable/disable email-based authentication
  - Set to `"true"` to require authentication
  - Set to `"false"` to allow unrestricted access (NOT recommended for production)
  - **In .env:** `AUTH_ENABLED=true`
  - **In secrets.toml:** `AUTH_ENABLED = "true"`
  
- `ALLOWED_EMAILS`: Comma-separated list of allowed email addresses
  - **In .env:** `ALLOWED_EMAILS=user1@example.com,user2@example.com,admin@example.com`
  - **In secrets.toml:** 
    ```toml
    ALLOWED_EMAILS = "user1@example.com,user2@example.com,admin@example.com"
    # OR as a list:
    ALLOWED_EMAILS = ["user1@example.com", "user2@example.com", "admin@example.com"]
    ```

### API Keys
- `OPENAI_API_KEY`: Your OpenAI API key (required if `GPT_SERVICES_ENABLED=true`)
  - **In .env:** `OPENAI_API_KEY=sk-...`
  - **In secrets.toml:** `OPENAI_API_KEY = "sk-..."`
- `NCBI_API_KEY`: Optional NCBI API key for PubMed data fetching
- `NCBI_EMAIL`: Optional email for NCBI API requests

## Security Notes

**IMPORTANT:**
- Never commit `.env` files or `secrets.toml` to version control
- Both files are already in `.gitignore`
- Keep your API keys secure
- Use strong email restrictions in production
- For Streamlit Cloud, use the dashboard secrets manager instead of committing secrets.toml

## Example Configurations

### .env file format:
```env
# Enable GPT services
GPT_SERVICES_ENABLED=true
OPENAI_API_KEY=sk-...

# Enable authentication
AUTH_ENABLED=true
ALLOWED_EMAILS=admin@university.edu,researcher@university.edu

# Optional NCBI settings
NCBI_API_KEY=your_ncbi_key
NCBI_EMAIL=your_email@university.edu
```

### secrets.toml format:
```toml
# Enable GPT services
GPT_SERVICES_ENABLED = "true"
OPENAI_API_KEY = "sk-..."

# Enable authentication
AUTH_ENABLED = "true"
ALLOWED_EMAILS = "admin@university.edu,researcher@university.edu"

# Optional NCBI settings
NCBI_API_KEY = "your_ncbi_key"
NCBI_EMAIL = "your_email@university.edu"
```

## Configuration Priority

The application checks configuration in this order:
1. **Streamlit secrets** (`st.secrets`) - highest priority
2. **Environment variables** (`.env` file or system env vars) - fallback
3. **Default values** - if neither is available

This means if you have both `.env` and `secrets.toml`, Streamlit secrets will be used.

