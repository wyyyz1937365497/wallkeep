from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap

from .. import i18n, library

ICON_SIZE = QSize(208, 150)
ICON_CACHE_LIMIT = 300


class AssetModel(QAbstractListModel):
    AssetRole = Qt.ItemDataRole.UserRole + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []
        self._icons: dict[str, QIcon] = {}
        self._icon_order: list[str] = []

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self._rows = rows
        self._icons.clear()
        self._icon_order.clear()
        self.endResetModel()

    def row_at(self, index: QModelIndex) -> dict | None:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        return self._rows[index.row()]

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def _icon(self, row: dict) -> QIcon:
        sha = row["sha256"]
        cached = self._icons.get(sha)
        if cached is not None:
            return cached
        thumb = library.thumb_path(sha)
        pixmap = QPixmap(str(thumb)) if thumb.exists() else QPixmap()
        if pixmap.isNull():
            icon = QIcon.fromTheme("image-x-generic")
        else:
            pixmap = pixmap.scaled(
                ICON_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            icon = QIcon(pixmap)
        self._icons[sha] = icon
        self._icon_order.append(sha)
        while len(self._icon_order) > ICON_CACHE_LIMIT:
            old = self._icon_order.pop(0)
            self._icons.pop(old, None)
        return icon

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        row = self.row_at(index)
        if row is None:
            return None
        source = f"@{row['source_user']}" if row.get("source_user") else i18n.tr("Local")
        if role == self.AssetRole:
            return row
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{row['width']}×{row['height']}  ·  {source}"
        if role == Qt.ItemDataRole.DecorationRole:
            return self._icon(row)
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{Path(row['path']).name}\n{row['width']} × {row['height']}  {source}"
        return None
