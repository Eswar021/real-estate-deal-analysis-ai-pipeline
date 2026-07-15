"""T12 pipeline logging — owned by the pipeline (works for the UI and the CLI/tests alike).

`configure_logging()` sets up ONE rotating file handler on the `t12` logger from
`config/logging.json` (env-overridable). It is file-only by design — the terminal stays clean.
Call it once at startup: the UI does so in `t12_mapping.apps.ready()`, the CLI in `run_parse`.

The active PROFILE decides how much the renderers in `parse_log` emit:
  - "summary" (default): banners + step summaries + the anchor/classification/NOI tables.
  - "verbose": the above PLUS the exact LLM input/output for every agent call, full reasons,
    and per-row scoring detail.
"""
import json
import logging
import logging.handlers
import os
from pathlib import Path

from .paths import LOGGING_CONFIG_PATH, LOG_DIR


def _load():
    try:
        with open(LOGGING_CONFIG_PATH) as f:
            return {k: v for k, v in json.load(f).items() if not k.startswith(("$", "version"))}
    except FileNotFoundError:
        return {}


_CFG = _load()
PROFILE = os.environ.get("T12_LOG_PROFILE", _CFG.get("profile", "summary")).strip().lower()


def profile():
    return PROFILE


def is_verbose():
    return PROFILE == "verbose"


def log_file_path():
    return os.environ.get("T12_LOG_FILE") or str(LOG_DIR / _CFG.get("file", "t12.log"))


_configured = False


def configure_logging():
    """Idempotent: attach the rotating file handler to the `t12` logger (file-only)."""
    global _configured
    if _configured:
        return
    _configured = True

    logger = logging.getLogger("t12")
    logger.setLevel(getattr(logging, os.environ.get("T12_LOG_LEVEL", _CFG.get("level", "DEBUG")).upper(), logging.DEBUG))
    logger.propagate = False   # never bubble to the root/console handlers → no terminal noise

    if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in logger.handlers):
        return
    path = Path(log_file_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=int(_CFG.get("max_bytes", 5_000_000)), backupCount=int(_CFG.get("backup_count", 5)))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(name)s: %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    logger.info("logging configured · profile=%s · file=%s", PROFILE, path)
