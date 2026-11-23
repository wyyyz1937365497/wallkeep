from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .. import library


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
