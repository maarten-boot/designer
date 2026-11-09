"""SQL table definitions from a Designer schema export.

Reads the JSON that `designer-export` writes and writes CREATE TABLE
statements for PostgreSQL, MariaDB or SQLite. Standard library only.
"""

from .dialects import DIALECTS, Dialect, Untranslatable, dialect
from .generate import ExportFileError, Report, generate

__all__ = ["DIALECTS", "Dialect", "ExportFileError", "Report", "Untranslatable", "dialect", "generate"]
