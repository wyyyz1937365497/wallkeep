from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

UNIT_NAME = "wallkeep-rotate.service"
UNIT_PATH = Path.home() / ".config" / "systemd" / "user" / UNIT_NAME


def _executable() -> str:
    path = sys.executable
    return f'"{path}"' if " " in path else path


def _unit_text() -> str:
    return (
        "[Unit]\n"
        "Description=Wallkeep wallpaper rotation\n"
        "After=graphical-session.target\n"
        "PartOf=graphical-session.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={_executable()} -m wallkeep.rotate --daemon\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def _run(*arguments: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["systemctl", "--user", *arguments],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


def sync(enabled: bool) -> tuple[bool, str]:
    if shutil.which("systemctl") is None:
        return False, "systemctl not found"
    UNIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    UNIT_PATH.write_text(_unit_text(), encoding="utf-8")
    ok, output = _run("daemon-reload")
    if not ok:
        return False, output
    if enabled:
        ok, output = _run("enable", "--now", UNIT_NAME)
        return ok, output
    active = _run("is-active", UNIT_NAME)[0]
    installed = _run("is-enabled", UNIT_NAME)[0]
    if not active and not installed:
        return True, ""
    ok, output = _run("disable", "--now", UNIT_NAME)
    return ok, output
