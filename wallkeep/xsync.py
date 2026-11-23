from __future__ import annotations

import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import db, library, paths


@dataclass
class SyncOptions:
    browser: str = "firefox"
    keyring: str = "gnomekeyring"
    proxy: str = ""
    image_only: bool = True


def normalize_user(value: str) -> str:
    value = value.strip()
    match = re.search(r"(?:x|twitter)\.com/([^/?#]+)", value)
    if match:
        value = match.group(1)
    return value.lstrip("@").strip()


def gallery_dl_executable() -> str:
    override = os.environ.get("WALLKEEP_GALLERY_DL")
    if override:
        return override
    candidate = Path(sys.executable).with_name("gallery-dl")
    if candidate.exists():
        return str(candidate)
    found = shutil.which("gallery-dl")
    if found:
        return found
    raise RuntimeError("gallery-dl executable not found; run `uv sync` first")


def sync_user(
    *,
    db_path: Path,
    library_dir: Path,
    user: str,
    options: SyncOptions,
    log: Callable[[str], None],
    cancel: threading.Event,
    on_import: Callable[[dict[str, int]], None] | None = None,
) -> dict[str, object]:
    user = normalize_user(user)
    if not user:
        raise ValueError("empty X username")
    staging = paths.STAGING_DIR / f"x_{user.lower()}"
    staging.mkdir(parents=True, exist_ok=True)
    archive = paths.ARCHIVE_DIR / f"x_{user.lower()}.sqlite3"
    executable = gallery_dl_executable()
    browser_spec = options.browser
    if (
        options.browser in {"chrome", "chromium", "edge", "brave"}
        and options.keyring
        and options.keyring != "auto"
    ):
        browser_spec += "+" + options.keyring
    command = [
        executable,
        "--config-ignore",
        "--cookies-from-browser",
        browser_spec,
        "--download-archive",
        str(archive),
        "--write-metadata",
        "-d",
        str(staging),
    ]
    if options.image_only:
        command += ["--filter", "extension in ('jpg', 'jpeg', 'png', 'webp')"]
    if options.proxy.strip():
        command += ["--proxy", options.proxy.strip()]
    command.append(f"https://x.com/{user}/media")

    log("$ " + " ".join(shlex.quote(part) for part in command))
    started = time.time()
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    tail: list[str] = []
    line_queue: queue.Queue[str | None] = queue.Queue()

    def read_output() -> None:
        try:
            for raw in process.stdout:
                line_queue.put(raw)
        finally:
            line_queue.put(None)

    threading.Thread(target=read_output, daemon=True).start()

    totals = {"downloaded": 0, "duplicate": 0, "similar": 0, "skipped": 0, "failed": 0}
    threshold = int(db.get_setting("similar_threshold", "8") or 0)

    def ready(path: Path) -> bool:
        # gallery-dl writes the JSON sidecar after the image is complete.
        if not (Path(str(path) + ".json").exists() or path.with_suffix(".json").exists()):
            return False
        try:
            return path.stat().st_size > 0
        except OSError:
            return False

    def ingest(final: bool = False) -> None:
        counts = library.import_x_downloads(
            db_path,
            library_dir,
            staging,
            user,
            similar_threshold=threshold,
            ready=None if final else ready,
            prune=final,
            log=log,
            cancel=cancel.is_set,
        )
        for key in totals:
            totals[key] += int(counts.get(key, 0))
        if on_import and any(counts.get(key, 0) for key in ("downloaded", "duplicate", "similar")):
            on_import(counts)

    last_ingest = 0.0
    terminated = False
    while True:
        try:
            raw_line = line_queue.get(timeout=0.4)
        except queue.Empty:
            raw_line = ""
        if raw_line is None:
            break
        if raw_line:
            for line in raw_line.replace("\r", "\n").splitlines():
                line = line.rstrip()
                if not line:
                    continue
                tail.append(line)
                tail = tail[-30:]
                log(line)
        now = time.monotonic()
        if now - last_ingest >= 0.5:
            if not cancel.is_set():
                ingest()
            last_ingest = now
        if cancel.is_set() and not terminated and process.poll() is None:
            terminated = True
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
    returncode = process.wait()
    ingest(final=True)
    counts = totals
    error = None
    if returncode != 0:
        error = "gallery-dl exited with code {}: {}".format(
            returncode, " | ".join(tail[-3:]) if tail else "no output"
        )
        log(error)
    db.update_sync(user, status="ok" if returncode == 0 else "error", error=error)
    return {
        "user": user,
        "returncode": returncode,
        "counts": counts,
        "error": error,
        "elapsed": time.time() - started,
        "cancelled": cancel.is_set(),
    }
