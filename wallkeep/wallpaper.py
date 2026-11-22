from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def _run(command: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


def set_wallpaper(path: Path) -> str:
    """Set the wallpaper through the running desktop stack.

    Returns a short description of the method that worked. Raises if all
    candidates fail.
    """
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    attempts: list[tuple[str, list[str]]] = [
        ("quickshell", ["qs", "-c", "ii", "ipc", "call", "wallpapers", "apply", str(path)]),
        ("swww", ["swww", "img", str(path)]),
        ("hyprpaper", ["hyprctl", "hyprpaper", "wallpaper", f",{path}"]),
    ]
    errors: list[str] = []
    for name, command in attempts:
        if shutil.which(command[0]) is None:
            continue
        ok, output = _run(command)
        if ok:
            return name
        errors.append(f"{name}: {output or 'failed'}")
    if errors:
        raise RuntimeError("; ".join(errors))
    raise RuntimeError("no supported wallpaper backend found (quickshell, swww, hyprpaper)")
