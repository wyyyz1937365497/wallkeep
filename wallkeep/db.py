from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from . import paths

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256 TEXT NOT NULL UNIQUE,
    dhash TEXT,
    phash TEXT,
    path TEXT NOT NULL UNIQUE,
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    bytes INTEGER NOT NULL DEFAULT 0,
    mime TEXT,
    origin TEXT NOT NULL,
    favorite INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    user TEXT NOT NULL,
    post_id TEXT NOT NULL,
    media_index INTEGER NOT NULL DEFAULT 0,
    url TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    posted_at INTEGER,
    asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'seen',
    first_seen INTEGER NOT NULL,
    downloaded_at INTEGER,
    match_asset_id INTEGER,
    match_distance INTEGER,
    match_kind TEXT,
    UNIQUE (platform, user, post_id, media_index)
);

CREATE INDEX IF NOT EXISTS idx_sources_asset ON sources(asset_id);
CREATE INDEX IF NOT EXISTS idx_sources_user ON sources(platform, user);
CREATE INDEX IF NOT EXISTS idx_assets_created ON assets(created_at);

CREATE TABLE IF NOT EXISTS sync_state (
    platform TEXT NOT NULL,
    user TEXT NOT NULL,
    last_sync INTEGER,
    last_status TEXT,
    last_error TEXT,
    PRIMARY KEY (platform, user)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "library_dir": str(paths.DEFAULT_LIBRARY_DIR),
    "cookies_browser": "firefox",
    "cookies_keyring": "gnomekeyring",
    "proxy": "",
    "image_only": "1",
    "language": "auto",
    "similar_threshold": "8",
    "x_include_videos": "0",
    "rotation_enabled": "0",
    "rotation_interval_minutes": "30",
    "rotation_mode": "shuffle",
    "rotation_scope": "all",
    "rotation_include_videos": "1",
    "wallpaper_fill_mode": "cover",
    "wallpaper_current_id": "",
    "wallpaper_current_path": "",
    "shell_theme_monochrome": "0",
    "shell_palette_before_mono": "",
    "shell_parallax_workspace": "0",
    "shell_parallax_zoom": "1.07",
    "shell_parallax_vertical": "0",
    "shell_parallax_sidebar": "0",
}


def connect(path: Path = paths.DB_PATH) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_db(path: Path = paths.DB_PATH) -> None:
    paths.ensure_dirs()
    with connect(path) as connection:
        connection.executescript(SCHEMA)
        _migrate(connection)
        for key, value in DEFAULT_SETTINGS.items():
            connection.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value)
            )


def _migrate(connection: sqlite3.Connection) -> None:
    """Add columns introduced after the first release without dropping data."""
    asset_columns = {row[1] for row in connection.execute("PRAGMA table_info(assets)")}
    if "phash" not in asset_columns:
        connection.execute("ALTER TABLE assets ADD COLUMN phash TEXT")
    if "favorite" not in asset_columns:
        connection.execute("ALTER TABLE assets ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0")
    source_columns = {row[1] for row in connection.execute("PRAGMA table_info(sources)")}
    for name, declaration in (
        ("match_asset_id", "INTEGER"),
        ("match_distance", "INTEGER"),
        ("match_kind", "TEXT"),
    ):
        if name not in source_columns:
            connection.execute(f"ALTER TABLE sources ADD COLUMN {name} {declaration}")


def get_setting(key: str, default: str = "") -> str:
    with connect() as connection:
        row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with connect() as connection:
        connection.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )


def library_dir() -> Path:
    return Path(get_setting("library_dir", str(paths.DEFAULT_LIBRARY_DIR))).expanduser()


def asset_by_sha(connection: sqlite3.Connection, sha256: str) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM assets WHERE sha256 = ?", (sha256,)).fetchone()


def asset_by_path(connection: sqlite3.Connection, path: str | Path) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM assets WHERE path = ?", (str(path),)).fetchone()


def insert_asset(
    connection: sqlite3.Connection,
    *,
    sha256: str,
    path: Path,
    width: int,
    height: int,
    size: int,
    mime: str | None,
    origin: str,
    dhash: str | None = None,
    phash: str | None = None,
    created_at: int | None = None,
) -> tuple[int, bool]:
    """Return (asset_id, created). Existing hashes are never duplicated."""
    now = int(time.time())
    cursor = connection.execute(
        "INSERT OR IGNORE INTO assets"
        "(sha256, dhash, phash, path, width, height, bytes, mime, origin, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            sha256,
            dhash,
            phash,
            str(path),
            width,
            height,
            size,
            mime or "",
            origin,
            created_at or now,
        ),
    )
    if cursor.rowcount:
        return int(cursor.lastrowid), True
    row = asset_by_sha(connection, sha256)
    if row is None:
        row = asset_by_path(connection, path)
    assert row is not None
    return int(row["id"]), False


def source_by_key(
    connection: sqlite3.Connection, platform: str, user: str, post_id: str, media_index: int
) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM sources WHERE platform = ? AND user = ? AND post_id = ? AND media_index = ?",
        (platform, user, post_id, media_index),
    ).fetchone()


def add_source(
    connection: sqlite3.Connection,
    *,
    platform: str,
    user: str,
    post_id: str,
    media_index: int,
    url: str,
    author: str,
    posted_at: int | None,
    asset_id: int | None,
    status: str,
    match_asset_id: int | None = None,
    match_distance: int | None = None,
    match_kind: str = "",
) -> tuple[int, bool]:
    now = int(time.time())
    cursor = connection.execute(
        "INSERT OR IGNORE INTO sources"
        "(platform, user, post_id, media_index, url, author, posted_at, asset_id, status, "
        "first_seen, downloaded_at, match_asset_id, match_distance, match_kind) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            platform,
            user,
            post_id,
            media_index,
            url,
            author,
            posted_at,
            asset_id,
            status,
            now,
            now if status in {"downloaded", "duplicate", "similar"} else None,
            match_asset_id,
            match_distance,
            match_kind,
        ),
    )
    if cursor.rowcount:
        return int(cursor.lastrowid), True
    row = source_by_key(connection, platform, user, post_id, media_index)
    assert row is not None
    if row["asset_id"] is None and asset_id is not None:
        connection.execute(
            "UPDATE sources SET asset_id = ?, status = ?, downloaded_at = COALESCE(downloaded_at, ?), "
            "match_asset_id = ?, match_distance = ?, match_kind = ? WHERE id = ?",
            (asset_id, status, now, match_asset_id, match_distance, match_kind, row["id"]),
        )
    return int(row["id"]), False


def ensure_user(user: str) -> None:
    with connect() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO sync_state(platform, user) VALUES ('x', ?)", (user,)
        )


def update_sync(user: str, *, status: str, error: str | None = None) -> None:
    with connect() as connection:
        connection.execute(
            "INSERT INTO sync_state(platform, user, last_sync, last_status, last_error) "
            "VALUES ('x', ?, ?, ?, ?) "
            "ON CONFLICT(platform, user) DO UPDATE SET "
            "last_sync = excluded.last_sync, last_status = excluded.last_status, last_error = excluded.last_error",
            (user, int(time.time()), status, error or ""),
        )


def fetch_stats() -> dict[str, int]:
    with connect() as connection:
        local = connection.execute("SELECT COUNT(*) FROM assets WHERE origin = 'local'").fetchone()[0]
        total = connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        x = connection.execute(
            "SELECT COUNT(DISTINCT a.id) FROM assets a "
            "JOIN sources s ON s.asset_id = a.id WHERE s.platform = 'x'"
        ).fetchone()[0]
        favorites = connection.execute("SELECT COUNT(*) FROM assets WHERE favorite = 1").fetchone()[0]
        return {
            "total": int(total),
            "local": int(local),
            "x": int(x),
            "favorites": int(favorites),
        }


def fetch_users() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT u.user, "
            "  (SELECT COUNT(DISTINCT s.asset_id) FROM sources s WHERE s.platform='x' AND s.user=u.user) AS count, "
            "  st.last_sync, st.last_status, st.last_error "
            "FROM (SELECT DISTINCT user FROM sources WHERE platform='x' UNION SELECT user FROM sync_state WHERE platform='x') u "
            "LEFT JOIN sync_state st ON st.platform='x' AND st.user=u.user "
            "ORDER BY u.user COLLATE NOCASE"
        ).fetchall()
        return [dict(row) for row in rows]


def fetch_assets(kind: str = "all", user: str | None = None, search: str = "") -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if kind == "local":
        clauses.append("a.origin = 'local'")
    elif kind == "favorites":
        clauses.append("a.favorite = 1")
    elif kind == "x":
        clauses.append("EXISTS (SELECT 1 FROM sources s WHERE s.asset_id = a.id AND s.platform = 'x')")
    if user:
        clauses.append(
            "EXISTS (SELECT 1 FROM sources s WHERE s.asset_id = a.id AND s.platform = 'x' AND s.user = ?)"
        )
        params.append(user)
    if search.strip():
        term = f"%{search.strip()}%"
        clauses.append(
            "(a.path LIKE ? OR EXISTS (SELECT 1 FROM sources s WHERE s.asset_id = a.id "
            "AND (s.user LIKE ? OR s.author LIKE ? OR s.post_id LIKE ?)))"
        )
        params.extend([term, term, term, term])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT a.*, s.user AS source_user, s.author AS source_author, s.url AS source_url,
               s.post_id AS source_post_id, s.posted_at AS source_posted_at, s.status AS source_status
        FROM assets a
        LEFT JOIN sources s ON s.id = (
            SELECT id FROM sources WHERE asset_id = a.id ORDER BY (platform = 'x') DESC, id LIMIT 1
        )
        {where}
        ORDER BY a.created_at DESC, a.id DESC
    """
    with connect() as connection:
        rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def fetch_asset(asset_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT a.*, s.user AS source_user, s.author AS source_author, s.url AS source_url, "
            "s.post_id AS source_post_id, s.posted_at AS source_posted_at, s.status AS source_status "
            "FROM assets a LEFT JOIN sources s ON s.id = ("
            "  SELECT id FROM sources WHERE asset_id = a.id ORDER BY (platform = 'x') DESC, id LIMIT 1"
            ") WHERE a.id = ?",
            (asset_id,),
        ).fetchone()
        return dict(row) if row else None


def set_favorite(asset_id: int, favorite: bool) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE assets SET favorite = ? WHERE id = ?",
            (1 if favorite else 0, asset_id),
        )


def fetch_rotation_pool(scope: str = "all", include_videos: bool = True) -> list[dict[str, Any]]:
    clauses: list[str] = []
    if scope == "favorites":
        clauses.append("a.favorite = 1")
    elif scope == "local":
        clauses.append("a.origin = 'local'")
    if not include_videos:
        clauses.append("(a.mime IS NULL OR a.mime NOT LIKE 'video/%')")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as connection:
        rows = connection.execute(
            f"SELECT a.* FROM assets a {where} ORDER BY a.id"
        ).fetchall()
        return [dict(row) for row in rows]
