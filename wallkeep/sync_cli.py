from __future__ import annotations

import argparse
import json
import signal
import threading

from . import db, paths, xsync

USER_MARKER = "__WALLKEEP_USER__ "
RESULT_MARKER = "__WALLKEEP_RESULT__ "
ERROR_MARKER = "__WALLKEEP_ERROR__ "


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wallkeep X sync helper")
    parser.add_argument("--user", action="append", required=True)
    parser.add_argument("--browser", default="firefox")
    parser.add_argument("--keyring", default="gnomekeyring")
    parser.add_argument("--proxy", default="")
    args = parser.parse_args(argv)

    cancel = threading.Event()

    def stop(_signum, _frame):
        cancel.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    options = xsync.SyncOptions(
        browser=args.browser,
        keyring=args.keyring,
        proxy=args.proxy,
        image_only=True,
    )
    errors: list[str] = []
    for user in args.user:
        if cancel.is_set():
            break
        print(USER_MARKER + json.dumps(user), flush=True)
        try:
            result = xsync.sync_user(
                db_path=paths.DB_PATH,
                library_dir=db.library_dir(),
                user=user,
                options=options,
                log=lambda line: print(line, flush=True),
                cancel=cancel,
            )
        except Exception as error:  # noqa: BLE001 - reported to the GUI
            message = f"@{user}: {error}"
            errors.append(message)
            print(ERROR_MARKER + message, flush=True)
            continue
        print(
            RESULT_MARKER
            + json.dumps(result, ensure_ascii=False, default=str),
            flush=True,
        )
        if result.get("error"):
            errors.append(f"@{user}: {result['error']}")
        if result.get("cancelled"):
            break
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
