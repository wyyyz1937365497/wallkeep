from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class AssetModel(QAbstractListModel):
    AssetRole = Qt.ItemDataRole.UserRole + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def row_at(self, index: QModelIndex) -> dict | None:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        return self._rows[index.row()]

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        row = self.row_at(index)
        if row is None:
            return None
        if role == self.AssetRole:
            return row
        if role == Qt.ItemDataRole.DisplayRole:
            return Path(row["path"]).name
        if role == Qt.ItemDataRole.ToolTipRole:
            source = f"@{row['source_user']}" if row.get("source_user") else "Local"
            return f"{Path(row['path']).name}\n{row['width']} × {row['height']}  {source}"
        return None
