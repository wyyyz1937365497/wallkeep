from __future__ import annotations

import os
from pathlib import Path


def _xdg(name: str, fallback: str) -> Path:
    value = os.environ.get(name)
    return Path(value) if value else Path.home() / fallback


DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share") / "wallkeep"
CACHE_DIR = _xdg("XDG_CACHE_HOME", ".cache") / "wallkeep"
CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "wallkeep"

DB_PATH = DATA_DIR / "wallkeep.db"
ARCHIVE_DIR = DATA_DIR / "archives"
STAGING_DIR = DATA_DIR / "staging"
THUMB_DIR = CACHE_DIR / "thumbs"
GALLERY_DL_CONFIG = DATA_DIR / "gallery-dl-empty.json"

DEFAULT_LIBRARY_DIR = Path.home() / "Pictures" / "wallkeep"


def ensure_dirs() -> None:
    for directory in (DATA_DIR, ARCHIVE_DIR, STAGING_DIR, THUMB_DIR, CONFIG_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    if not GALLERY_DL_CONFIG.exists():
        GALLERY_DL_CONFIG.write_text("{}\n", encoding="utf-8")
