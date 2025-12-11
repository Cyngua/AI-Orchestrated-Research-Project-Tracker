# Configuration Guide

This directory contains configuration files for the ARCC Tracker application.

## Setup

1. **Create your `.env` file:**
   ```bash
   cp .env.sample .env
   ```

2. **Edit `.env` with your settings:**
   - Set `GPT_SERVICES_ENABLED=true` to enable AI features (requires OpenAI API key)
   - Set `AUTH_ENABLED=true` to enable email-based authentication
   - Add allowed email addresses to `ALLOWED_EMAILS` (comma-separated)
   - Add your `OPENAI_API_KEY` if using GPT services

## Configuration Options

### GPT Services
- `GPT_SERVICES_ENABLED`: Enable/disable GPT-powered features (AI summaries, reports)
  - Set to `"true"` to enable (requires `OPENAI_API_KEY`)
  - Set to `"false"` to disable (useful for deployment without API keys)

### Authentication
- `AUTH_ENABLED`: Enable/disable email-based authentication
  - Set to `"true"` to require authentication
  - Set to `"false"` to allow unrestricted access (NOT recommended for production)
  
- `ALLOWED_EMAILS`: Comma-separated list of allowed email addresses
  - Example: `ALLOWED_EMAILS=user1@example.com,user2@example.com,admin@example.com`

### API Keys
- `OPENAI_API_KEY`: Your OpenAI API key (required if `GPT_SERVICES_ENABLED=true`)
- `NCBI_API_KEY`: Optional NCBI API key for PubMed data fetching
- `NCBI_EMAIL`: Optional email for NCBI API requests

## Security Notes

**IMPORTANT:**
- Never commit `.env` files to version control
- The `.env` file is already in `.gitignore`
- Keep your API keys secure
- Use strong email restrictions in production

## Example Configuration

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

