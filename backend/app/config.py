"""Environment settings. Values come from the host or a local .env file."""

import os

from dotenv import load_dotenv

# Read a local .env if present (never commit real keys).
load_dotenv()


def _env(name: str, default: str = "") -> str:
    """Return a stripped env var, or default when missing."""
    value = os.getenv(name, "").strip()
    return value or default


# LLM providers, tried in this order. Each one is optional; set at least one key.
GROQ_API_KEY = _env("GROQ_API_KEY")
GROQ_MODEL = _env("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_FALLBACK_MODEL = _env("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")

OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY")
OPENROUTER_MODEL = _env("OPENROUTER_MODEL", "openai/gpt-4o-mini")

GEMINI_API_KEY = _env("GEMINI_API_KEY")
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-2.0-flash")

# Per-call LLM timeout; keeps the whole request well under the 30s budget.
LLM_TIMEOUT_SECONDS = float(_env("LLM_TIMEOUT_SECONDS", "12"))
