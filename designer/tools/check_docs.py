"""Check the documents against each other and against the code.

    python3 tools/check_docs.py

The specification and its appendices cross-reference constantly — sections,
diagnostic codes, validator names, file paths, counts — and nothing was
verifying any of it. The first run found six errors: a validator library that
still said "forty" after it grew to forty-four, a worked example described as
25 items across two contexts when it is 30 across three, two wrong test counts,
three diagnostic codes specified but not implemented and not marked as such,
and a `build_example.py` that both the notes and `make dist` referred to after
it had ceased to exist — with the failure swallowed by `2>/dev/null || true`.

Prose goes stale the way code does. The difference is that nothing runs it.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/designer-model/src"))

import designer_model as dm
from designer_model.codes import REGISTRY
from designer_model.stdlib import standard_library

DOCS = ROOT / "docs"
GONE_ON_PURPOSE = {
    "build_example.py",
    "designer-check.py",
    "designer-example-sales.json",
}
"""Named only in the notes that record their removal. Listing them here is how
a deliberate absence is told apart from a stale reference."""


def sections(text: str) -> set[str]:
    return set(re.findall(r"^#+\s+(?:§\s?)?(\d+(?:\.\d+)*)[.\s]", text, re.MULTILINE))


def main() -> int:
    docs = {p.name: p.read_text() for p in sorted(DOCS.glob("designer-*.md"))}
    if not docs:
        print("no documents found", file=sys.stderr)
        return 2
    prose = "\n".join(docs.values())
    known_sections = set().union(*(sections(t) for t in docs.values()))
    library = standard_library()
    model = dm.load(ROOT / "examples/sales.json")
    files = {p.name for p in ROOT.rglob("*") if p.is_file()}

    problems: list[str] = []

    for name, text in docs.items():
        for match in re.finditer(r"§\s?(\d+(?:\.\d+)*)", text):
            if match.group(1) not in known_sections:
                line = text[: match.start()].count("\n") + 1
                problems.append(
                    f"{name}:{line} §{match.group(1)} names no section anywhere"
                )

    # a code the documents name but the registry lacks has to say so where a
    # reader would look for it, which is the table rather than the prose
    table = [
        line
        for line in prose.splitlines()
        if re.match(r"\|\s*`(MOD|EXP|INT)\d{3}`", line)
    ]
    for code in sorted(
        set(re.findall(r"\b((?:MOD|EXP|INT)\d{3})\b", prose)) - set(REGISTRY)
    ):
        row = next((line for line in table if f"`{code}`" in line), "")
        if "not yet implemented" not in row:
            problems.append(
                f"{code} is documented but not in the registry, and its row does not say so"
            )

    catalogued = set(
        re.findall(
            r"^\|\s*`([a-z_][a-z0-9_]*)`\s*\|",
            docs.get("designer-validator-library.md", ""),
            re.MULTILINE,
        )
    )
    for missing in sorted(catalogued - set(library.names)):
        problems.append(
            f"the validator catalogue lists {missing}, which the library does not have"
        )
    for absent in sorted(set(library.names) - catalogued):
        problems.append(f"the library has {absent}, which the catalogue does not list")

    for name, text in docs.items():
        for match in re.finditer(r"`([\w./-]+\.(?:py|json|toml|ini))`", text):
            target = pathlib.Path(match.group(1)).name
            if (
                target in files
                or target in GONE_ON_PURPOSE
                or target.startswith("designer-spec")
            ):
                continue
            line = text[: match.start()].count("\n") + 1
            problems.append(
                f"{name}:{line} names {match.group(1)}, which does not exist"
            )

    # "forty validators" survived the library growing to forty-four, which is
    # exactly the kind of claim nobody re-reads
    words = {
        "forty": 40,
        "forty-four": 44,
        "two": 2,
        "three": 3,
        "four": 4,
        "eight": 8,
        "nine": 9,
    }
    for name, text in docs.items():
        for match in re.finditer(r"\b([a-z-]+|\d+)\s+(built-ins?|validators)\b", text):
            said = words.get(match.group(1), None)
            if said is None and match.group(1).isdigit():
                said = int(match.group(1))
            if said is not None and said != len(library.names):
                line = text[: match.start()].count("\n") + 1
                problems.append(
                    f"{name}:{line} says {match.group(0)!r}; the library has {len(library.names)}"
                )

    # HISTORY.md is appended by hand, and a hand that forgets is what put the
    # instruction at the top of it. Nothing here can know a turn is missing —
    # only the numbering can be checked, which catches a botched append.
    history = ROOT / "HISTORY.md"
    if history.exists():
        numbers = [
            int(n)
            for n in re.findall(r"^## (\d+)\.", history.read_text(), re.MULTILINE)
        ]
        expected = list(range(1, len(numbers) + 1))
        if numbers != expected:
            gaps = sorted(set(expected) - set(numbers))
            twice = sorted({n for n in numbers if numbers.count(n) > 1})
            problems.append(
                f"HISTORY.md numbering is not contiguous: missing {gaps}, repeated {twice}"
            )

    claim = re.search(r"(\d+) items across (\w+) Contexts", prose)
    if claim:
        words = {"two": 2, "three": 3, "four": 4}
        if int(claim.group(1)) != len(model.index()):
            problems.append(
                f"the example is described as {claim.group(1)} items; it has {len(model.index())}"
            )
        if words.get(claim.group(2)) != len(model.contexts):
            problems.append(
                f"the example is described as {claim.group(2)} contexts; it has {len(model.contexts)}"
            )

    if problems:
        print(f"{len(problems)} problem(s):")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(
        f"documents agree with the code: {len(docs)} documents, "
        f"{len(known_sections)} sections, {len(REGISTRY)} codes, "
        f"{len(library.names)} validators, {len(model.index())} example items"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
