"""Settings are read from environment variables (or a local .env file)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Tiny .env loader so we don't need an extra dependency. Never commit .env."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

DOCS_DIR = Path(os.getenv("WIA_DOCS_DIR", ROOT / "data" / "docs"))
DB_PATH = Path(os.getenv("WIA_DB_PATH", ROOT / "data" / "wia.db"))
AUDIT_LOG = Path(os.getenv("WIA_AUDIT_LOG", ROOT / "data" / "audit.jsonl"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")

TOP_K = int(os.getenv("WIA_TOP_K", "4"))
# Below this retrieval score we refuse instead of asking the LLM to guess.
MIN_SCORE = float(os.getenv("WIA_MIN_SCORE", "0.12"))
