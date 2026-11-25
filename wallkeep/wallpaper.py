from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

from . import paths

VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".avi", ".mov"}
ANIMATED_EXTS = {".gif"}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _desktop_env() -> dict[str, str]:
    env = os.environ.copy()
    runtime = Path(env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
    if not env.get("WAYLAND_DISPLAY") and runtime.is_dir():
        for socket in sorted(runtime.glob("wayland-*")):
            if socket.is_socket():
                env["WAYLAND_DISPLAY"] = socket.name
                break
    if not env.get("HYPRLAND_INSTANCE_SIGNATURE") and (runtime / "hypr").is_dir():
        for directory in sorted((runtime / "hypr").iterdir()):
            if directory.is_dir() and (directory / ".socket.sock").exists():
                env["HYPRLAND_INSTANCE_SIGNATURE"] = directory.name
                break
    return env


def _run(command: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=30, env=_desktop_env()
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


def monitor_size() -> tuple[int, int]:
    try:
        result = subprocess.run(
            ["hyprctl", "monitors", "-j"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=_desktop_env(),
        )
        monitors = json.loads(result.stdout)
        sizes = [(int(m["width"]), int(m["height"])) for m in monitors if m.get("width")]
        if sizes:
            return max(sizes, key=lambda size: size[0] * size[1])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return 1920, 1080


def composite_path(source: Path, sha256: str, size: tuple[int, int]) -> Path:
    return paths.CACHE_DIR / "wallpapers" / f"{sha256[:16]}_{size[0]}x{size[1]}.jpg"


def render_fit_blur(source: Path, sha256: str, size: tuple[int, int]) -> Path:
    destination = composite_path(source, sha256, size)
    if destination.exists():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
        foreground = ImageOps.contain(image, size, Image.Resampling.LANCZOS)
        if foreground.size == size:
            canvas = foreground
        else:
            small = (max(1, size[0] // 4), max(1, size[1] // 4))
            canvas = ImageOps.fit(image, small, Image.Resampling.LANCZOS)
            canvas = canvas.filter(ImageFilter.GaussianBlur(8)).resize(
                size, Image.Resampling.BILINEAR
            )
            canvas.paste(
                foreground,
                ((size[0] - foreground.width) // 2, (size[1] - foreground.height) // 2),
            )
    temporary = destination.with_name(destination.stem + ".tmp.jpg")
    canvas.save(temporary, "JPEG", quality=94, optimize=True)
    temporary.replace(destination)
    return destination


def set_wallpaper(
    path: Path, fill_mode: str = "cover", sha256: str | None = None
) -> str:
    """Apply a wallpaper through the running desktop stack.

    Images in ``fit_blur`` mode are rendered as an aspect-fit foreground over a
    blurred, enlarged copy of the same image. Videos/GIFs are passed through so
    the shell can keep them animated.
    """
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    apply_path = path
    suffix = path.suffix.lower()
    if (
        fill_mode == "fit_blur"
        and suffix not in VIDEO_EXTS
        and suffix not in ANIMATED_EXTS
    ):
        digest = sha256 or _sha256_file(path)
        try:
            apply_path = render_fit_blur(path, digest, monitor_size())
        except Exception:
            apply_path = path

    attempts: list[tuple[str, list[str]]] = [
        (
            "quickshell",
            ["qs", "-c", "ii", "ipc", "call", "wallpapers", "apply", str(apply_path)],
        ),
        ("swww", ["swww", "img", str(apply_path)]),
        ("hyprpaper", ["hyprctl", "hyprpaper", "wallpaper", f",{apply_path}"]),
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
