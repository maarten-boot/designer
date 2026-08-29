"""designer-model — the Designer data model.

Standard library only, and no UI: this package is what a generator, a CLI or a
different front end would depend on. A test asserts it never imports tkinter.
"""

from .check import Checker, Report, check
from .codes import REGISTRY, CodeDefinition, blocks_export, definition
from .commands import Command, CommandStack, Macro
from .deletion import DeletePlan, plan_delete
from .derive import Deriver
from .diagnostics import Consequence, Diagnostic, Scope, Severity, Subject
from .model import (
    BaseTypeRef,
    Binding,
    Context,
    Entity,
    Model,
    Property,
    Schema,
    SchemaBinding,
    Slot,
    Type,
    TypeRef,
    Validator,
)
from .persistence import DocumentError, dump, dumps, load, save
from .session import Session, read_autosave
from .stdlib import Library, standard_library

__all__ = [
    "REGISTRY",
    "BaseTypeRef",
    "Binding",
    "Checker",
    "CodeDefinition",
    "Command",
    "CommandStack",
    "Consequence",
    "Context",
    "DeletePlan",
    "Deriver",
    "Diagnostic",
    "DocumentError",
    "Entity",
    "Library",
    "Macro",
    "Model",
    "Property",
    "Report",
    "Schema",
    "SchemaBinding",
    "Scope",
    "Session",
    "Severity",
    "Slot",
    "Subject",
    "Type",
    "TypeRef",
    "Validator",
    "blocks_export",
    "check",
    "definition",
    "dump",
    "dumps",
    "load",
    "plan_delete",
    "read_autosave",
    "save",
    "standard_library",
]
