from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from .. import i18n, library


def human_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


class DuplicatesDialog(QDialog):
    def __init__(self, groups: list[list[dict[str, Any]]], db_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("Duplicate images"))
        self.resize(1180, 820)
        self._db_path = db_path
        self._groups = [sorted(group, key=lambda row: row.get("bytes") or 0, reverse=True) for group in groups]
        self._entries: list[tuple[int, QTreeWidgetItem, dict[str, Any]]] = []
        self._icons: dict[str, QIcon] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(10)

        hint = QLabel(
            i18n.tr(
                "Images are grouped by 64-bit pHash similarity. Unchecked images are kept; "
                "the largest file of each group is kept by default."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(
            [
                i18n.tr("Image"),
                i18n.tr("Dimensions"),
                i18n.tr("Size"),
                i18n.tr("Source"),
                i18n.tr("Delete"),
            ]
        )
        self.tree.setIconSize(QSize(96, 72))
        self.tree.setUniformRowHeights(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setColumnWidth(4, 70)
        layout.addWidget(self.tree, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        auto_button = QPushButton(i18n.tr("Keep largest, check the rest"))
        auto_button.clicked.connect(self._auto_check)
        delete_button = QPushButton(i18n.tr("Delete checked…"))
        delete_button.setDefault(True)
        delete_button.clicked.connect(self._delete_checked)
        cancel_button = QPushButton(i18n.tr("Cancel"))
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(auto_button)
        buttons.addWidget(delete_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)

        self._populate()
        self._auto_check()

    def _icon(self, asset: dict[str, Any]) -> QIcon:
        sha = asset["sha256"]
        cached = self._icons.get(sha)
        if cached is not None:
            return cached
        thumb = library.thumb_path(sha)
        pixmap = QPixmap(str(thumb)) if thumb.exists() else QPixmap()
        if pixmap.isNull():
            icon = QIcon.fromTheme("image-x-generic")
        else:
            icon = QIcon(
                pixmap.scaled(
                    QSize(96, 72),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self._icons[sha] = icon
        return icon

    def _populate(self) -> None:
        for group_index, group in enumerate(self._groups):
            total = sum(int(row.get("bytes") or 0) for row in group)
            group_item = QTreeWidgetItem(
                [
                    i18n.trf(
                        "Group {index} · {count} images · {size}",
                        index=group_index + 1,
                        count=len(group),
                        size=human_size(total),
                    )
                ]
            )
            group_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            font = group_item.font(0)
            font.setBold(True)
            group_item.setFont(0, font)
            group_item.setFirstColumnSpanned(True)
            self.tree.addTopLevelItem(group_item)

            for asset in group:
                item = QTreeWidgetItem(group_item)
                item.setIcon(0, self._icon(asset))
                item.setText(0, Path(asset["path"]).name)
                item.setToolTip(0, asset["path"])
                item.setText(1, f"{asset['width']}×{asset['height']}")
                item.setText(2, human_size(int(asset.get("bytes") or 0)))
                source = (
                    f"@{asset['source_user']}"
                    if asset.get("source_user")
                    else i18n.tr("Local")
                )
                item.setText(3, source)
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(4, Qt.CheckState.Unchecked)
                item.setData(0, Qt.ItemDataRole.UserRole, asset)
                self._entries.append((group_index, item, asset))
            group_item.setExpanded(True)

    def _auto_check(self) -> None:
        for group_index, group in enumerate(self._groups):
            largest_id = max(group, key=lambda row: row.get("bytes") or 0)["id"]
            for entry_group, item, asset in self._entries:
                if entry_group != group_index:
                    continue
                state = (
                    Qt.CheckState.Unchecked
                    if asset["id"] == largest_id
                    else Qt.CheckState.Checked
                )
                item.setCheckState(4, state)

    def _checked_assets(self) -> list[dict[str, Any]]:
        return [
            asset
            for _group, item, asset in self._entries
            if item.checkState(4) == Qt.CheckState.Checked
        ]

    def _delete_checked(self) -> None:
        checked = {asset["id"] for asset in self._checked_assets()}
        if not checked:
            return

        keep_by_id: dict[int, int] = {}
        total_bytes = 0
        for group_index, group in enumerate(self._groups):
            entries = [(item, asset) for gi, item, asset in self._entries if gi == group_index]
            checked_group = [(item, asset) for item, asset in entries if item.checkState(4) == Qt.CheckState.Checked]
            if not checked_group:
                continue
            kept_group = [
                (item, asset)
                for item, asset in entries
                if item.checkState(4) != Qt.CheckState.Checked
            ]
            if not kept_group:
                QMessageBox.warning(
                    self,
                    i18n.tr("Duplicate images"),
                    i18n.tr("Keep at least one image in every group."),
                )
                return
            keep = max(kept_group, key=lambda pair: pair[1].get("bytes") or 0)[1]
            for _item, asset in checked_group:
                keep_by_id[asset["id"]] = keep["id"]
                total_bytes += int(asset.get("bytes") or 0)

        answer = QMessageBox.question(
            self,
            i18n.tr("Delete duplicate images?"),
            i18n.trf(
                "Delete {count} images ({size})? Files are moved to the trash; "
                "unchecked images are kept.",
                count=len(keep_by_id),
                size=human_size(total_bytes),
            ),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = library.delete_assets(self._db_path, checked, keep_by_id)
        finally:
            QApplication.restoreOverrideCursor()

        if result["deleted"]:
            message = i18n.trf(
                "Deleted {count} images, freed {size}.",
                count=result["deleted"],
                size=human_size(result["freed"]),
            )
            if result["permanent"]:
                message += "\n" + i18n.trf(
                    "{count} files were permanently deleted because the trash was unavailable.",
                    count=result["permanent"],
                )
            if result["errors"]:
                message += "\n\n" + i18n.tr("Some files could not be deleted:")
                message += "\n" + "\n".join(html.escape(error) for error in result["errors"][:5])
            QMessageBox.information(self, i18n.tr("Duplicate images"), message)
            self.accept()
        else:
            QMessageBox.warning(
                self,
                i18n.tr("Some files could not be deleted"),
                "\n".join(result["errors"][:8]) or i18n.tr("No files were deleted."),
            )
