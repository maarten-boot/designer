"""Entry point.

tkinter is in the standard library but packaged separately on Debian and Ubuntu,
so it cannot be declared as a dependency. The check happens before anything
else, and says what to install rather than letting an ImportError traceback be
the user's first experience.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TKINTER_MISSING = """\
Designer needs tkinter, which is part of the Python standard library but is
packaged separately on some systems.

    Debian / Ubuntu   sudo apt install python3-tk
    Fedora            sudo dnf install python3-tkinter
    macOS (Homebrew)  brew install python-tk
"""


def check_tkinter() -> bool:
    try:
        import tkinter  # noqa: F401
    except ImportError:
        return False
    return True


def _startup_model(settings, path: Path | None):
    """Recovery first, then the last file, then nothing.

    Reopening must never prevent startup: a file that is missing, unreadable, or
    written by a newer build gives an empty model and a note, not a failure.
    """
    from tkinter import messagebox

    from designer_model import Session, read_autosave

    from .state import config_dir

    if path is not None:
        return Session.open(path, undo_limit=settings.undo_limit), None

    recovered = read_autosave(config_dir())
    if recovered is not None:
        belongs = recovered.path.name if recovered.path else "an unsaved model"
        keep = messagebox.askyesno(
            "Recover unsaved work",
            f"The last session did not end cleanly.\n\n"
            f"Recover {belongs}, last written {recovered.saved_at:%H:%M on %d %b}?",
        )
        if keep:
            session = Session(recovered.model, recovered.path, undo_limit=settings.undo_limit)
            return session, None
        Session().clear_autosave(config_dir())

    if settings.last_file and Path(settings.last_file).exists():
        try:
            return Session.open(settings.last_file, undo_limit=settings.undo_limit), None
        except Exception as error:
            return Session(undo_limit=settings.undo_limit), f"{settings.last_file}: {error}"

    return Session(undo_limit=settings.undo_limit), None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="designer", description="Author a data model.")
    parser.add_argument("model", nargs="?", type=Path, help="a model file to open")
    arguments = parser.parse_args(argv)

    if not check_tkinter():
        print(TKINTER_MISSING, file=sys.stderr)
        return 1

    from tkinter import messagebox

    from .app import DesignerApp
    from .state import Settings

    settings = Settings.load()
    session, complaint = _startup_model(settings, arguments.model)
    app = DesignerApp(session, settings)
    if complaint:
        messagebox.showwarning("Could not reopen", complaint)
    if session.path:
        settings.remember(session.path)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
