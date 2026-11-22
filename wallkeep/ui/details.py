from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import i18n
from .theme import theme_icon

PREVIEW_SIZE = QSize(360, 250)


def human_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


class DetailsPanel(QWidget):
    set_wallpaper_requested = Signal(str)
    open_requested = Signal(str)
    folder_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._asset: dict | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.title = QLabel("No wallpaper selected")
        title_font = self.title.font()
        title_font.setBold(True)
        title_font.setPointSizeF(title_font.pointSizeF() + 0.5)
        self.title.setFont(title_font)
        self.title.setWordWrap(True)
        layout.addWidget(self.title)

        self.preview = QLabel("Select a wallpaper to preview it")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFrameShape(QFrame.Shape.StyledPanel)
        self.preview.setMinimumSize(PREVIEW_SIZE)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.preview)

        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.form.setHorizontalSpacing(14)
        self.form.setVerticalSpacing(7)

        self.dimensions = self._value_label()
        self.file_size = self._value_label()
        self.source = self._value_label()
        self.added = self._value_label()
        self.hash = self._value_label()
        self.form.addRow("Dimensions", self.dimensions)
        self.form.addRow("Size", self.file_size)
        self.form.addRow("Source", self.source)
        self.form.addRow("Added", self.added)
        self.form.addRow("SHA-256", self.hash)
        layout.addLayout(self.form)

        self.link = QLabel()
        self.link.setOpenExternalLinks(True)
        self.link.setTextFormat(Qt.TextFormat.RichText)
        self.link.setWordWrap(True)
        self.link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        layout.addWidget(self.link)

        layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.wallpaper_button = QPushButton("Set as wallpaper")
        self.wallpaper_button.setIcon(
            theme_icon("preferences-desktop-wallpaper", "video-display")
        )
        self.open_button = QPushButton("Open")
        self.open_button.setIcon(theme_icon("document-open"))
        self.folder_button = QPushButton("Show in folder")
        self.folder_button.setIcon(theme_icon("folder-open"))
        buttons.addWidget(self.wallpaper_button, 2)
        buttons.addWidget(self.open_button, 1)
        buttons.addWidget(self.folder_button, 1)
        layout.addLayout(buttons)

        self.wallpaper_button.clicked.connect(self._emit_wallpaper)
        self.open_button.clicked.connect(self._emit_open)
        self.folder_button.clicked.connect(self._emit_folder)
        self.clear()
        i18n.translate_widget_tree(self)

    @staticmethod
    def _value_label() -> QLabel:
        label = QLabel("—")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setWordWrap(True)
        return label

    def clear(self) -> None:
        self._asset = None
        self.title.setText(i18n.tr("No wallpaper selected"))
        self.preview.clear()
        self.preview.setText(i18n.tr("Select a wallpaper to preview it"))
        for label in (self.dimensions, self.file_size, self.source, self.added, self.hash):
            label.setText("—")
        self.hash.setToolTip("")
        self.link.clear()
        self.link.hide()
        for button in (self.wallpaper_button, self.open_button, self.folder_button):
            button.setEnabled(False)

    def show_asset(self, asset: dict | None) -> None:
        if not asset:
            self.clear()
            return
        self._asset = asset
        path = Path(asset["path"])
        self.title.setText(path.name)
        self.title.setToolTip(str(path))

        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid():
            reader.setScaledSize(
                size.scaled(PREVIEW_SIZE, Qt.AspectRatioMode.KeepAspectRatio)
            )
        image = reader.read()
        if image.isNull():
            self.preview.clear()
            self.preview.setText(i18n.tr("Preview unavailable"))
        else:
            self.preview.setPixmap(QPixmap.fromImage(image))

        self.dimensions.setText(f"{asset['width']} × {asset['height']}")
        self.file_size.setText(human_size(int(asset["bytes"])))
        source = f"@{asset['source_user']}" if asset.get("source_user") else i18n.tr("Local file")
        self.source.setText(source)
        timestamp = asset.get("source_posted_at") or asset.get("created_at")
        self.added.setText(
            datetime.fromtimestamp(int(timestamp)).strftime("%Y-%m-%d %H:%M")
            if timestamp
            else "—"
        )
        sha = asset["sha256"]
        self.hash.setText(sha[:16] + "…")
        self.hash.setToolTip(sha)

        url = asset.get("source_url") or ""
        if url:
            escaped = html.escape(url, quote=True)
            self.link.setText(
                f'<a href="{escaped}">{html.escape(i18n.tr("Open original post"))}</a>'
            )
            self.link.show()
        else:
            self.link.hide()
        for button in (self.wallpaper_button, self.open_button, self.folder_button):
            button.setEnabled(True)

    def _emit_wallpaper(self) -> None:
        if self._asset:
            self.set_wallpaper_requested.emit(self._asset["path"])

    def _emit_open(self) -> None:
        if self._asset:
            self.open_requested.emit(self._asset["path"])

    def _emit_folder(self) -> None:
        if self._asset:
            self.folder_requested.emit(self._asset["path"])
