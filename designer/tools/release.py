"""Build the release, and prove it installs.

    python3 tools/release.py

Builds a wheel and an sdist of each package into `dist/`, then installs them
from `dist/` alone — no index, no source tree — into a fresh virtual environment
and runs what a user would run: `designer-check` on the worked example,
`designer-export` compared byte for byte with the committed export, and an
import of the application. A package that has only been built has not been
verified; one that has been installed somewhere clean and run has.

Uses `build` from the running Python if it has it. If not — Debian's and
Ubuntu's Python refuse `pip install` outside a virtual environment (PEP 668) —
it makes its own, `.release-env/`, once, and reuses it. Building fetches
`hatchling` into an isolated environment, so the first run needs the network.
"""

from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import shutil
import subprocess
import sys
import tomllib
import venv

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
TOOLING = ROOT / ".release-env"
PACKAGES = ("designer-model", "designer-app")


def run(*command: str | pathlib.Path, **kwargs) -> subprocess.CompletedProcess:
    print("  $", " ".join(str(c) for c in command))
    return subprocess.run([str(c) for c in command], check=True, **kwargs)


def versions() -> dict[str, str]:
    """Each package's version, and the model version the app pins: they are
    released together, so the three must agree."""
    found = {}
    for name in PACKAGES:
        project = tomllib.loads(
            (ROOT / "packages" / name / "pyproject.toml").read_text()
        )["project"]
        found[name] = project["version"]
        if name == "designer-app":
            pins = [
                d for d in project["dependencies"] if d.startswith("designer-model")
            ]
            found["pinned"] = pins[0].partition("==")[2] if pins else ""
    return found


def builder() -> pathlib.Path:
    """A Python that can run `python -m build`."""
    if importlib.util.find_spec("build") is not None:
        return pathlib.Path(sys.executable)
    python = TOOLING / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    if not python.exists():
        print(f"no `build` module here; making {TOOLING.relative_to(ROOT)}/ for it")
        venv.create(TOOLING, with_pip=True)
        run(python, "-m", "pip", "install", "-q", "build>=1")
    return python


def main() -> int:
    found = versions()
    if len(set(found.values())) != 1:
        print(f"versions disagree: {found}", file=sys.stderr)
        return 1
    version = found["designer-model"]
    print(f"designer {version}")

    shutil.rmtree(DIST, ignore_errors=True)
    DIST.mkdir()
    python = builder()
    for name in PACKAGES:
        run(
            python,
            "-m",
            "build",
            "--outdir",
            DIST,
            ROOT / "packages" / name,
            stdout=subprocess.DEVNULL,
        )

    verify = DIST / ".verify"
    venv.create(verify, with_pip=True)
    bin_dir = verify / ("Scripts" if sys.platform == "win32" else "bin")
    run(
        bin_dir / "python",
        "-m",
        "pip",
        "install",
        "-q",
        "--no-index",
        "--find-links",
        DIST,
        "designer-app",
    )

    # run from somewhere that is not the source tree, so nothing can be
    # imported from it by accident
    elsewhere = {"cwd": verify}
    examples = ROOT / "examples"
    run(
        bin_dir / "designer-check",
        examples / "sales.json",
        "--level",
        "everything",
        stdout=subprocess.DEVNULL,
        **elsewhere,
    )
    exported = run(
        bin_dir / "designer-export",
        examples / "sales.json",
        "sales_schema",
        capture_output=True,
        text=True,
        **elsewhere,
    ).stdout
    if exported != (examples / "sales_schema.export.json").read_text():
        print(
            "the installed exporter does not reproduce examples/sales_schema.export.json",
            file=sys.stderr,
        )
        return 1
    run(
        bin_dir / "python",
        "-c",
        "import designer_app.main, designer_model.bench",
        **elsewhere,
    )
    shutil.rmtree(verify)

    print(f"\nverified; the release is in {DIST.relative_to(ROOT)}/:")
    for artifact in sorted(DIST.iterdir()):
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        print(f"  {artifact.name:42} sha256 {digest[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
