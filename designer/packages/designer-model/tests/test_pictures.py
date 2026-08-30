"""Presenting a value, and reading one back.

The law under test throughout: `parse(present(v)) == v` for every value the
type admits. Most picture mistakes are failures of it, and they are invisible
until somebody's total changes by a penny.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from designer_model import pictures as p


def shown(base: str, picture: str, value) -> str:
    return p.present(p.compile_picture(base, picture), value)


def back(base: str, picture: str, text: str, lenient: bool = True):
    return p.parse(p.compile_picture(base, picture), text, lenient)


# --- numbers -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("picture", "value", "expected"),
    [
        ("#,##0.00", Decimal("1234.5"), "1,234.50"),
        ("#,##0.00", Decimal("0"), "0.00"),
        ("#,##0.##", Decimal("1234.5"), "1,234.5"),
        ("0.00", Decimal("-3.5"), "-3.50"),
        ("+0.00", Decimal("3.5"), "+3.50"),
        ("#,##0", Decimal("1234567"), "1,234,567"),
    ],
)
def test_a_number_presents_as_written(picture, value, expected) -> None:
    assert shown("decimal", picture, value) == expected


def test_zeroes_pad_and_hashes_do_not() -> None:
    assert shown("integer", "0000", 42) == "0042"
    assert shown("integer", "####", 42) == "42"


def test_a_negative_picture_is_the_same_number_in_brackets() -> None:
    assert shown("decimal", "#,##0.00;(#,##0.00)", Decimal("-12")) == "(12.00)"
    assert shown("decimal", "#,##0.00;(#,##0.00)", Decimal("12")) == "12.00"


def test_a_percentage_is_stored_as_a_fraction() -> None:
    assert shown("decimal", "0.0%", Decimal("0.075")) == "7.5%"
    assert back("decimal", "0.0%", "7.5%") == Decimal("0.075")


def test_a_percentage_needs_a_decimal_or_a_real() -> None:
    """On an integer the smallest step is 100%, so 7.5% is unreachable and the
    picture is always a mistake."""
    with pytest.raises(p.PictureError, match="not an integer"):
        p.compile_picture("integer", "0%")


def test_an_integer_picture_has_no_decimal_places() -> None:
    with pytest.raises(p.PictureError, match="decimal places"):
        p.compile_picture("integer", "0.00")


def test_nonsense_is_refused_when_the_picture_is_written() -> None:
    for picture in ("", "abc", "0.0.0", "#,#0,"):
        with pytest.raises(p.PictureError):
            p.compile_picture("decimal", picture)


def test_a_number_reads_back() -> None:
    assert back("decimal", "#,##0.00", "1,234.50") == Decimal("1234.50")
    assert back("integer", "0000", "0042") == 42
    assert back("real", "0.00", "3.50") == 3.5


def test_reading_back_tolerates_what_cannot_change_the_value() -> None:
    """Leniently: surrounding space, and a missing grouping separator."""
    assert back("decimal", "#,##0.00", "  1234.50  ") == Decimal("1234.50")
    assert back("decimal", "#,##0.00", "1234.50") == Decimal("1234.50")


def test_strict_reading_wants_the_separators() -> None:
    with pytest.raises(p.ParseError, match="grouping"):
        back("decimal", "#,##0.00", "1234.50", lenient=False)


def test_text_that_is_not_a_number_is_unreadable() -> None:
    """Not a validation failure: there is no value to validate, which is a
    different thing to tell somebody."""
    with pytest.raises(p.ParseError):
        back("decimal", "0.00", "half past three")


def test_a_fraction_is_refused_where_a_whole_number_is_written() -> None:
    with pytest.raises(p.ParseError, match="whole number"):
        back("integer", "0000", "12.5")


# --- strings -----------------------------------------------------------------


def test_a_string_is_padded_to_its_positions() -> None:
    assert shown("string", "X(10)<", "Ada") == "Ada       "
    assert shown("string", "X(10)>", "Ada") == "       Ada"
    assert shown("string", "X(5)^", "Ada") == " Ada "


def test_case_is_applied_on_the_way_out() -> None:
    assert shown("string", "X(3)U", "gbp") == "GBP"
    assert shown("string", "X(3)L", "GBP") == "gbp"


def test_a_long_value_is_never_cut() -> None:
    """The positions are a hint about width; an application may scroll. A
    length meant to be a limit is a rule."""
    assert shown("string", "X(3)<", "Ada Lovelace") == "Ada Lovelace"


def test_a_string_picture_must_be_a_string_picture() -> None:
    with pytest.raises(p.PictureError, match="X\\(n\\)"):
        p.compile_picture("string", "#,##0.00")


# --- dates and times ---------------------------------------------------------


def test_a_date_presents_in_the_order_written() -> None:
    day = dt.date(2026, 8, 30)
    assert shown("date", "dd-MM-yyyy", day) == "30-08-2026"
    assert shown("date", "yyyy-MM-dd", day) == "2026-08-30"


def test_the_order_is_the_whole_point() -> None:
    """`01-02-2026` is 1 February or 2 January depending on the picture, and no
    database schema records which."""
    assert back("date", "dd-MM-yyyy", "01-02-2026") == dt.date(2026, 2, 1)
    assert back("date", "MM-dd-yyyy", "01-02-2026") == dt.date(2026, 1, 2)


def test_quoted_text_is_literal() -> None:
    moment = dt.datetime(2026, 8, 30, 14, 22, 5, tzinfo=dt.UTC)
    assert shown("datetime", "yyyy-MM-dd'T'HH:mm:ss", moment) == "2026-08-30T14:22:05"


def test_an_offset_presents_and_reads_back() -> None:
    moment = dt.datetime(2026, 8, 30, 14, 22, 5, tzinfo=dt.UTC)
    text = shown("datetime", "yyyy-MM-dd'T'HH:mm:ssZZ", moment)
    assert text.endswith("+00:00")
    assert back("datetime", "yyyy-MM-dd'T'HH:mm:ssZZ", text) == moment


def test_an_offset_is_converted_to_utc() -> None:
    """The model carries no local zone, and inventing one here would put a rule
    about time in the presentation layer."""
    read = back("datetime", "yyyy-MM-dd'T'HH:mm:ssZZ", "2026-08-30T16:22:05+02:00")
    assert read == dt.datetime(2026, 8, 30, 14, 22, 5, tzinfo=dt.UTC)


def test_a_field_of_another_type_is_refused() -> None:
    with pytest.raises(p.PictureError, match="not a field of date"):
        p.compile_picture("date", "yyyy-MM-dd HH:mm")


def test_a_field_twice_is_refused() -> None:
    with pytest.raises(p.PictureError, match="twice"):
        p.compile_picture("date", "dd-dd-yyyy")


def test_unreadable_text_says_what_it_wanted() -> None:
    with pytest.raises(p.ParseError, match="expected"):
        back("date", "dd-MM-yyyy", "30/08/2026")


def test_an_impossible_date_is_unreadable() -> None:
    with pytest.raises(p.ParseError):
        back("date", "dd-MM-yyyy", "31-02-2026")


# --- booleans ----------------------------------------------------------------


def test_a_boolean_is_two_labels() -> None:
    assert shown("boolean", "Yes;No", True) == "Yes"
    assert shown("boolean", "Yes;No", False) == "No"
    assert back("boolean", "Yes;No", "No") is False


def test_boolean_labels_read_back_in_any_case_leniently() -> None:
    assert back("boolean", "Yes;No", "yes") is True


def test_two_identical_labels_are_refused() -> None:
    """The value could not be read back."""
    with pytest.raises(p.PictureError, match="must differ"):
        p.compile_picture("boolean", "Same;Same")


# --- the law -----------------------------------------------------------------


def test_the_round_trip_holds_for_a_sound_pairing() -> None:
    picture = p.compile_picture("decimal", "#,##0.00")
    assert p.check_round_trip(picture, [Decimal("0.00"), Decimal("-12.30")]).holds


def test_rounding_on_the_way_out_is_caught() -> None:
    """The commonest picture mistake, and invisible until a total changes."""
    result = p.check_round_trip(p.compile_picture("decimal", "#,##0.00"), [Decimal("1234.5678")])
    assert not result.holds
    assert "1,234.57" in result.why()


def test_a_case_changing_picture_is_lossy_unless_the_type_says_otherwise() -> None:
    """Reversibility is quantified over the values the Type admits: `X(3)U` is
    sound on a Type with `is_uppercase` and lossy without it. Neither the
    picture nor the rules are at fault — the pair is."""
    picture = p.compile_picture("string", "X(3)U")
    assert not p.check_round_trip(picture, ["gbp"]).holds
    assert p.check_round_trip(picture, ["GBP", "USD"]).holds


def test_padding_is_lossy_for_a_value_with_its_own_spaces() -> None:
    picture = p.compile_picture("string", "X(6)<")
    assert not p.check_round_trip(picture, [" ada "]).holds
    assert p.check_round_trip(picture, ["ada"]).holds


def test_an_absent_value_presents_as_nothing() -> None:
    assert p.present(p.compile_picture("decimal", "0.00"), None) == ""


# --- regional separators -----------------------------------------------------


@pytest.mark.parametrize(
    ("label", "decimal_point", "group_mark", "expected"),
    [
        ("UK and US", ".", ",", "1,234,567.50"),
        ("Germany", ",", ".", "1.234.567,50"),
        ("France", ",", " ", "1 234 567,50"),
        ("Switzerland", ".", "'", "1'234'567.50"),
    ],
)
def test_one_picture_serves_every_region(label, decimal_point, group_mark, expected) -> None:
    """The structure — grouped by three, two decimals — is the same everywhere.
    Only the two characters differ, so only they are configured."""
    picture = p.compile_picture("decimal", "#,##0.00", decimal_point, group_mark)
    assert p.present(picture, Decimal("1234567.5")) == expected


@pytest.mark.parametrize(
    ("decimal_point", "group_mark"),
    [(".", ","), (",", "."), (",", " "), (".", "'")],
)
def test_every_region_reads_its_own_writing_back(decimal_point, group_mark) -> None:
    picture = p.compile_picture("decimal", "#,##0.00", decimal_point, group_mark)
    assert p.check_round_trip(picture, [Decimal("1234567.50"), Decimal("-0.05")]).holds


def test_the_picture_itself_stays_canonical() -> None:
    """Written literally, `#,##0` and `0,00` would be indistinguishable, and the
    rule needed to tell them apart gets `#,##0` wrong."""
    german = p.compile_picture("decimal", "#,##0.00", ",", ".")
    assert german.text == "#,##0.00"
    assert german.maximum_decimals == 2
    assert german.grouping == 3


def test_a_german_number_reads_back_as_itself() -> None:
    picture = p.compile_picture("decimal", "#,##0.00", ",", ".")
    assert p.parse(picture, "1.234,50") == Decimal("1234.50")


def test_a_german_number_is_not_read_as_an_english_one() -> None:
    """`1.234` is one thousand two hundred and thirty-four, not 1.234."""
    picture = p.compile_picture("decimal", "#,##0.00", ",", ".")
    assert p.parse(picture, "1.234") == Decimal("1234")


def test_the_two_separators_must_differ() -> None:
    with pytest.raises(p.PictureError, match="must differ"):
        p.compile_picture("decimal", "#,##0.00", ".", ".")


def test_an_unusable_separator_is_refused() -> None:
    with pytest.raises(p.PictureError, match="not a decimal separator"):
        p.compile_picture("decimal", "0.00", "x", ",")


def test_grouping_may_show_nothing() -> None:
    picture = p.compile_picture("decimal", "#,##0.00", ".", "")
    assert p.present(picture, Decimal("1234.5")) == "1234.50"


def test_dates_need_no_such_setting() -> None:
    """A region writing `30/08/2026` writes a different picture: the separator
    there is literal text rather than a role."""
    assert shown("date", "dd/MM/yyyy", dt.date(2026, 8, 30)) == "30/08/2026"
    assert shown("date", "dd.MM.yyyy", dt.date(2026, 8, 30)) == "30.08.2026"
