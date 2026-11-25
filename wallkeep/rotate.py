from __future__ import annotations

import argparse
import fcntl
import random
import signal
import time
from pathlib import Path

from . import db, paths, wallpaper


def select_asset(
    scope: str, include_videos: bool, mode: str
) -> dict | None:
    pool = db.fetch_rotation_pool(scope, include_videos)
    if not pool:
        return None
    current_id = int(db.get_setting("wallpaper_current_id", "0") or 0)
    if mode == "sequential":
        for asset in pool:
            if int(asset["id"]) > current_id:
                return asset
        return pool[0]
    candidates = [asset for asset in pool if int(asset["id"]) != current_id]
    return random.SystemRandom().choice(candidates or pool)


def apply_asset(asset: dict) -> str:
    fill_mode = db.get_setting("wallpaper_fill_mode", "cover")
    method = wallpaper.set_wallpaper(Path(asset["path"]), fill_mode)
    db.set_setting("wallpaper_current_id", str(asset["id"]))
    db.set_setting("wallpaper_current_path", str(asset["path"]))
    return method


def next_wallpaper() -> dict:
    scope = db.get_setting("rotation_scope", "all")
    include_videos = db.get_setting("rotation_include_videos", "1") == "1"
    mode = db.get_setting("rotation_mode", "shuffle")
    asset = select_asset(scope, include_videos, mode)
    if asset is None:
        raise RuntimeError("no wallpapers match the rotation settings")
    method = apply_asset(asset)
    return {"asset": asset, "method": method}


def daemon() -> int:
    paths.ensure_dirs()
    lock_path = paths.CACHE_DIR / "rotate.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = open(lock_path, "w", encoding="utf-8")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("wallkeep-rotate: another rotation daemon is already running", flush=True)
        return 0

    stop = False

    def request_stop(_signum, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    next_run = 0.0
    while not stop:
        enabled = db.get_setting("rotation_enabled", "0") == "1"
        try:
            interval = max(1, int(db.get_setting("rotation_interval_minutes", "30") or 30))
        except ValueError:
            interval = 30
        now = time.monotonic()
        if enabled and now >= next_run:
            try:
                result = next_wallpaper()
                asset = result["asset"]
                print(
                    f"wallkeep-rotate: {asset['path']} ({result['method']})",
                    flush=True,
                )
                next_run = now + interval * 60
            except Exception as error:  # noqa: BLE001 - daemon keeps running
                print(f"wallkeep-rotate: {error}", flush=True)
                next_run = now + 60
        elif not enabled:
            next_run = now
        deadline = min(15.0, max(0.5, next_run - time.monotonic())) if enabled else 15.0
        time.sleep(deadline)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wallkeep wallpaper rotation")
    parser.add_argument("--daemon", action="store_true", help="run continuously")
    parser.add_argument("--once", action="store_true", help="apply one wallpaper and exit")
    args = parser.parse_args(argv)
    if args.once:
        try:
            result = next_wallpaper()
        except Exception as error:  # noqa: BLE001 - CLI
            print(f"wallkeep-rotate: {error}", flush=True)
            return 1
        print(result["asset"]["path"], flush=True)
        return 0
    if args.daemon:
        return daemon()
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
