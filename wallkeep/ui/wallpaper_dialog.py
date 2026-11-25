from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .. import db, i18n, library, rotate, rotation_service, shell, wallpaper


class WallpaperDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wallpaper rotation and shell")
        self.setMinimumWidth(540)
        self._current_id = int(db.get_setting("wallpaper_current_id", "0") or 0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        preview_row = QHBoxLayout()
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedSize(220, 140)
        self.preview.setFrameShape(QFrame.Shape.StyledPanel)
        preview_row.addWidget(self.preview)
        preview_box = QVBoxLayout()
        self.current_label = QLabel()
        self.current_label.setWordWrap(True)
        preview_box.addWidget(self.current_label)
        self.current_hint = QLabel(
            "The current wallpaper is stored by Wallkeep; files are never modified."
        )
        self.current_hint.setWordWrap(True)
        preview_box.addWidget(self.current_hint)
        preview_box.addStretch(1)
        preview_row.addLayout(preview_box, 1)
        layout.addLayout(preview_row)

        rotation_box = QGroupBox("Rotation")
        rotation_form = QFormLayout(rotation_box)
        rotation_form.setHorizontalSpacing(14)
        rotation_form.setVerticalSpacing(8)
        self.rotation_enabled = QCheckBox("Rotate the wallpaper automatically")
        self.rotation_enabled.setChecked(db.get_setting("rotation_enabled", "0") == "1")
        rotation_form.addRow(self.rotation_enabled)
        self.interval = QSpinBox()
        self.interval.setRange(1, 1440)
        self.interval.setSuffix(" min")
        self.interval.setValue(
            max(1, int(db.get_setting("rotation_interval_minutes", "30") or 30))
        )
        rotation_form.addRow("Interval", self.interval)
        self.mode = QComboBox()
        self.mode.addItem("Shuffle", "shuffle")
        self.mode.addItem("Sequential", "sequential")
        mode_index = self.mode.findData(db.get_setting("rotation_mode", "shuffle"))
        self.mode.setCurrentIndex(mode_index if mode_index >= 0 else 0)
        rotation_form.addRow("Order", self.mode)
        self.scope = QComboBox()
        self.scope.addItem("All wallpapers", "all")
        self.scope.addItem("Favorites", "favorites")
        self.scope.addItem("Local files", "local")
        scope_index = self.scope.findData(db.get_setting("rotation_scope", "all"))
        self.scope.setCurrentIndex(scope_index if scope_index >= 0 else 0)
        rotation_form.addRow("Pool", self.scope)
        self.include_videos = QCheckBox("Include videos")
        self.include_videos.setChecked(
            db.get_setting("rotation_include_videos", "1") == "1"
        )
        self.include_videos.setToolTip(
            "Videos need mpvpaper and the end-4 quickshell wallpaper service."
        )
        rotation_form.addRow(self.include_videos)
        self.fill_mode = QComboBox()
        self.fill_mode.addItem("Cover (crop)", "cover")
        self.fill_mode.addItem("Fit with blurred background", "fit_blur")
        fill_index = self.fill_mode.findData(db.get_setting("wallpaper_fill_mode", "cover"))
        self.fill_mode.setCurrentIndex(fill_index if fill_index >= 0 else 0)
        rotation_form.addRow("Image fit", self.fill_mode)
        layout.addWidget(rotation_box)

        effects = shell.current()
        effects_box = QGroupBox("Shell effects")
        effects_form = QFormLayout(effects_box)
        effects_form.setHorizontalSpacing(14)
        effects_form.setVerticalSpacing(8)
        self.monochrome = QCheckBox("Monochrome theme")
        self.monochrome.setChecked(effects["palette_type"] == "scheme-monochrome")
        effects_form.addRow(self.monochrome)
        self.parallax = QCheckBox("Workspace parallax")
        self.parallax.setChecked(effects["workspace"])
        effects_form.addRow(self.parallax)
        self.zoom = QDoubleSpinBox()
        self.zoom.setRange(1.0, 2.0)
        self.zoom.setSingleStep(0.01)
        self.zoom.setDecimals(2)
        self.zoom.setValue(effects["zoom"])
        effects_form.addRow("Parallax zoom", self.zoom)
        self.vertical = QCheckBox("Vertical parallax")
        self.vertical.setChecked(effects["vertical"])
        effects_form.addRow(self.vertical)
        self.sidebar = QCheckBox("Sidebar parallax")
        self.sidebar.setChecked(effects["sidebar"])
        effects_form.addRow(self.sidebar)
        layout.addWidget(effects_box)

        buttons_row = QHBoxLayout()
        self.next_button = QPushButton("Next wallpaper now")
        self.next_button.clicked.connect(self._next_now)
        buttons_row.addWidget(self.next_button)
        buttons_row.addStretch(1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        buttons_row.addWidget(buttons)
        layout.addLayout(buttons_row)
        i18n.translate_widget_tree(self)
        self._refresh_current()

    def _refresh_current(self) -> None:
        self._current_id = int(db.get_setting("wallpaper_current_id", "0") or 0)
        asset = db.fetch_asset(self._current_id) if self._current_id else None
        if asset is None:
            path = db.get_setting("wallpaper_current_path", "")
            if path:
                self.current_label.setText(i18n.trf("Current wallpaper: {path}", path=path))
            else:
                self.current_label.setText(i18n.tr("No wallpaper selected yet."))
            self.preview.clear()
            self.preview.setText(i18n.tr("No preview"))
            return
        self.current_label.setText(
            i18n.trf("Current wallpaper: {name}", name=Path(asset["path"]).name)
        )
        thumb = library.thumb_path(str(asset["sha256"]))
        pixmap = QPixmap(str(thumb)) if thumb.exists() else QPixmap(str(asset["path"]))
        if pixmap.isNull():
            self.preview.clear()
            self.preview.setText(i18n.tr("Preview unavailable"))
        else:
            self.preview.setPixmap(
                pixmap.scaled(
                    self.preview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def _write_settings(self) -> bool:
        previous_fill = db.get_setting("wallpaper_fill_mode", "cover")
        db.set_setting("rotation_enabled", "1" if self.rotation_enabled.isChecked() else "0")
        db.set_setting("rotation_interval_minutes", str(self.interval.value()))
        db.set_setting("rotation_mode", str(self.mode.currentData()))
        db.set_setting("rotation_scope", str(self.scope.currentData()))
        db.set_setting(
            "rotation_include_videos", "1" if self.include_videos.isChecked() else "0"
        )
        db.set_setting("wallpaper_fill_mode", str(self.fill_mode.currentData()))
        db.set_setting(
            "shell_theme_monochrome", "1" if self.monochrome.isChecked() else "0"
        )
        db.set_setting(
            "shell_parallax_workspace", "1" if self.parallax.isChecked() else "0"
        )
        db.set_setting("shell_parallax_zoom", f"{self.zoom.value():.2f}")
        db.set_setting("shell_parallax_vertical", "1" if self.vertical.isChecked() else "0")
        db.set_setting("shell_parallax_sidebar", "1" if self.sidebar.isChecked() else "0")
        try:
            palette_changed = shell.apply_effects(
                monochrome=self.monochrome.isChecked(),
                parallax=self.parallax.isChecked(),
                zoom=self.zoom.value(),
                vertical=self.vertical.isChecked(),
                sidebar=self.sidebar.isChecked(),
            )
        except OSError as error:
            QMessageBox.warning(self, i18n.tr("Could not update shell"), str(error))
            return False
        if palette_changed or previous_fill != str(self.fill_mode.currentData()):
            self._reapply_current()
        return True

    def _reapply_current(self) -> None:
        if not self._current_id:
            return
        asset = db.fetch_asset(self._current_id)
        if asset is None:
            return
        try:
            wallpaper.set_wallpaper(
                Path(asset["path"]),
                str(self.fill_mode.currentData()),
                str(asset["sha256"]),
            )
        except Exception as error:  # noqa: BLE001 - shown to the user
            QMessageBox.warning(self, i18n.tr("Could not re-apply wallpaper"), str(error))

    def _next_now(self) -> None:
        if not self._write_settings():
            return
        try:
            result = rotate.next_wallpaper()
        except Exception as error:  # noqa: BLE001 - shown to the user
            QMessageBox.critical(self, i18n.tr("Could not set wallpaper"), str(error))
            return
        self._refresh_current()
        self.current_label.setText(
            i18n.trf(
                "Applied {name} via {method}",
                name=Path(result["asset"]["path"]).name,
                method=result["method"],
            )
        )

    def _save(self) -> None:
        if not self._write_settings():
            return
        enabled = self.rotation_enabled.isChecked()
        ok, output = rotation_service.sync(enabled)
        if not ok:
            QMessageBox.warning(
                self,
                i18n.tr("Could not update rotation service"),
                output or i18n.tr("systemctl failed"),
            )
        self.accept()
