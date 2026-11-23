from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import (
    QItemSelectionModel,
    QProcess,
    QProcessEnvironment,
    QSettings,
    QSize,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QAction, QBrush, QDesktopServices, QFontDatabase, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import db, i18n, library, paths, wallpaper
from ..sync_cli import ERROR_MARKER, RESULT_MARKER, USER_MARKER
from .details import DetailsPanel
from .dialogs import AddUserDialog, SettingsDialog
from .duplicates import DuplicatesDialog
from .model import AssetModel
from .workers import DuplicateWorker, ImportWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wallkeep")
        self.resize(1400, 880)
        self.settings = QSettings("Wallkeep", "Wallkeep")
        self.model = AssetModel(self)
        self._worker: ImportWorker | DuplicateWorker | None = None
        self._sync_process: QProcess | None = None
        self._sync_buffer = ""
        self._sync_errors: list[str] = []
        self._sync_cancel_requested = False
        self._busy = False
        self._pending_duplicates: list[list[dict]] | None = None
        self._current_filter: tuple[str, str | None] = ("all", None)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._reload_assets)

        # While the sync helper runs, poll SQLite and insert new rows in
        # batches. No Qt objects are touched from the sync worker process.
        self._live_timer = QTimer(self)
        self._live_timer.setSingleShot(False)
        self._live_timer.setInterval(1500)
        self._live_timer.timeout.connect(self._apply_live_import)

        self._build_actions()
        self._build_ui()
        self._restore_state()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _icon(self, *names: str) -> QIcon:
        for name in names:
            icon = QIcon.fromTheme(name)
            if not icon.isNull():
                return icon
        return self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)

    def _build_actions(self) -> None:
        self.import_action = QAction(self._icon("folder-open"), "Import folder…", self)
        self.import_action.setShortcut(QKeySequence("Ctrl+O"))
        self.import_action.setStatusTip("Index a folder of existing wallpapers")
        self.import_action.triggered.connect(self._choose_import)

        self.add_user_action = QAction(self._icon("list-add-user", "user-group-new", "list-add"), "Add X user…", self)
        self.add_user_action.setShortcut(QKeySequence("Ctrl+N"))
        self.add_user_action.setStatusTip("Download the media timeline of an X profile")
        self.add_user_action.triggered.connect(self._add_user)

        self.sync_action = QAction(self._icon("view-refresh"), "Sync", self)
        self.sync_action.setShortcut(QKeySequence("F5"))
        self.sync_action.setStatusTip("Sync the selected X user, or all X users")
        self.sync_action.triggered.connect(self._start_sync)

        self.stop_action = QAction(self._icon("process-stop"), "Stop", self)
        self.stop_action.setEnabled(False)
        self.stop_action.triggered.connect(self._stop)

        self.duplicates_action = QAction(
            self._icon("edit-find", "document-duplicate"), "Find duplicates…", self
        )
        self.duplicates_action.setStatusTip(
            "Scan all images by pHash and review near-duplicates"
        )
        self.duplicates_action.triggered.connect(self._find_duplicates)

        self.settings_action = QAction(self._icon("configure"), "Settings", self)
        self.settings_action.setShortcut(QKeySequence("Ctrl+,"))
        self.settings_action.triggered.connect(self._open_settings)

        self.reload_action = QAction(self._icon("view-refresh"), "Reload library", self)
        self.reload_action.setShortcut(QKeySequence("Ctrl+R"))
        self.reload_action.triggered.connect(self.refresh)

        self.quit_action = QAction(self._icon("application-exit"), "Quit", self)
        self.quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self.quit_action.triggered.connect(self.close)

        self.about_action = QAction("About Wallkeep", self)
        self.about_action.triggered.connect(self._about)

        self.focus_search = QShortcut(QKeySequence("Ctrl+F"), self)
        self.focus_search.activated.connect(self._focus_search)

    def _build_ui(self) -> None:
        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("mainToolBar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.addAction(self.import_action)
        toolbar.addAction(self.add_user_action)
        toolbar.addSeparator()
        toolbar.addAction(self.sync_action)
        toolbar.addAction(self.stop_action)
        toolbar.addAction(self.duplicates_action)
        toolbar.addSeparator()
        toolbar.addAction(self.settings_action)
        spacer = QWidget(toolbar)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        self.search = QLineEdit(toolbar)
        self.search.setPlaceholderText("Search wallpapers…")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(320)
        self.search.addAction(self._icon("edit-find"), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(lambda _text: self._search_timer.start())
        toolbar.addWidget(self.search)
        self.addToolBar(toolbar)

        menu = self.menuBar()
        file_menu = menu.addMenu("&File")
        file_menu.addAction(self.import_action)
        file_menu.addAction(self.add_user_action)
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        library_menu = menu.addMenu("&Library")
        library_menu.addAction(self.sync_action)
        library_menu.addAction(self.stop_action)
        library_menu.addAction(self.duplicates_action)
        library_menu.addAction(self.reload_action)
        library_menu.addSeparator()
        library_menu.addAction(self.settings_action)

        self.view_menu = menu.addMenu("&View")

        help_menu = menu.addMenu("&Help")
        help_menu.addAction(self.about_action)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(False)
        self.tree.setMinimumWidth(180)
        self.tree.setMaximumWidth(320)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection)

        self.list_view = QListView()
        self.list_view.setViewMode(QListView.ViewMode.IconMode)
        self.list_view.setFlow(QListView.Flow.LeftToRight)
        self.list_view.setWrapping(True)
        self.list_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.list_view.setMovement(QListView.Movement.Static)
        self.list_view.setUniformItemSizes(True)
        self.list_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list_view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_view.setSpacing(6)
        self.list_view.setMouseTracking(True)
        self.list_view.setFrameShape(QFrame.Shape.NoFrame)
        # Use Qt's native C++ item delegate. A Python-painted delegate
        # (QStyledItemDelegate.paint) triggers a shiboken refcount crash
        # in PySide6 6.12 while scrolling large grids.
        self.list_view.setIconSize(QSize(208, 150))
        self.list_view.setGridSize(QSize(226, 206))
        self.list_view.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.list_view.setWordWrap(False)
        self.list_view.setModel(self.model)
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._context_menu)
        self.list_view.doubleClicked.connect(lambda _index: self._open_current())
        self.list_view.selectionModel().selectionChanged.connect(self._on_selection_changed)

        self.empty_page = QWidget()
        empty_layout = QVBoxLayout(self.empty_page)
        empty_layout.setContentsMargins(40, 40, 40, 40)
        empty_layout.setSpacing(12)
        empty_layout.addStretch(1)
        self.empty_label = QLabel()
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        empty_font = self.empty_label.font()
        empty_font.setPointSizeF(empty_font.pointSizeF() + 1)
        self.empty_label.setFont(empty_font)
        empty_layout.addWidget(self.empty_label)
        empty_buttons = QHBoxLayout()
        empty_buttons.addStretch(1)
        import_button = QPushButton("Import folder…")
        import_button.setIcon(self.import_action.icon())
        import_button.clicked.connect(self.import_action.trigger)
        add_button = QPushButton("Add X user…")
        add_button.setIcon(self.add_user_action.icon())
        add_button.clicked.connect(self.add_user_action.trigger)
        empty_buttons.addWidget(import_button)
        empty_buttons.addWidget(add_button)
        empty_buttons.addStretch(1)
        empty_layout.addLayout(empty_buttons)
        empty_layout.addStretch(2)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.list_view)
        self.stack.addWidget(self.empty_page)
        self.stack.setCurrentWidget(self.list_view)

        self.details = DetailsPanel()
        self.details.setMinimumWidth(320)
        self.details.setMaximumWidth(440)
        self.details.set_wallpaper_requested.connect(self._set_wallpaper)
        self.details.open_requested.connect(self._open_path)
        self.details.folder_requested.connect(self._reveal_path)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(self.stack)
        self.splitter.addWidget(self.details)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([230, 800, 360])
        self.setCentralWidget(self.splitter)

        status = QStatusBar(self)
        self.setStatusBar(status)
        self.status_label = QLabel("Ready")
        status.addWidget(self.status_label, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(150)
        self.progress.setFixedHeight(14)
        self.progress.hide()
        status.addPermanentWidget(self.progress)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(5000)
        self.log_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_edit.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.log_dock = QDockWidget("Activity", self)
        self.log_dock.setObjectName("activityDock")
        self.log_dock.setWidget(self.log_edit)
        self.log_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        self.log_dock.hide()
        self.view_menu.addAction(self.log_dock.toggleViewAction())
        i18n.translate_widget_tree(self)

    # -------------------------------------------------------------- library

    def _iter_tree(self, item: QTreeWidgetItem):
        yield item
        for index in range(item.childCount()):
            yield from self._iter_tree(item.child(index))

    def _select_filter(self, kind: str, user: str | None) -> None:
        self._current_filter = (kind, user)
        for top_index in range(self.tree.topLevelItemCount()):
            for item in self._iter_tree(self.tree.topLevelItem(top_index)):
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data == {"kind": kind, "user": user}:
                    self.tree.setCurrentItem(item)
                    return

    def _header_item(self, text: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([text])
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)
        item.setForeground(0, QBrush(self.palette().placeholderText()))
        return item

    def _filter_item(
        self,
        text: str,
        kind: str,
        user: str | None,
        icon: QIcon,
        tooltip: str = "",
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem([text])
        item.setIcon(0, icon)
        item.setData(0, Qt.ItemDataRole.UserRole, {"kind": kind, "user": user})
        if tooltip:
            item.setToolTip(0, tooltip)
        return item

    def _rebuild_sidebar(self, stats: dict[str, int], users: list[dict]) -> None:
        current = self._current_filter
        self.tree.blockSignals(True)
        self.tree.clear()

        library_header = self._header_item(i18n.tr("Library"))
        self.tree.addTopLevelItem(library_header)
        library_header.addChild(
            self._filter_item(
                i18n.trf("All wallpapers ({count})", count=stats["total"]),
                "all",
                None,
                self._icon("folder-pictures"),
            )
        )
        library_header.addChild(
            self._filter_item(
                i18n.trf("Local ({count})", count=stats["local"]),
                "local",
                None,
                self._icon("folder"),
            )
        )
        library_header.addChild(
            self._filter_item(
                i18n.trf("X ({count})", count=stats["x"]),
                "x",
                None,
                self._icon("internet-web-browser"),
            )
        )

        users_header = self._header_item(i18n.tr("X users"))
        self.tree.addTopLevelItem(users_header)
        if users:
            for user in users:
                tooltip_parts = []
                if user.get("last_sync"):
                    from datetime import datetime

                    tooltip_parts.append(
                        i18n.trf(
                            "Last sync: {date}",
                            date=datetime.fromtimestamp(int(user["last_sync"])).strftime(
                                "%Y-%m-%d %H:%M"
                            ),
                        )
                    )
                if user.get("last_error"):
                    tooltip_parts.append(i18n.trf("Last error: {error}", error=user["last_error"]))
                elif user.get("last_status"):
                    tooltip_parts.append(i18n.trf("Status: {status}", status=user["last_status"]))
                users_header.addChild(
                    self._filter_item(
                        i18n.trf("@{user} ({count})", user=user["user"], count=user["count"]),
                        "user",
                        user["user"],
                        self._icon("user-home", "user-identity"),
                        "\n".join(tooltip_parts),
                    )
                )
        else:
            empty = QTreeWidgetItem([i18n.tr("No users yet")])
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            empty.setForeground(0, QBrush(self.palette().placeholderText()))
            users_header.addChild(empty)

        self.tree.expandAll()
        self.tree.blockSignals(False)
        self._select_filter(current[0], current[1])
        if self.tree.currentItem() is None:
            self._select_filter("all", None)

    def refresh(self) -> None:
        stats = db.fetch_stats()
        users = db.fetch_users()
        self._rebuild_sidebar(stats, users)
        self._reload_assets()

    def _reload_assets(self) -> None:
        current_asset = self._current_asset()
        current_id = int(current_asset["id"]) if current_asset else None
        kind, user = self._current_filter
        rows = db.fetch_assets(kind, user, self.search.text())
        self.model.set_rows(rows)
        restored = False
        if current_id is not None:
            for row_index, row in enumerate(rows):
                if int(row["id"]) == current_id:
                    model_index = self.model.index(row_index, 0)
                    self.list_view.setCurrentIndex(model_index)
                    self.list_view.selectionModel().select(
                        model_index, QItemSelectionModel.SelectionFlag.ClearAndSelect
                    )
                    self.details.show_asset(row)
                    restored = True
                    break
        if not restored:
            self.details.clear()
        if rows:
            self.stack.setCurrentWidget(self.list_view)
        else:
            self.stack.setCurrentWidget(self.empty_page)
            self._update_empty_text(kind, user)
        count = len(rows)
        self.status_label.setText(i18n.trn("{count} wallpaper", "{count} wallpapers", count))

    def _update_empty_text(self, kind: str, user: str | None) -> None:
        if self.search.text().strip():
            self.empty_label.setText(
                i18n.trf("No wallpapers match “{query}”.", query=self.search.text().strip())
            )
        elif user:
            self.empty_label.setText(
                i18n.trf(
                    "No wallpapers from @{user} yet.\n"
                    "Press F5 or use Sync to download the media timeline.",
                    user=user,
                )
            )
        elif kind == "local":
            self.empty_label.setText(
                i18n.tr("No local wallpapers indexed yet.\nImport a folder to index it in place.")
            )
        elif kind == "x":
            self.empty_label.setText(
                i18n.tr("No X wallpapers yet.\nAdd an X user and sync their media timeline.")
            )
        else:
            self.empty_label.setText(
                i18n.tr(
                    "Your wallpaper library is empty.\n"
                    "Import an existing folder, or add an X user to download their media."
                )
            )

    def _on_tree_selection(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind = data.get("kind", "all")
        user = data.get("user")
        if (kind, user) == self._current_filter:
            return
        self._current_filter = (kind, user)
        self._reload_assets()

    # ------------------------------------------------------------- actions

    def _choose_import(self) -> None:
        if self._busy:
            return
        start = self.settings.value("import_dir", str(Path.home() / "Pictures"))
        chosen = QFileDialog.getExistingDirectory(
            self, i18n.tr("Import wallpaper folder"), str(start)
        )
        if not chosen:
            return
        self.settings.setValue("import_dir", chosen)
        self._start_import(Path(chosen))

    def _start_import(self, root: Path) -> None:
        self._append_log(f"Indexing {root} …")
        worker = ImportWorker(paths.DB_PATH, root, self)
        worker.log.connect(self._append_log)
        worker.finished_ok.connect(self._import_done)
        worker.failed.connect(self._worker_failed)
        self._begin_worker(worker, i18n.trf("Indexing {name}…", name=root.name))

    def _add_user(self) -> None:
        if self._busy:
            return
        dialog = AddUserDialog(self)
        if dialog.exec() != AddUserDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        user = values["user"]
        if not user:
            return
        db.ensure_user(user)
        db.set_setting("cookies_browser", values["browser"])
        db.set_setting("cookies_keyring", values["keyring"])
        db.set_setting("proxy", values["proxy"])
        self.sync_action.setStatusTip("Sync the selected X user, or all X users")
        self.refresh()
        self._select_filter("user", user)
        self._start_sync()

    def _start_sync(self) -> None:
        if self._busy:
            return
        kind, user = self._current_filter
        if kind == "user" and user:
            users = [user]
        else:
            users = [entry["user"] for entry in db.fetch_users()]
        if not users:
            QMessageBox.information(self, i18n.tr("No X users"), i18n.tr("Add an X user first."))
            return
        library_dir = db.library_dir()
        try:
            library_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            QMessageBox.critical(
                self, i18n.tr("Cannot create download folder"), str(error)
            )
            return

        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.setProgram(sys.executable)
        arguments = [
            "-m",
            "wallkeep.sync_cli",
            "--browser",
            db.get_setting("cookies_browser", "firefox"),
            "--keyring",
            db.get_setting("cookies_keyring", "gnomekeyring"),
        ]
        proxy = db.get_setting("proxy", "").strip()
        if proxy:
            arguments += ["--proxy", proxy]
        for entry in users:
            arguments += ["--user", entry]
        process.setArguments(arguments)

        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONUNBUFFERED", "1")
        environment.insert("PYTHONIOENCODING", "utf-8")
        process.setProcessEnvironment(environment)
        process.readyReadStandardOutput.connect(self._read_sync_output)
        process.finished.connect(self._sync_process_finished)
        process.errorOccurred.connect(self._sync_process_error)

        self._sync_process = process
        self._sync_buffer = ""
        self._sync_errors = []
        self._sync_cancel_requested = False
        if len(users) == 1:
            label = i18n.trf("Syncing {target}…", target=f"@{users[0]}")
        else:
            label = i18n.trf("Syncing {count} X users…", count=len(users))
        self._set_busy(True, label)
        self._live_timer.start()
        process.start()

    def _begin_worker(self, worker, label: str) -> None:
        self._worker = worker
        self._set_busy(True, label)
        worker.finished.connect(self._thread_finished)
        worker.start()

    def _read_sync_output(self) -> None:
        process = self._sync_process
        if process is None:
            return
        chunk = bytes(process.readAllStandardOutput()).decode("utf-8", "replace")
        if chunk:
            self._sync_buffer += chunk.replace("\r", "\n")
        while "\n" in self._sync_buffer:
            line, self._sync_buffer = self._sync_buffer.split("\n", 1)
            self._handle_sync_line(line)

    def _handle_sync_line(self, line: str) -> None:
        line = line.rstrip()
        if not line:
            return
        if line.startswith(RESULT_MARKER):
            try:
                result = json.loads(line[len(RESULT_MARKER) :])
            except ValueError:
                self._append_log(line)
                return
            counts = result.get("counts", {})
            user = result.get("user", "?")
            self._append_log(
                f"@{user}: {counts.get('downloaded', 0)} new, "
                f"{counts.get('duplicate', 0)} duplicates, "
                f"{counts.get('similar', 0)} similar, "
                f"{counts.get('skipped', 0)} already indexed, "
                f"{counts.get('failed', 0)} failed"
            )
            if result.get("error"):
                self._sync_errors.append(f"@{user}: {result['error']}")
        elif line.startswith(ERROR_MARKER):
            message = line[len(ERROR_MARKER) :]
            self._sync_errors.append(message)
            self._append_log(message)
        elif line.startswith(USER_MARKER):
            try:
                user = json.loads(line[len(USER_MARKER) :])
            except ValueError:
                user = "?"
            self._append_log(f"Syncing @{user}…")
        else:
            self._append_log(line)

    def _sync_process_finished(self, exit_code: int, _exit_status) -> None:
        process = self._sync_process
        if process is None:
            return
        self._read_sync_output()
        if self._sync_buffer.strip():
            self._handle_sync_line(self._sync_buffer)
            self._sync_buffer = ""
        self._live_timer.stop()
        self._sync_process = None
        process.deleteLater()
        self._set_busy(False, i18n.tr("Ready"))
        self.refresh()
        if self._sync_cancel_requested:
            self.status_label.setText(i18n.tr("Sync cancelled"))
        elif exit_code != 0 or self._sync_errors:
            self.log_dock.show()
            errors = self._sync_errors or [
                f"sync helper exited with code {exit_code}"
            ]
            hint = ""
            if any(
                "AuthRequired" in error
                or "authenticated cookies" in error
                or "could not be decrypted" in error
                for error in errors
            ):
                hint = "\n\n" + i18n.tr(
                    "X rejected the cookies. Set Cookie keyring to GNOME keyring, "
                    "or log in to x.com again in the browser."
                )
            QMessageBox.warning(
                self,
                i18n.tr("Sync finished with errors"),
                "\n".join(errors[:3]) + ("\n…" if len(errors) > 3 else "") + hint,
            )
            self.status_label.setText(i18n.tr("Sync finished with errors"))
        else:
            self.status_label.setText(i18n.tr("Sync complete"))
        self._sync_cancel_requested = False

    def _sync_process_error(self, error) -> None:
        if self._sync_process is None:
            return
        if error == QProcess.ProcessError.FailedToStart:
            self._sync_errors.append("Failed to start sync helper")
            self._append_log("Failed to start sync helper")
            self._sync_process_finished(-1, QProcess.ExitStatus.CrashExit)
        else:
            self._append_log(f"Sync process error: {error}")

    def _kill_sync(self) -> None:
        if self._sync_process is not None:
            self._sync_process.kill()

    def _find_duplicates(self) -> None:
        if self._busy:
            return
        threshold = int(db.get_setting("similar_threshold", "8") or 0)
        if threshold <= 0:
            QMessageBox.information(
                self,
                i18n.tr("Duplicate images"),
                i18n.tr("The similarity threshold is 0. Set it in Settings first."),
            )
            return
        self._pending_duplicates = None
        worker = DuplicateWorker(paths.DB_PATH, threshold, self)
        worker.progress.connect(self._duplicate_progress)
        worker.log.connect(self._append_log)
        worker.finished_ok.connect(self._duplicates_ready)
        worker.failed.connect(self._worker_failed)
        self._begin_worker(worker, i18n.tr("Scanning fingerprints…"))

    def _duplicate_progress(self, done: int, total: int, phase: str) -> None:
        if phase == "fingerprints":
            self.status_label.setText(
                i18n.trf("Computing fingerprints… {done}/{total}", done=done, total=total)
            )
        else:
            self.status_label.setText(
                i18n.trf("Comparing fingerprints… {done}/{total}", done=done, total=total)
            )

    def _duplicates_ready(self, groups: list[list[dict]]) -> None:
        self._pending_duplicates = groups

    def _thread_finished(self) -> None:
        worker = self._worker
        self._worker = None
        self._set_busy(False, i18n.tr("Ready"))
        if worker is not None:
            worker.deleteLater()
        self.refresh()
        groups = self._pending_duplicates
        self._pending_duplicates = None
        if groups is None:
            return
        if not groups:
            QMessageBox.information(
                self,
                i18n.tr("No duplicates found"),
                i18n.trf(
                    "No duplicates found at the current pHash threshold ({threshold}).",
                    threshold=db.get_setting("similar_threshold", "8"),
                ),
            )
            return
        dialog = DuplicatesDialog(groups, paths.DB_PATH, self)
        dialog.exec()
        self.refresh()

    def _stop(self) -> None:
        if self._sync_process is not None:
            self.status_label.setText(i18n.tr("Stopping…"))
            self._sync_cancel_requested = True
            self.stop_action.setEnabled(False)
            self._sync_process.terminate()
            QTimer.singleShot(5000, self._kill_sync)
            return
        if self._worker is None:
            return
        self.status_label.setText(i18n.tr("Stopping…"))
        self._worker.requestInterruption()
        self.stop_action.setEnabled(False)

    def _set_busy(self, busy: bool, label: str) -> None:
        self._busy = busy
        for action in (
            self.import_action,
            self.add_user_action,
            self.sync_action,
            self.duplicates_action,
            self.settings_action,
        ):
            action.setEnabled(not busy)
        self.stop_action.setEnabled(busy)
        self.progress.setVisible(busy)
        self.status_label.setText(label)

    def _import_done(self, result: dict) -> None:
        summary = i18n.trf(
            "Imported {imported} new, {duplicate} duplicates, "
            "{skipped} already indexed, {failed} failed.",
            imported=result.get("imported", 0),
            duplicate=result.get("duplicate", 0),
            skipped=result.get("skipped", 0),
            failed=result.get("failed", 0),
        )
        self._append_log(summary)
        self.status_label.setText(summary)

    def _apply_live_import(self) -> None:
        kind, current = self._current_filter
        rows = db.fetch_assets(kind, current, self.search.text())
        known = self.model.existing_ids()
        new_rows = [row for row in rows if int(row["id"]) not in known]
        if new_rows:
            self.model.prepend_rows(new_rows)
            self.stack.setCurrentWidget(self.list_view)

    def _worker_failed(self, message: str) -> None:
        self._append_log(f"Error: {message}")
        self.log_dock.show()
        QMessageBox.critical(self, i18n.tr("Wallkeep error"), message)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        db.set_setting("library_dir", values["library_dir"])
        db.set_setting("cookies_browser", values["browser"])
        db.set_setting("cookies_keyring", values["keyring"])
        db.set_setting("proxy", values["proxy"])
        db.set_setting("language", values["language"])
        db.set_setting("similar_threshold", values["similar_threshold"])
        self._append_log(f"Settings saved. X downloads go to {values['library_dir']}")

    def _about(self) -> None:
        QMessageBox.about(
            self,
            i18n.tr("About Wallkeep"),
            i18n.tr(
                "<b>Wallkeep</b><br>"
                "A local-first wallpaper library for indexing, browsing, "
                "deduplicating and categorizing local images.<br><br>"
                "Wallkeep does not download from X itself: optional X sync "
                "is delegated entirely to gallery-dl."
            ),
        )

    # ------------------------------------------------------------ selection

    def _current_asset(self) -> dict | None:
        index = self.list_view.currentIndex()
        return self.model.row_at(index) if index.isValid() else None

    def _selected_assets(self) -> list[dict]:
        selection = self.list_view.selectionModel()
        return [
            row
            for index in selection.selectedIndexes()
            if (row := self.model.row_at(index)) is not None
        ]

    def _on_selection_changed(self, *_args) -> None:
        self.details.show_asset(self._current_asset())

    def _context_menu(self, position) -> None:
        index = self.list_view.indexAt(position)
        if not index.isValid():
            return
        selection = self.list_view.selectionModel()
        if not selection.isSelected(index):
            selection.select(
                index, QItemSelectionModel.SelectionFlag.ClearAndSelect
            )
            self.list_view.setCurrentIndex(index)
        asset = self.model.row_at(index)
        if not asset:
            return
        assets = self._selected_assets() or [asset]
        menu = QMenu(self)
        wallpaper_action = menu.addAction(
            self._icon("preferences-desktop-wallpaper"), i18n.tr("Set as wallpaper")
        )
        open_action = menu.addAction(self._icon("document-open"), i18n.tr("Open"))
        folder_action = menu.addAction(self._icon("folder-open"), i18n.tr("Show in folder"))
        menu.addSeparator()
        copy_action = menu.addAction(self._icon("edit-copy"), i18n.tr("Copy path"))
        menu.addSeparator()
        delete_action = menu.addAction(
            self._icon("edit-delete", "user-trash"), i18n.tr("Delete…")
        )
        chosen = menu.exec(self.list_view.viewport().mapToGlobal(position))
        if chosen == wallpaper_action:
            self._set_wallpaper(asset["path"])
        elif chosen == open_action:
            self._open_path(asset["path"])
        elif chosen == folder_action:
            self._reveal_path(asset["path"])
        elif chosen == copy_action:
            QApplication.clipboard().setText(asset["path"])
        elif chosen == delete_action:
            self._delete_assets(assets)

    def _delete_assets(self, assets: list[dict]) -> None:
        if not assets:
            return
        if self._busy:
            self.status_label.setText(i18n.tr("Wait for the current task to finish."))
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = library.trash_assets(
                paths.DB_PATH,
                {asset["id"] for asset in assets},
                log=self._append_log,
            )
        finally:
            QApplication.restoreOverrideCursor()
        if result["deleted"]:
            self.refresh()
            self.status_label.setText(
                i18n.trf("Moved {count} images to the trash.", count=result["deleted"])
            )
        if result["errors"]:
            QMessageBox.warning(
                self,
                i18n.tr("Could not move to trash"),
                "\n".join(result["errors"][:8]),
            )
        elif not result["deleted"]:
            QMessageBox.warning(
                self,
                i18n.tr("Could not move to trash"),
                i18n.tr("No images were deleted."),
            )

    def _open_current(self) -> None:
        asset = self._current_asset()
        if asset:
            self._open_path(asset["path"])

    def _set_wallpaper(self, path: str) -> None:
        try:
            method = wallpaper.set_wallpaper(Path(path))
        except Exception as error:  # noqa: BLE001 - shown to the user
            QMessageBox.critical(self, i18n.tr("Could not set wallpaper"), str(error))
            return
        self.status_label.setText(i18n.trf("Wallpaper set via {method}", method=method))
        self._append_log(f"Wallpaper set: {path} ({method})")

    def _open_path(self, path: str) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _reveal_path(self, path: str) -> None:
        path_obj = Path(path)
        if shutil.which("dolphin"):
            if QProcess.startDetached("dolphin", ["--select", str(path_obj)]):
                return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path_obj.parent)))

    def _focus_search(self) -> None:
        self.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search.selectAll()

    # -------------------------------------------------------------- helpers

    def _append_log(self, message: str) -> None:
        self.log_edit.appendPlainText(message)
        scrollbar = self.log_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _restore_state(self) -> None:
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self.settings.value("windowState")
        if state is not None:
            self.restoreState(state)
        splitter = self.settings.value("splitter")
        if splitter is not None:
            self.splitter.restoreState(splitter)

    def _save_state(self) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("splitter", self.splitter.saveState())

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._busy:
            answer = QMessageBox.question(
                self,
                i18n.tr("Stop task?"),
                i18n.tr("A library task is still running. Stop it and quit?"),
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._sync_cancel_requested = True
            process = self._sync_process
            if process is not None:
                process.terminate()
                if not process.waitForFinished(4000):
                    process.kill()
                    process.waitForFinished(1000)
                self._sync_process = None
            self._live_timer.stop()
            if self._worker is not None:
                self._worker.requestInterruption()
                self._worker.wait(4000)
        self._save_state()
        event.accept()
