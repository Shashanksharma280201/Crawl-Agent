"""Shared OpenAI helpers: .env loading + client construction.

Used by the on-demand summary endpoint in the web app. Never hardcodes a key.
"""
import os

# Repo root (parent of web/) so the default `.env` lookup resolves to the
# project-root .env, not web/.env.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_dotenv(path=None):
    """Minimal .env parser -> populates os.environ (does not overwrite existing)."""
    path = path or os.path.join(BASE_DIR, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def get_client():
    """Return (OpenAI client, model). Raises RuntimeError with a clear message
    if the key is missing."""
    load_dotenv()
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Paste your key into the .env file "
            "(OPENAI_API_KEY=sk-...) and retry."
        )
    from openai import OpenAI
    model = os.environ.get("OPENAI_MODEL", "gpt-4o").strip() or "gpt-4o"
    return OpenAI(api_key=key), model
