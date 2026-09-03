"""One place to turn logging on: console plus a rotating file under logs/.

The stdout of a background uvicorn is wherever the shell that started it put it, and on
2026-09-03 the only record of two failed live calls was a temp file one session happened
to redirect into. The file here survives restarts and is what to read after a bad call:
every [turn], [hops] and [tool] line for a session, with its timings.
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(os.getenv("LOG_DIR") or Path(__file__).resolve().parent.parent / "logs")
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup(level: int = logging.INFO) -> Path:
    root = logging.getLogger("pitchpilot")
    if root.handlers:
        return LOG_DIR / "backend.log"
    root.setLevel(level)
    root.propagate = False

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(FORMAT))
    root.addHandler(console)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / "backend.log"
    rotating = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    rotating.setFormatter(logging.Formatter(FORMAT))
    root.addHandler(rotating)
    return path
