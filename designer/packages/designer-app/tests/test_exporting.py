"""File ▸ Export schema…, without a window.

Which Schema is meant, what the file is called, and what a blocked export
shows are decided in `exporting.py`; the window only asks for a filename.
"""

from __future__ import annotations

import pathlib

import pytest
from designer_model import load
from designer_model.export import dumps, export_schema
from designer_model.stdlib import standard_library

from designer_app import exporting
from designer_app.selection import Selection

EXAMPLES = pathlib.Path(__file__).resolve().parents[3] / "examples"
EXAMPLE = EXAMPLES / "sales.json"


@pytest.fixture
def model():
    return load(EXAMPLE)


def named(items, name):
    return next(i for i in items if i.name == name)


def test_the_selected_schema_is_the_one_exported(model):
    support = named(model.schemas, "support_schema")
    assert exporting.schema_for_export(model, Selection(schema=support.uuid)) is support


def test_with_several_schemas_and_none_selected_there_is_no_guess(model):
    assert exporting.schema_for_export(model, Selection()) is None


def test_the_only_schema_needs_no_selection(model):
    model.schemas = model.schemas[:1]
    assert exporting.schema_for_export(model, Selection()) is model.schemas[0]


def test_a_selection_that_no_longer_exists_is_not_used(model):
    from uuid import uuid4

    assert exporting.schema_for_export(model, Selection(schema=uuid4())) is None


def test_the_file_is_suggested_beside_the_model(model):
    schema = named(model.schemas, "sales_schema")
    assert exporting.suggested_path(schema, EXAMPLE) == EXAMPLES / "sales_schema.export.json"
    assert exporting.suggested_path(schema, None) == pathlib.Path("sales_schema.export.json")


def test_an_export_is_the_exporters_own_text(model):
    schema = named(model.schemas, "sales_schema")
    outcome = exporting.run(model, schema, standard_library())
    assert outcome.text == dumps(export_schema(model, schema.uuid))
    assert outcome.text == (EXAMPLES / "sales_schema.export.json").read_text()
    assert outcome.blockers == []


def test_a_blocked_export_lists_what_blocks_it(model):
    schema = named(model.schemas, "sales_schema")
    schema.members = tuple(m for m in schema.members if m != named(model.entities, "Customer").uuid)
    outcome = exporting.run(model, schema, standard_library())
    assert outcome.text is None
    # the schema rule's path runs through order.customer, so MOD509 joins in
    assert {row.code for row in outcome.blockers} == {"MOD503", "MOD509"}
    assert all(row.blocks_export for row in outcome.blockers)
    assert outcome.headline == "2 findings block the export of sales_schema"


def test_one_blocker_is_counted_in_the_singular(model):
    from uuid import uuid4

    from designer_model.ids import builtin_id
    from designer_model.model import Binding

    named(model.types, "CountryCode").validators.append(Binding(uuid=uuid4(), validator=builtin_id("max_length")))
    outcome = exporting.run(model, named(model.schemas, "sales_schema"), standard_library())
    assert outcome.headline == "1 finding blocks the export of sales_schema"
