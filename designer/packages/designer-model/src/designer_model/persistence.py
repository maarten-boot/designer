"""Persistence.

One JSON document per model: a flat list per kind, every reference a UUID
string, nothing nested (spec §12). The model is a graph, so nesting would force
an arbitrary spanning tree and fixups on load.

Emission is canonical — field order is fixed and optional fields are omitted
when unset — so a load/save round trip is byte-identical and a diff between two
saves shows only what actually changed.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from . import literals
from .model import (
    AnyTypeRef,
    Argument,
    BaseTypeRef,
    Binding,
    Context,
    Entity,
    Index,
    Interface,
    InterfaceBinding,
    LiteralArg,
    Model,
    OrderTerm,
    PathArg,
    Property,
    Schema,
    SchemaBinding,
    Slot,
    SlotArg,
    Type,
    TypeRef,
    Validator,
)

SCHEMA_VERSION = 2


def needed_version(model) -> int:
    """The lowest version that can represent this document.

    Interfaces widened the shape, so a model using them is version 2. One that
    does not stays at 1 and keeps loading in an older build — bumping every
    document on save would strand models that never used the feature, for
    nothing.
    """
    if model.interfaces or any(t.interfaces for t in model.types):
        return 2
    return 1


LIBRARY_VERSION = 1


class DocumentError(ValueError):
    """The document is not a Designer model. Distinct from a model that is
    merely incomplete, which loads fine."""


# --- scalars ----------------------------------------------------------------


def _uuid(raw: Any, what: str) -> UUID:
    try:
        return UUID(raw)
    except (AttributeError, ValueError) as exc:
        raise DocumentError(f"{what}: {raw!r} is not a UUID") from exc


def _opt_uuid(raw: Any, what: str) -> UUID | None:
    return None if raw is None else _uuid(raw, what)


def _stamp(raw: str) -> dt.datetime:
    return literals._decode_datetime(raw)


def _stamp_out(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def _type_ref_in(raw: dict[str, Any] | None, what: str) -> AnyTypeRef | None:
    if raw is None:
        return None
    if "base_type" in raw:
        return BaseTypeRef(raw["base_type"])
    if "type" in raw:
        return TypeRef(_uuid(raw["type"], what))
    raise DocumentError(f"{what}: a type reference is base_type or type")


def _type_ref_out(ref: AnyTypeRef | None) -> dict[str, Any] | None:
    if ref is None:
        return None
    if isinstance(ref, BaseTypeRef):
        return {"base_type": ref.base_type}
    return {"type": str(ref.type_uuid)}


def _arg_in(raw: dict[str, Any], what: str) -> Argument:
    if "literal" in raw:
        return LiteralArg(literals.decode(raw["literal"]))
    if "slot" in raw:
        return SlotArg(_uuid(raw["slot"], what))
    if "path" in raw:
        return PathArg(tuple(_uuid(p, what) for p in raw["path"]))
    raise DocumentError(f"{what}: an argument is literal, slot or path")


def _arg_out(arg: Argument) -> dict[str, Any]:
    if isinstance(arg, LiteralArg):
        return {"literal": literals.encode(arg.literal)}
    if isinstance(arg, SlotArg):
        return {"slot": str(arg.slot)}
    return {"path": [str(p) for p in arg.path]}


# --- bindings ---------------------------------------------------------------


def _binding_in(raw: dict[str, Any], what: str) -> Binding:
    return Binding(
        uuid=_uuid(raw["uuid"], what),
        validator=_opt_uuid(raw.get("validator"), what),
        arguments={k: _arg_in(v, what) for k, v in raw.get("arguments", {}).items()},
        message=raw.get("message"),
    )


def _binding_out(binding: Binding) -> dict[str, Any]:
    out: dict[str, Any] = {
        "uuid": str(binding.uuid),
        "validator": None if binding.validator is None else str(binding.validator),
        "arguments": {k: _arg_out(v) for k, v in binding.arguments.items()},
    }
    if binding.message is not None:
        out["message"] = binding.message
    return out


def _schema_binding_in(raw: dict[str, Any], what: str) -> SchemaBinding:
    return SchemaBinding(
        uuid=_uuid(raw["uuid"], what),
        validator=_opt_uuid(raw.get("validator"), what),
        arguments={k: _arg_in(v, what) for k, v in raw.get("arguments", {}).items()},
        message=raw.get("message"),
        anchor=_opt_uuid(raw.get("anchor"), what),
        enforcement=raw.get("enforcement", "application"),
    )


def _schema_binding_out(binding: SchemaBinding) -> dict[str, Any]:
    return {
        "uuid": str(binding.uuid),
        "validator": None if binding.validator is None else str(binding.validator),
        "anchor": None if binding.anchor is None else str(binding.anchor),
        "arguments": {k: _arg_out(v) for k, v in binding.arguments.items()},
        "message": binding.message,
        "enforcement": binding.enforcement,
    }


# --- slots ------------------------------------------------------------------


def _slot_in(raw: dict[str, Any], what: str) -> Slot:
    kind = raw["kind"]
    slot = Slot(
        uuid=_uuid(raw["uuid"], what),
        slot_name=raw["slot_name"],
        kind=kind,
        required=raw["required"],
        position=raw["position"],
    )
    if kind == "value":
        slot.property = _opt_uuid(raw.get("property"), what)
        default = raw.get("default")
        slot.default = None if default is None else literals.decode(default["literal"])
        slot.type_override = _opt_uuid(raw.get("type_override"), what)
    elif kind == "reference":
        slot.target = _opt_uuid(raw.get("target"), what)
        slot.inverse_name = raw.get("inverse_name")
        slot.on_delete = raw.get("on_delete", "restrict")
    else:
        raise DocumentError(f"{what}: slot kind {kind!r} is not value or reference")
    return slot


def _slot_out(slot: Slot) -> dict[str, Any]:
    out: dict[str, Any] = {
        "uuid": str(slot.uuid),
        "slot_name": slot.slot_name,
        "kind": slot.kind,
        "required": slot.required,
        "position": slot.position,
    }
    if slot.is_value:
        out["property"] = None if slot.property is None else str(slot.property)
        if slot.default is not None:
            out["default"] = {"literal": literals.encode(slot.default)}
        if slot.type_override is not None:
            out["type_override"] = str(slot.type_override)
    else:
        out["target"] = None if slot.target is None else str(slot.target)
        out["inverse_name"] = slot.inverse_name
        out["on_delete"] = slot.on_delete
    return out


# --- items ------------------------------------------------------------------


def _common(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "uuid": _uuid(raw["uuid"], raw.get("name", "?")),
        "name": raw["name"],
        "description": raw.get("description", ""),
        "created": _stamp(raw["created"]),
        "modified": _stamp(raw["modified"]),
    }


def _head_out(item: Any) -> dict[str, Any]:
    return {"uuid": str(item.uuid), "name": item.name, "description": item.description}


def _tail_out(item: Any) -> dict[str, Any]:
    return {"created": _stamp_out(item.created), "modified": _stamp_out(item.modified)}


def load(source: str | Path | dict[str, Any]) -> Model:
    raw = source if isinstance(source, dict) else json.loads(Path(source).read_text())
    if "schema_version" not in raw:
        raise DocumentError("no schema_version: this is not a Designer model")
    if raw["schema_version"] > SCHEMA_VERSION:
        raise DocumentError(
            f"schema_version {raw['schema_version']} is newer than this build understands ({SCHEMA_VERSION})"
        )

    model = Model(schema_version=raw["schema_version"], library_version=raw.get("library_version", LIBRARY_VERSION))

    for c in raw.get("contexts", []):
        model.contexts.append(Context(**_common(c), parent=_opt_uuid(c.get("parent"), c["name"])))

    for v in raw.get("validators", []):
        model.validators.append(
            Validator(
                **_common(v),
                context=_opt_uuid(v.get("context"), v["name"]),
                kind=v.get("kind", "leaf"),
                parameters=tuple(v.get("parameters", ())),
                expression=v.get("expression", ""),
                message=v.get("message", ""),
            )
        )

    # a version 1 file has no interfaces key, which reads as none
    for i in raw.get("interfaces", []):
        model.interfaces.append(
            Interface(
                **_common(i),
                context=_opt_uuid(i.get("context"), i["name"]),
                base_type=i.get("base_type", ""),
                picture=i.get("picture", ""),
                decimal_point=i.get("decimal_point", "."),
                group_mark=i.get("group_mark", ","),
                parse_lenient=i.get("parse_lenient", True),
                blank=i.get("blank", ""),
            )
        )

    for t in raw.get("types", []):
        model.types.append(
            Type(
                **_common(t),
                context=_opt_uuid(t.get("context"), t["name"]),
                parent=_type_ref_in(t.get("parent"), t["name"]),
                validators=[_binding_in(b, t["name"]) for b in t.get("validators", [])],
                interfaces=[
                    InterfaceBinding(
                        uuid=_uuid(b["uuid"], t["name"]),
                        interface=_opt_uuid(b.get("interface"), t["name"]),
                        is_default=b.get("is_default", False),
                    )
                    for b in t.get("interfaces", [])
                ],
            )
        )

    for p in raw.get("properties", []):
        model.properties.append(
            Property(
                **_common(p),
                context=_opt_uuid(p.get("context"), p["name"]),
                type=_type_ref_in(p.get("type"), p["name"]),
            )
        )

    for e in raw.get("entities", []):
        model.entities.append(
            Entity(
                **_common(e),
                context=_opt_uuid(e.get("context"), e["name"]),
                abstract=e.get("abstract", False),
                extends=_opt_uuid(e.get("extends"), e["name"]),
                slots=[_slot_in(s, e["name"]) for s in e.get("slots", [])],
                validators=[_binding_in(b, e["name"]) for b in e.get("validators", [])],
                identity=tuple(_uuid(i, e["name"]) for i in e.get("identity", [])),
                indexes=tuple(
                    Index(tuple(_uuid(s, e["name"]) for s in i["slots"]), i["unique"]) for i in e.get("indexes", [])
                ),
                default_order=tuple(
                    OrderTerm(_uuid(o["slot"], e["name"]), o["ascending"]) for o in e.get("default_order", [])
                ),
            )
        )

    for s in raw.get("schemas", []):
        model.schemas.append(
            Schema(
                **_common(s),
                context=_opt_uuid(s.get("context"), s["name"]),
                members=tuple(_uuid(m, s["name"]) for m in s.get("members", [])),
                validators=[_schema_binding_in(b, s["name"]) for b in s.get("validators", [])],
            )
        )

    return model


def dump(model: Model) -> dict[str, Any]:
    version = needed_version(model)
    document: dict[str, Any] = {
        "schema_version": version,
        "library_version": model.library_version,
        "contexts": [
            {
                **_head_out(c),
                "parent": None if c.parent is None else str(c.parent),
                **_tail_out(c),
            }
            for c in model.contexts
        ],
        "validators": [
            {
                **_head_out(v),
                "context": None if v.context is None else str(v.context),
                "kind": v.kind,
                "parameters": list(v.parameters),
                "expression": v.expression,
                "message": v.message,
                **_tail_out(v),
            }
            for v in model.validators
        ],
        "interfaces": [
            {
                **_head_out(i),
                "context": None if i.context is None else str(i.context),
                "base_type": i.base_type,
                "picture": i.picture,
                "decimal_point": i.decimal_point,
                "group_mark": i.group_mark,
                "parse_lenient": i.parse_lenient,
                "blank": i.blank,
                **_tail_out(i),
            }
            for i in model.interfaces
        ],
        "types": [
            {
                **_head_out(t),
                "context": None if t.context is None else str(t.context),
                "parent": _type_ref_out(t.parent),
                "validators": [_binding_out(b) for b in t.validators],
                "interfaces": [
                    {
                        "uuid": str(b.uuid),
                        "interface": None if b.interface is None else str(b.interface),
                        "is_default": b.is_default,
                    }
                    for b in t.interfaces
                ],
                **_tail_out(t),
            }
            for t in model.types
        ],
        "properties": [
            {
                **_head_out(p),
                "context": None if p.context is None else str(p.context),
                "type": _type_ref_out(p.type),
                **_tail_out(p),
            }
            for p in model.properties
        ],
        "entities": [
            {
                **_head_out(e),
                "context": None if e.context is None else str(e.context),
                "abstract": e.abstract,
                "extends": None if e.extends is None else str(e.extends),
                "slots": [_slot_out(s) for s in e.slots],
                "validators": [_binding_out(b) for b in e.validators],
                "identity": [str(i) for i in e.identity],
                "indexes": [{"slots": [str(s) for s in i.slots], "unique": i.unique} for i in e.indexes],
                "default_order": [{"slot": str(o.slot), "ascending": o.ascending} for o in e.default_order],
                **_tail_out(e),
            }
            for e in model.entities
        ],
        "schemas": [
            {
                **_head_out(s),
                "context": None if s.context is None else str(s.context),
                "members": [str(m) for m in s.members],
                "validators": [_schema_binding_out(b) for b in s.validators],
                **_tail_out(s),
            }
            for s in model.schemas
        ],
    }
    if version < 2:
        # a document declaring version 1 must not contain version 2 keys:
        # the shape follows the declared version, or the file is lying
        # about itself and an older build would meet something it does not
        # know while being told it is safe
        document.pop("interfaces")
        for written in document["types"]:
            written.pop("interfaces")
    return document


def dumps(model: Model) -> str:
    return json.dumps(dump(model), indent=2) + "\n"


def save(model: Model, path: str | Path) -> None:
    Path(path).write_text(dumps(model))
