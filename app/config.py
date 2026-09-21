"""Load environment variables used by the API and LLM clients."""

import os

from dotenv import load_dotenv

# Read a local .env if present (never commit real keys).
load_dotenv()


def _env(name: str, default: str = "") -> str:
    """Return a stripped env var, or default when missing."""
    value = os.getenv(name, default)
    return value.strip() if value else default


# Optional Free-AI Gateway (OpenAI-compatible HTTP proxy).
FREE_AI_GATEWAY_URL = _env("FREE_AI_GATEWAY_URL")
FREE_AI_GATEWAY_API_KEY = _env("FREE_AI_GATEWAY_API_KEY", "not-needed")

# Groq OpenAI-compatible API (works without running the Node gateway).
GROQ_API_KEY = _env("GROQ_API_KEY")
GROQ_MODEL = _env("GROQ_MODEL", "openai/gpt-oss-20b")

# Primary LLM gateway (OpenRouter).
OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY")
OPENROUTER_MODEL = _env("OPENROUTER_MODEL", "openai/gpt-4o-mini")

# Fallback LLM (Google Gemini direct).
GEMINI_API_KEY = _env("GEMINI_API_KEY")
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-2.0-flash")

# Per-request LLM timeout; keep well under the 30s API budget.
LLM_TIMEOUT_SECONDS = float(_env("LLM_TIMEOUT_SECONDS", "12"))

# Server bind port (Dockerfile / uvicorn also default to 8000).
PORT = int(_env("PORT", "8000"))
