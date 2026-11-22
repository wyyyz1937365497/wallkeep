from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStyle

SYSTEM_QT_PLUGINS = "/usr/lib/qt6/plugins"

BROWSERS = [
    ("Firefox", "firefox"),
    ("Chrome", "chrome"),
    ("Chromium", "chromium"),
    ("Brave", "brave"),
    ("Edge", "edge"),
]

KEYRINGS = [
    ("GNOME keyring (libsecret)", "gnomekeyring"),
    ("KWallet", "kwallet"),
    ("Basic", "basictext"),
    ("Auto", "auto"),
]


def install_qt_plugin_path() -> None:
    """Expose the system Qt plugins (KDE platform theme, Breeze, Darkly)."""
    if not os.path.isdir(SYSTEM_QT_PLUGINS):
        return
    current = [part for part in os.environ.get("QT_PLUGIN_PATH", "").split(":") if part]
    if SYSTEM_QT_PLUGINS not in current:
        current.append(SYSTEM_QT_PLUGINS)
    os.environ["QT_PLUGIN_PATH"] = ":".join(current)


def theme_icon(*names: str) -> QIcon:
    for name in names:
        icon = QIcon.fromTheme(name)
        if not icon.isNull():
            return icon
    app = QApplication.instance()
    if app is not None:
        return app.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
    return QIcon()


def configure_application(app: QApplication) -> None:
    app.setApplicationName("Wallkeep")
    app.setApplicationDisplayName("Wallkeep")
    app.setOrganizationName("Wallkeep")
    app.setDesktopFileName("wallkeep")
    app.setWindowIcon(theme_icon("image-x-generic"))
    # Follow the desktop's Qt style/palette/font. No stylesheet: the KDE
    # platform theme (Darkly/Breeze) is what keeps this app native-looking.
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
