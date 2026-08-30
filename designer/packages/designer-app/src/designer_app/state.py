"""Application state.

Where the window put itself, which files were open, how wide the columns were.
None of it belongs in the model document, and all of it must survive a corrupt
settings file — a bad preferences file is never a reason to fail to start.

The standard library has no `platformdirs` equivalent, so the resolver below is
written out. It is about twenty lines and it is the only thing that would
otherwise pull a dependency into a package tree that has none.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NAME = "Designer"
SETTINGS_NAME = "settings.json"

# Left to right, and the order matters: the model is built from left to right.
# A Context scopes everything; Types and Validators are the primitives; a
# Property is a Type given a name; an Entity is Properties given a shape; a
# Schema is the deliverable. Starting at the Schema would start at the end.
COLUMNS = ("context", "type", "validator", "property", "entity", "schema")

# The visible heading for each. Here rather than in the window, so the order and
# the labels are one thing that cannot drift apart, and so a test can reach them
# without a display.
TITLES = {
    "context": "Context",
    "type": "Type",
    "validator": "Validator",
    "property": "Property",
    "entity": "Entity",
    "schema": "Schema",
}


def config_dir() -> Path:
    """The per-user configuration directory for this platform."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        return Path(base or Path.home() / "AppData/Roaming") / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME")
    return Path(base or Path.home() / ".config") / APP_NAME.lower()


@dataclass
class Settings:
    """Every key exists from the first release, whether or not any interface
    exposes it, so a preferences dialog later needs no format change."""

    recent_files: list[str] = field(default_factory=list)
    last_file: str | None = None
    window_geometry: str | None = None
    sash_positions: list[int] = field(default_factory=list)
    column_widths: dict[str, int] = field(default_factory=dict)
    collapsed_columns: list[str] = field(default_factory=list)
    sort_descending: list[str] = field(default_factory=list)
    finding_level: str = "warning"
    """How much of the model check to show.

    Warnings and above by default: a model under construction is full of
    unfinished items and unreferenced types, and a list that is mostly noise
    trains people to ignore it.
    """
    show_builtins: bool = False
    undo_limit: int = 100
    autosave_delay_ms: int = 250
    recent_files_limit: int = 10

    # --- recent files -------------------------------------------------------

    def remember(self, path: str | Path) -> None:
        """Most recent first, deduplicated by resolved path."""
        resolved = str(Path(path).resolve())
        self.recent_files = [resolved] + [p for p in self.recent_files if p != resolved]
        del self.recent_files[self.recent_files_limit :]
        self.last_file = resolved

    def recent(self) -> list[tuple[str, bool]]:
        """Each recent file with whether it is currently reachable.

        A missing entry is kept and marked rather than dropped: a disconnected
        share or an unmounted volume should not erase history.
        """
        return [(p, Path(p).exists()) for p in self.recent_files]

    def forget(self, path: str | Path) -> None:
        resolved = str(Path(path).resolve())
        self.recent_files = [p for p in self.recent_files if p != resolved]
        if self.last_file == resolved:
            self.last_file = None

    # --- persistence --------------------------------------------------------

    @classmethod
    def load(cls, directory: Path | None = None) -> Settings:
        path = (directory or config_dir()) / SETTINGS_NAME
        try:
            raw = json.loads(path.read_text())
        except (OSError, ValueError):
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        settings = cls(**{k: v for k, v in raw.items() if k in known})
        settings.collapsed_columns = [c for c in settings.collapsed_columns if c in COLUMNS]
        settings.sort_descending = [c for c in settings.sort_descending if c in COLUMNS]
        settings.column_widths = {k: v for k, v in settings.column_widths.items() if k in COLUMNS}
        return settings

    def save(self, directory: Path | None = None) -> Path:
        directory = directory or config_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / SETTINGS_NAME
        scratch = path.with_suffix(".tmp")
        scratch.write_text(json.dumps(asdict(self), indent=2) + "\n")
        scratch.replace(path)
        return path
