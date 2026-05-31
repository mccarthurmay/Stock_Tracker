"""Configuration for the research data spine.

Named ``settings`` (not ``config``) on purpose: the repo's root .gitignore
reserves ``config.py`` for gitignored credential files (e.g. backend/config.py),
so this version-controlled settings module must avoid that name.

Credentials are read from the environment (or a research/.env file). If they
are absent, we source the backend's credential file (backend/config.py), which
is where this project keeps its Alpaca keys. Keys are never hard-coded here.
The free Alpaca tier serves options from the *indicative* feed, recorded as
the default (ROADMAP §2a).
"""
from __future__ import annotations

import os
from pathlib import Path

try:  # optional: load research/.env if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:  # pragma: no cover - dotenv is optional
    pass

RESEARCH_DIR = Path(__file__).resolve().parent
REPO_ROOT = RESEARCH_DIR.parent
DATA_DIR = RESEARCH_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "research.duckdb"
BACKEND_CONFIG = REPO_ROOT / "backend" / "config.py"

# Free Basic plan -> options come from the indicative feed; equities from IEX.
# These are recorded on every pull so a later run can never silently mix feeds.
OPTIONS_FEED = os.getenv("ALPACA_OPTIONS_FEED", "indicative").lower()
STOCK_FEED = os.getenv("ALPACA_STOCK_FEED", "iex").lower()

# Alpaca's data API allows ~200 req/min on the free tier; stay under it.
MAX_REQUESTS_PER_MINUTE = int(os.getenv("ALPACA_MAX_RPM", "180"))

# Underlying price adjustment. 'split' keeps strikes comparable across splits
# without applying retroactive dividend adjustment. Note: any adjustment is
# applied with *today's* factors, a mild lookahead — documented in README.
UNDERLYING_ADJUSTMENT = os.getenv("ALPACA_ADJUSTMENT", "split").lower()


def source_backend_env() -> None:
    """Populate ALPACA_* / FRED_* env vars by executing backend/config.py.

    backend/config.py is a gitignored script that sets os.environ for the
    Alpaca (and FRED) keys. Executing it only mutates the environment; it does
    not import the Flask app.
    """
    if not BACKEND_CONFIG.exists():
        return
    try:
        code = compile(BACKEND_CONFIG.read_text(), str(BACKEND_CONFIG), "exec")
        exec(code, {"__name__": "_backend_config", "__file__": str(BACKEND_CONFIG)})
    except Exception:  # pragma: no cover - best-effort convenience
        pass


def get_credentials() -> tuple[str, str]:
    """Return (key, secret) from env, research/.env, or backend/config.py."""
    key, secret = os.getenv("ALPACA_KEY"), os.getenv("ALPACA_SECRET")
    if not key or not secret:
        source_backend_env()
        key, secret = os.getenv("ALPACA_KEY"), os.getenv("ALPACA_SECRET")
    if not key or not secret:
        raise RuntimeError(
            "ALPACA_KEY / ALPACA_SECRET are not set. Export them, create "
            "research/.env, or keep them in backend/config.py."
        )
    return key, secret
