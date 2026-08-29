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
