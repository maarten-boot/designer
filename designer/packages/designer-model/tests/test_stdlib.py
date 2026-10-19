"""The standard library.

It ships as a JSON model fragment rather than as code (spec §5.7), so the first
thing to assert is that it really is one: the ordinary loader reads it, and it
round-trips like any other document.
"""

from __future__ import annotations

import pytest

from designer_model import dumps, load
from designer_model.ids import NAMESPACE_STDLIB, builtin_id, is_builtin_id
from designer_model.stdlib import DATA, operand_uuids, standard_library


@pytest.fixture
def library():
    return standard_library()


def test_it_is_an_ordinary_model_document() -> None:
    document = load(DATA)
    assert dumps(document) == DATA.read_text()


def test_built_ins_are_present(library) -> None:
    assert len(library) >= 40
    for name in ["max_length", "one_of", "in_past", "non_blank", "max_scale"]:
        assert library.by_name(name) is not None


def test_identifiers_are_derivable_not_assigned(library) -> None:
    """The same name resolves to the same UUID on every installation, which is
    what lets a model file reference a built-in it does not contain."""
    for name in library.names:
        assert library.by_name(name).uuid == builtin_id(name)


def test_built_ins_are_distinguishable_from_authored_items(library) -> None:
    for name in library.names:
        assert is_builtin_id(builtin_id(name))


def test_namespace_is_stable() -> None:
    """These two values are the contract. If either changes, every model file
    referencing a built-in breaks, so they are pinned rather than recomputed."""
    assert str(NAMESPACE_STDLIB) == "ca5c92d9-7292-5f29-b793-8365eae7b1c3"
    assert str(builtin_id("max_length")) == "b5bfc6ca-adeb-523c-8b84-ec070bb68290"


def test_built_ins_have_no_context(library) -> None:
    """Global, like BaseTypes: visible everywhere, owned by no namespace."""
    for name in library.names:
        assert library.by_name(name).context is None


def test_temporal_built_ins_are_not_deterministic(library) -> None:
    for name in ["in_past", "in_future", "not_in_past", "not_in_future"]:
        assert not library.is_deterministic(builtin_id(name))


def test_ordinary_built_ins_are_deterministic(library) -> None:
    for name in ["max_length", "one_of", "positive", "is_email"]:
        assert library.is_deterministic(builtin_id(name))


def test_composites_store_operands_as_uuids(library) -> None:
    non_blank = library.by_name("non_blank")
    assert non_blank.is_composite
    assert "non_empty" not in non_blank.expression
    assert set(operand_uuids(non_blank.expression)) == {
        builtin_id("non_empty"),
        builtin_id("trimmed"),
    }


def test_composite_inherits_a_parameter(library) -> None:
    """is_safe_identifier carries max_length's parameter, which is the
    union-of-operands rule doing something useful."""
    assert library.by_name("is_safe_identifier").parameters == ("max",)


def test_temporal_built_ins_use_current(library) -> None:
    """One expression, polymorphic over date and datetime through unification,
    rather than two validators or a dispatch rule (spec §5.7)."""
    assert library.by_name("in_past").expression == "value < current()"


def test_regex_patterns_are_literals(library) -> None:
    """The pattern must be a literal so it compiles at authoring time."""
    for name in ["is_email", "is_url", "is_uuid", "is_country_code", "is_identifier"]:
        assert '"' in library.by_name(name).expression


def test_every_built_in_has_a_message(library) -> None:
    for name in library.names:
        assert library.by_name(name).message
        assert library.by_name(name).description


# --- deprecation (spec §5.7) -------------------------------------------------


def _with_deprecated(name: str, replacement: str | None = None, reason: str = ""):
    """The shipped library, with one built-in deprecated — nothing is yet."""
    from designer_model.stdlib import Deprecation, Library

    shipped = standard_library()
    validators = [shipped.by_name(n) for n in shipped.names]
    marked = Deprecation(since=2, replacement=builtin_id(replacement) if replacement else None, reason=reason)
    return Library(validators, 2, {builtin_id(name): marked})


def test_every_shipped_deprecation_names_a_built_in_and_a_live_replacement(library) -> None:
    for uuid, found in library.deprecations.items():
        assert uuid in library, f"{uuid} is deprecated but not a built-in"
        assert found.since <= library.version
        if found.replacement is not None:
            assert found.replacement in library
            assert found.replacement not in library.deprecated, "a replacement that is itself deprecated"


def test_a_deprecated_built_in_still_resolves() -> None:
    library = _with_deprecated("is_uuid")
    assert library.by_name("is_uuid") is not None
    assert library.get(builtin_id("is_uuid")) is not None


def test_pickers_leave_it_out_unless_it_is_already_chosen() -> None:
    library = _with_deprecated("is_uuid")
    assert "is_uuid" not in library.offered()
    assert "is_uuid" in library.offered(keep=builtin_id("is_uuid"))
    assert len(library.offered()) == len(library) - 1


def test_the_advice_says_since_when_what_instead_and_why() -> None:
    library = _with_deprecated("is_uuid", "is_email", "a bad example")
    assert library.advice(builtin_id("is_uuid")) == "since library v2; use is_email instead; a bad example"
    assert library.advice(builtin_id("is_email")) == ""


def test_using_one_is_a_note_with_the_advice() -> None:
    from designer_model.check import check
    from designer_model.codes import definition
    from designer_model.diagnostics import Severity, render

    model = load(DATA.parents[5] / "examples" / "sales.json")
    library = _with_deprecated("max_length", "is_email")
    findings = [f for f in check(model, library).findings if f.code == "LIB102"]
    assert len(findings) == 1  # ShortText binds it
    assert definition("LIB102").severity is Severity.INFO
    names = {i.uuid: i.name for i in model.index().values()} | {builtin_id("max_length"): "max_length"}
    message = render(definition("LIB102").template, findings[0].args, names)
    assert message.endswith("which is deprecated (since library v2; use is_email instead)")


def test_a_composite_operand_counts_as_a_use() -> None:
    from designer_model.check import check

    model = load(DATA.parents[5] / "examples" / "sales.json")
    library = _with_deprecated("is_uuid")  # order_reference is is_order_number OR is_uuid
    subjects = {str(f.subject) for f in check(model, library).findings if f.code == "LIB102"}
    assert any("expression" in s for s in subjects)


def test_a_deprecated_built_in_does_not_block_export() -> None:
    from designer_model.export import export_schema

    model = load(DATA.parents[5] / "examples" / "sales.json")
    schema = next(s for s in model.schemas if s.name == "sales_schema")
    export_schema(model, schema.uuid, _with_deprecated("max_length"))


# --- every built-in against its own examples (validator library §9) ----------

EXAMPLES = DATA.with_name("examples.json")


def _examples() -> dict:
    import json

    return json.loads(EXAMPLES.read_text())["examples"]


def _verdict(library, validator, value, arguments) -> bool:
    from designer_model.expressions.evaluate import evaluate_composite, evaluate_leaf

    if not validator.is_composite:
        return evaluate_leaf(validator.expression, value, arguments)
    return evaluate_composite(validator.expression, lambda u: _verdict(library, library.get(u), value, arguments))


def test_every_built_in_has_examples(library) -> None:
    assert set(_examples()) == library.names


@pytest.mark.parametrize("name", sorted(_examples()))
def test_a_built_in_passes_and_fails_its_examples(library, name) -> None:
    from designer_model.literals import ListLiteral, decode

    def plain(raw):
        # infinity and NaN are what is_finite is for, and what a model file
        # refuses; this file is test data, so they are read as they are
        if (isinstance(raw.get("real"), float) and raw["real"] != raw["real"]) or raw.get("real") in (
            float("inf"),
            float("-inf"),
        ):
            return raw["real"]
        literal = decode(raw)
        return list(literal.values) if isinstance(literal, ListLiteral) else literal.value

    entry = _examples()[name]
    validator = library.by_name(name)
    arguments = {k: plain(v) for k, v in entry["arguments"].items()}
    for raw in entry["pass"]:
        assert _verdict(library, validator, plain(raw), arguments), f"{name} refused {raw}"
    for raw in entry["fail"]:
        assert not _verdict(library, validator, plain(raw), arguments), f"{name} admitted {raw}"


def test_a_built_in_from_a_newer_library_names_the_version_needed() -> None:
    from uuid import uuid4

    from designer_model.check import check
    from designer_model.codes import definition
    from designer_model.diagnostics import render
    from designer_model.model import Binding

    model = load(DATA.parents[5] / "examples" / "sales.json")
    model.library_version = 3
    item = next(t for t in model.types if t.name == "ShortText")
    item.validators.append(Binding(uuid=uuid4(), validator=builtin_id("is_iban")))  # not in v1
    (finding,) = [f for f in check(model).findings if f.code == "LIB101"]
    text = render(definition("LIB101").template, finding.args, {item.uuid: "ShortText"})
    assert text.endswith("the model needs standard library v3, this is v1")
