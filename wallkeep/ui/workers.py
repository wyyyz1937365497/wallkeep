from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .. import library, xsync


class ImportWorker(QThread):
    log = Signal(str)
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, db_path: Path, root: Path, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.root = Path(root)

    def run(self) -> None:
        def progress(done: int, total: int, path: Path) -> None:
            if done == 1 or done == total or done % 20 == 0:
                self.log.emit(f"Indexing {done}/{total}: {path.name}")

        try:
            result = library.import_folder(
                self.db_path,
                self.root,
                on_progress=progress,
                cancel=self.isInterruptionRequested,
            )
        except Exception as error:  # noqa: BLE001 - reported to the UI
            self.failed.emit(str(error))
        else:
            self.finished_ok.emit(result)


class SyncWorker(QThread):
    log = Signal(str)
    imported = Signal(str, dict)
    finished_ok = Signal(dict)
    failed = Signal(str)
    def __init__(
        self,
        *,
        db_path: Path,
        library_dir: Path,
        users: list[str],
        options: xsync.SyncOptions,
        parent=None,
    ):
        super().__init__(parent)
        self.db_path = db_path
        self.library_dir = Path(library_dir)
        self.users = users
        self.options = options
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        results: list[dict] = []
        try:
            for user in self.users:
                if self._cancel.is_set():
                    break
                self.log.emit(f"Syncing @{user}…")
                try:
                    result = xsync.sync_user(
                        db_path=self.db_path,
                        library_dir=self.library_dir,
                        user=user,
                        options=self.options,
                        log=self.log.emit,
                        cancel=self._cancel,
                        on_import=lambda counts: self.imported.emit(user, counts),
                    )
                except Exception as error:  # noqa: BLE001 - reported to the UI
                    results.append({"user": user, "error": str(error), "counts": {}})
                    self.log.emit(f"@{user} failed: {error}")
                    continue
                results.append(result)
                counts = result.get("counts", {})
                self.log.emit(
                    f"@{user}: {counts.get('downloaded', 0)} new, "
                    f"{counts.get('duplicate', 0)} duplicates, "
                    f"{counts.get('similar', 0)} similar, "
                    f"{counts.get('skipped', 0)} already indexed"
                )
        finally:
            self.finished_ok.emit({"results": results, "cancelled": self._cancel.is_set()})


class DuplicateWorker(QThread):
    progress = Signal(int, int, str)
    log = Signal(str)
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(self, db_path: Path, threshold: int, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.threshold = threshold

    def run(self) -> None:
        try:
            groups = library.scan_duplicates(
                self.db_path,
                self.threshold,
                progress=lambda done, total, phase: self.progress.emit(done, total, phase),
                log=self.log.emit,
                cancel=self.isInterruptionRequested,
            )
        except Exception as error:  # noqa: BLE001 - reported to the UI
            self.failed.emit(str(error))
            return
        if self.isInterruptionRequested():
            return
        self.finished_ok.emit(groups)
