from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

from . import paths, shell

VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".avi", ".mov"}
ANIMATED_EXTS = {".gif"}


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


def _fit_blur_size() -> tuple[int, int]:
    width, height = monitor_size()
    try:
        zoom = float(shell.current().get("zoom", 1.07))
    except (TypeError, ValueError):
        zoom = 1.07
    # The shell displays the composite at 1:1 after accounting for parallax
    # zoom. Matching that size avoids a second, possibly unsmoothed, QML scale.
    factor = max(1.0, zoom)
    return max(1, round(width * factor)), max(1, round(height * factor))

def render_fit_blur(source: Path, size: tuple[int, int]) -> Path:
    """Render a fit-with-blurred-background PNG on demand.

    The foreground keeps the source's pixels apart from the downscale needed
    to fit the target; the border is a blurred cover copy. PNG avoids JPEG
    recompression.
    """
    directory = paths.CACHE_DIR / "wallpapers"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"fit-blur-{time.time_ns()}.png"
    temporary = destination.with_name(destination.name + ".tmp")
    with Image.open(source) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
        foreground = ImageOps.contain(image, size, Image.Resampling.LANCZOS)
        if foreground.size == size:
            canvas = foreground
        else:
            small = (max(1, size[0] // 4), max(1, size[1] // 4))
            canvas = ImageOps.fit(image, small, Image.Resampling.LANCZOS)
            radius = max(8, int(min(size) / 160))
            canvas = canvas.filter(ImageFilter.GaussianBlur(radius)).resize(
                size, Image.Resampling.BILINEAR
            )
            canvas.paste(
                foreground,
                ((size[0] - foreground.width) // 2, (size[1] - foreground.height) // 2),
            )
    canvas.save(temporary, "PNG", compress_level=6)
    temporary.replace(destination)
    return destination


def _cleanup_composites(keep: Path | None = None) -> None:
    directory = paths.CACHE_DIR / "wallpapers"
    if not directory.is_dir():
        return
    for path in directory.iterdir():
        if not path.is_file() or (keep is not None and path == keep):
            continue
        if path.suffix.lower() in {".png", ".jpg"} or path.name.endswith(".tmp"):
            path.unlink(missing_ok=True)


def set_wallpaper(path: Path, fill_mode: str = "cover") -> str:
    """Apply a wallpaper through the running desktop stack.

    ``fit_blur`` is rendered at apply time as a PNG (no JPEG recompression);
    no wallpaper library is pre-generated. Switching away removes the old composite.
    """
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    apply_path = path
    generated: Path | None = None
    suffix = path.suffix.lower()
    if (
        fill_mode == "fit_blur"
        and suffix not in VIDEO_EXTS
        and suffix not in ANIMATED_EXTS
    ):
        try:
            generated = render_fit_blur(path, _fit_blur_size())
            apply_path = generated
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
            if name == "quickshell":
                _cleanup_composites(generated)
            return name
        errors.append(f"{name}: {output or 'failed'}")
    if generated is not None:
        generated.unlink(missing_ok=True)
    if errors:
        raise RuntimeError("; ".join(errors))
    raise RuntimeError("no supported wallpaper backend found (quickshell, swww, hyprpaper)")
