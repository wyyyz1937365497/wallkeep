from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from . import db


def config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "illogical-impulse" / "config.json"


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".wallkeep.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def current() -> dict[str, Any]:
    data = _load(config_path())
    appearance = data.get("appearance") if isinstance(data.get("appearance"), dict) else {}
    palette = appearance.get("palette") if isinstance(appearance.get("palette"), dict) else {}
    background = data.get("background") if isinstance(data.get("background"), dict) else {}
    parallax = background.get("parallax") if isinstance(background.get("parallax"), dict) else {}
    try:
        zoom = float(parallax.get("workspaceZoom", 1.07) or 1.07)
    except (TypeError, ValueError):
        zoom = 1.07
    return {
        "palette_type": str(palette.get("type") or "auto"),
        "workspace": bool(parallax.get("enableWorkspace", False)),
        "zoom": zoom,
        "vertical": bool(parallax.get("vertical", False)),
        "sidebar": bool(parallax.get("enableSidebar", False)),
    }


def apply_effects(
    *,
    monochrome: bool,
    parallax: bool,
    zoom: float,
    vertical: bool,
    sidebar: bool,
) -> bool:
    """Write shell appearance/parallax settings. Returns True if palette changed."""
    path = config_path()
    data = _load(path)
    appearance = data.setdefault("appearance", {})
    if not isinstance(appearance, dict):
        appearance = data["appearance"] = {}
    palette = appearance.setdefault("palette", {})
    if not isinstance(palette, dict):
        palette = appearance["palette"] = {}
    background = data.setdefault("background", {})
    if not isinstance(background, dict):
        background = data["background"] = {}
    parallax_data = background.setdefault("parallax", {})
    if not isinstance(parallax_data, dict):
        parallax_data = background["parallax"] = {}

    current_type = str(palette.get("type") or "auto")
    palette_changed = False
    if monochrome:
        if current_type != "scheme-monochrome":
            db.set_setting("shell_palette_before_mono", current_type or "auto")
            palette["type"] = "scheme-monochrome"
            palette_changed = True
    elif current_type == "scheme-monochrome":
        palette["type"] = db.get_setting("shell_palette_before_mono", "auto") or "auto"
        palette_changed = True

    parallax_data["enableWorkspace"] = bool(parallax)
    parallax_data["workspaceZoom"] = round(float(zoom), 2)
    parallax_data["vertical"] = bool(vertical)
    parallax_data["enableSidebar"] = bool(sidebar)
    _save(path, data)
    return palette_changed
