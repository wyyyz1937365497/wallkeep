from __future__ import annotations

import sys

from .ui.theme import install_qt_plugin_path

install_qt_plugin_path()

from PySide6.QtWidgets import QApplication  # noqa: E402

from . import db, i18n, paths  # noqa: E402
from .ui.main_window import MainWindow  # noqa: E402
from .ui.theme import configure_application  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    paths.ensure_dirs()
    db.init_db()
    app = QApplication(argv if argv is not None else sys.argv)
    i18n.configure(db.get_setting("language", "auto"))
    configure_application(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
