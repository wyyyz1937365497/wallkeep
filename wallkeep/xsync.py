from __future__ import annotations

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
    for raw_line in process.stdout:
        if cancel.is_set():
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            break
        for line in raw_line.replace("\r", "\n").splitlines():
            line = line.rstrip()
            if not line:
                continue
            tail.append(line)
            tail = tail[-30:]
            log(line)
    returncode = process.wait()

    counts = library.import_x_downloads(
        db_path,
        library_dir,
        staging,
        user,
        similar_threshold=int(db.get_setting("similar_threshold", "8") or 0),
        log=log,
        cancel=cancel.is_set,
    )
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
