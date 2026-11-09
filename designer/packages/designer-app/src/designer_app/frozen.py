"""The entry point of the frozen build (spec §14.5).

A frozen executable is its own interpreter and runs only this script, so the
jobs `python -m` would do elsewhere arrive here as flags, looked at before
anything else is imported:

    Designer [model.json]                   the application, as `designer`
    Designer --bench-worker                 the test bench's worker (bench.py)
    Designer --self-test MODEL REPORT       open a window over MODEL, run one
                                            test-bench trial through the worker,
                                            close, and write what happened to
                                            REPORT; exit status 0 if it worked

The self-test writes to a file rather than printing because a windowed build
on Windows has no console to print to. It is what the release workflow runs on
each platform: a build that cannot open a window, find its bundled library or
start its own worker fails there, not on a user's machine.
"""

from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile
import traceback

SELF_TEST = "--self-test"


def self_test(model_path: str, report_path: str) -> int:
    lines: list[str] = []
    status = 1
    scratch: pathlib.Path | None = None
    restore: list[tuple[object, object]] = []
    try:
        from designer_model import Session, bench

        from . import app as app_module
        from . import state
        from .app import DesignerApp
        from .state import Settings

        # never the user's own settings or autosave: both modules that hold
        # the name are pointed at a scratch folder
        scratch = pathlib.Path(tempfile.mkdtemp(prefix="designer-self-test-"))
        for module in (state, app_module):
            restore.append((module, module.config_dir))
            module.config_dir = lambda: scratch  # type: ignore[attr-defined]

        session = Session.open(model_path)
        lines.append(f"opened {model_path}: {len(session.model.index())} items")
        app = DesignerApp(session, Settings())
        app.update()
        lines.append(f"window: {app.winfo_width()}x{app.winfo_height()}, contrast {app.settings.contrast}")
        app.destroy()

        target = session.model.types[0]
        trial = bench.run(session.model, target.uuid, "x")
        lines.append(f"bench on {target.name}: {trial.summary}")
        if trial.stopped:
            raise RuntimeError(f"the bench worker did not answer: {trial.stopped}")
        status = 0
        lines.append("ok")
    except BaseException:  # the report must say why, whatever it was
        lines.append(traceback.format_exc())
    finally:
        for module, original in restore:
            module.config_dir = original  # type: ignore[attr-defined]
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
    pathlib.Path(report_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return status


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    from designer_model import bench

    if args[:1] == [bench.WORKER_FLAG]:
        bench.worker_main()
        return 0
    if args[:1] == [SELF_TEST]:
        if len(args) != 3:
            print(f"usage: Designer {SELF_TEST} MODEL REPORT", file=sys.stderr)
            return 2
        return self_test(args[1], args[2])

    from .main import main as application

    return application(args)


if __name__ == "__main__":
    raise SystemExit(main())
