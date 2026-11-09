"""Build the frozen application for this platform, and prove it runs.

    python3 tools/freeze.py                  build, then self-test
    python3 tools/freeze.py --no-self-test   build only

One download per platform with Python and tkinter inside, made by PyInstaller
(spec §14.5). It cannot cross-build: Linux builds Linux, and the release
workflow (`.github/workflows/frozen.yml` at the repository root) runs this
on Linux, Windows and macOS. Results go to `dist-frozen/`, not `dist/`, which
`tools/release.py` empties.

    linux    designer-X.Y.Z-linux-x86_64.tar.gz    a folder; run `Designer` in it
    windows  designer-X.Y.Z-windows-x86_64.zip     a folder; run `Designer.exe` in it
    macos    designer-X.Y.Z-macos-arm64.zip        `Designer.app`

A folder, not a single file, on every platform: a one-file build unpacks itself
to a temporary folder at every start, and the test bench starts a new worker
for every trial within `bench.TIMEOUT` (2 s) — which the unpacking alone can
use up, on Windows above all, where a virus scanner reads it first.

After building, it runs the executable's self-test (`--self-test`, see
`designer_app/frozen.py`): open a window over the worked example, start the
test bench's worker from the frozen executable, write a report. A build that
only compiled has not been verified. On Linux the self-test needs a display:
run under `xvfb-run -a` when there is none.

Without PyInstaller in the running Python it makes an environment for it in
this machine's cache, `~/.cache/designer-release/freeze-pyX.Y/`, as
`release.py` does for `build`, and never inside the repository (turn 151).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from release import CACHE, ROOT, run, versions

OUT = ROOT / "dist-frozen"
ENTRY = ROOT / "tools" / "frozen_entry.py"
EXAMPLE = ROOT / "examples" / "sales.json"
PYINSTALLER = "pyinstaller>=6.10"
BUNDLE_ID = "io.github.maarten-boot.designer"


def system() -> str:
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def machine() -> str:
    raw = platform.machine().lower()
    return {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}.get(raw, raw)


def ensure_pyinstaller() -> None:
    """Re-run this script under a Python that has PyInstaller, if this one
    does not."""
    if importlib.util.find_spec("PyInstaller") is not None:
        return
    if os.environ.get("DESIGNER_FREEZE_ENV"):
        raise SystemExit("PyInstaller is still missing in the build environment")
    environment = CACHE / f"freeze-py{sys.version_info.major}.{sys.version_info.minor}"
    bindir = "Scripts" if sys.platform == "win32" else "bin"
    python = (
        environment / bindir / ("python.exe" if sys.platform == "win32" else "python")
    )
    if not python.exists():
        print(f"making a build environment in {environment}")
        venv.create(environment, with_pip=True)
    run(python, "-m", "pip", "install", "--quiet", "--upgrade", PYINSTALLER)
    env = {**os.environ, "DESIGNER_FREEZE_ENV": "1"}
    raise SystemExit(subprocess.call([str(python), __file__, *sys.argv[1:]], env=env))


def build(work: pathlib.Path) -> pathlib.Path:
    """PyInstaller's output for this platform: the executable, or the .app."""
    mac = system() == "macos"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--log-level=WARN",
        "--name=Designer",
        "--windowed",
        "--onedir",
        f"--distpath={work / 'dist'}",
        f"--workpath={work / 'build'}",
        f"--specpath={work}",
        f"--paths={ROOT / 'packages/designer-model/src'}",
        f"--paths={ROOT / 'packages/designer-app/src'}",
        # stdlib.json, deprecations.json, examples.json: read beside the code.
        # --add-data, not --collect-data, which needs the package installed
        f"--add-data={ROOT / 'packages/designer-model/src/designer_model/data'}{os.pathsep}designer_model/data",
        "--hidden-import=designer_app.frozen",
    ]
    if mac:
        command.append(f"--osx-bundle-identifier={BUNDLE_ID}")
    run(*command, str(ENTRY))
    dist = work / "dist"
    return dist / ("Designer.app" if mac else "Designer")


def executable_in(built: pathlib.Path) -> pathlib.Path:
    if built.suffix == ".app":
        return built / "Contents" / "MacOS" / "Designer"
    return built / ("Designer.exe" if system() == "windows" else "Designer")


def self_test(built: pathlib.Path, work: pathlib.Path) -> int:
    report = work / "self-test.txt"
    command = [str(executable_in(built)), "--self-test", str(EXAMPLE), str(report)]
    print("  $", " ".join(command))
    try:
        status = subprocess.run(command, check=False, timeout=180).returncode
    except subprocess.TimeoutExpired:
        status = -1
        print("self-test: no answer within 180 s", file=sys.stderr)
    print(
        report.read_text(encoding="utf-8")
        if report.exists()
        else "self-test: no report was written"
    )
    return status


def package(built: pathlib.Path, version: str) -> pathlib.Path:
    name = f"designer-{version}-{system()}-{machine()}"
    OUT.mkdir(exist_ok=True)
    licence = (
        ROOT.parent / "LICENSE"
        if (ROOT.parent / "LICENSE").exists()
        else ROOT / "LICENSE"
    )
    if system() == "linux":
        target = OUT / f"{name}.tar.gz"
        with tarfile.open(target, "w:gz") as archive:
            archive.add(built, arcname=name)  # keeps the executable bits
            archive.add(licence, arcname=f"{name}/LICENSE")
    elif system() == "macos":
        target = OUT / f"{name}.zip"
        target.unlink(missing_ok=True)
        # ditto, not zipfile: a bundle holds symlinks and executable bits
        run("ditto", "-c", "-k", "--keepParent", built, target)
    else:
        target = OUT / f"{name}.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(built.rglob("*")):
                archive.write(path, f"{name}/{path.relative_to(built).as_posix()}")
            archive.write(licence, f"{name}/LICENSE")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--no-self-test", action="store_true", help="build without running the result"
    )
    arguments = parser.parse_args()

    found = versions()
    if len(set(found.values())) != 1:
        print(f"versions disagree: {found}", file=sys.stderr)
        return 1
    version = found["designer-model"]
    ensure_pyinstaller()
    print(
        f"designer {version}, frozen for {system()}-{machine()} on Python {platform.python_version()}"
    )

    work = pathlib.Path(tempfile.mkdtemp(prefix="designer-freeze-"))
    try:
        built = build(work)
        if not arguments.no_self_test and self_test(built, work) != 0:
            print("\nthe self-test failed; nothing was packaged", file=sys.stderr)
            return 1
        target = package(built, version)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"\n{target.relative_to(ROOT)}  {target.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
