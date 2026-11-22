from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .. import db, i18n, paths
from ..xsync import normalize_user
from .theme import BROWSERS, KEYRINGS


def _browser_combo(current: str) -> QComboBox:
    combo = QComboBox()
    for label, value in BROWSERS:
        combo.addItem(label, value)
    index = combo.findData(current)
    combo.setCurrentIndex(index if index >= 0 else 0)
    return combo


def _keyring_combo(current: str) -> QComboBox:
    combo = QComboBox()
    for label, value in KEYRINGS:
        combo.addItem(label, value)
    index = combo.findData(current)
    combo.setCurrentIndex(index if index >= 0 else 0)
    return combo


class AddUserDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add X user")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        intro = QLabel(
            "The media tab of this profile is downloaded with your browser login. "
            "Make sure x.com is logged in in the selected browser."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)
        self.username = QLineEdit()
        self.username.setPlaceholderText("username without @")
        self.username.setClearButtonEnabled(True)
        self.browser = _browser_combo(db.get_setting("cookies_browser", "firefox"))
        self.keyring = _keyring_combo(db.get_setting("cookies_keyring", "gnomekeyring"))
        self.proxy = QLineEdit(db.get_setting("proxy", ""))
        self.proxy.setPlaceholderText("http://127.0.0.1:7890 (optional)")
        form.addRow("X username", self.username)
        form.addRow("Cookie source", self.browser)
        form.addRow("Cookie keyring", self.keyring)
        form.addRow("Proxy", self.proxy)
        layout.addLayout(form)

        note = QLabel(
            "Cookies are read from the selected browser on every sync. "
            "No password or cookie value is stored by Wallkeep."
        )
        note.setWordWrap(True)
        note.setForegroundRole(self.foregroundRole())
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        i18n.translate_widget_tree(self)

    def _accept(self) -> None:
        username = normalize_user(self.username.text())
        if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", username):
            QMessageBox.warning(
                self,
                i18n.tr("Invalid username"),
                i18n.tr("Enter an X username (1–15 letters, digits or _)."),
            )
            return
        self.username.setText(username)
        self.accept()

    def values(self) -> dict[str, str]:
        return {
            "user": normalize_user(self.username.text()),
            "browser": self.browser.currentData(),
            "keyring": self.keyring.currentData(),
            "proxy": self.proxy.text().strip(),
        }


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wallkeep settings")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)

        library_row = QHBoxLayout()
        self.library = QLineEdit(db.get_setting("library_dir", str(paths.DEFAULT_LIBRARY_DIR)))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        library_row.addWidget(self.library, 1)
        library_row.addWidget(browse)
        form.addRow("X download folder", library_row)

        self.browser = _browser_combo(db.get_setting("cookies_browser", "firefox"))
        self.keyring = _keyring_combo(db.get_setting("cookies_keyring", "gnomekeyring"))
        self.proxy = QLineEdit(db.get_setting("proxy", ""))
        self.proxy.setPlaceholderText("http://127.0.0.1:7890 (optional)")
        form.addRow("Cookie source", self.browser)
        form.addRow("Cookie keyring", self.keyring)
        form.addRow("Proxy", self.proxy)

        self.similar = QSpinBox()
        self.similar.setRange(0, 20)
        self.similar.setValue(int(db.get_setting("similar_threshold", "8") or 8))
        self.similar.setToolTip(
            "pHash Hamming distance, 0 disables. Lower = stricter."
        )
        form.addRow("Similarity threshold", self.similar)

        self.language = QComboBox()
        for label, value in (("System", "auto"), ("English", "en"), ("简体中文", "zh_CN")):
            self.language.addItem(label, value)
        index = self.language.findData(db.get_setting("language", "auto"))
        self.language.setCurrentIndex(index if index >= 0 else 0)
        form.addRow("Language", self.language)

        data = QLabel(str(paths.DATA_DIR))
        data.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        data.setWordWrap(True)
        form.addRow("Database and archives", data)

        layout.addLayout(form)

        hint = QLabel(
            "Local folders are indexed in place. X media is moved into the download folder above."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        similarity_hint = QLabel(
            "pHash Hamming distance, 0 disables. Lower = stricter."
        )
        similarity_hint.setWordWrap(True)
        layout.addWidget(similarity_hint)
        language_hint = QLabel("Language changes take effect after restart.")
        language_hint.setWordWrap(True)
        layout.addWidget(language_hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        i18n.translate_widget_tree(self)

    def _browse(self) -> None:
        start = self.library.text() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, i18n.tr("X download folder"), start)
        if chosen:
            self.library.setText(chosen)

    def _accept(self) -> None:
        library = Path(self.library.text()).expanduser()
        if not library:
            QMessageBox.warning(
                self, i18n.tr("Invalid folder"), i18n.tr("Choose a download folder.")
            )
            return
        try:
            library.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            QMessageBox.warning(self, i18n.tr("Cannot create folder"), str(error))
            return
        self.accept()

    def values(self) -> dict[str, str]:
        return {
            "library_dir": str(Path(self.library.text()).expanduser()),
            "browser": self.browser.currentData(),
            "keyring": self.keyring.currentData(),
            "proxy": self.proxy.text().strip(),
            "similar_threshold": str(self.similar.value()),
            "language": self.language.currentData(),
        }
