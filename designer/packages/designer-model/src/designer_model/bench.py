"""The test bench: try a value against a Type (spec §15).

Somebody types what a person would type. It is read the way the application
would read it — through the Type's Interface when it has one, otherwise as a
literal of its base type — and then every rule along the Type's chain says
whether it passes, and why not when it does not.

Reading and validating are kept apart, because they fail differently (appendix
*interfaces* §6): "that is not a date" is not "that date is in the future". Text
that cannot be read has no value to validate, and the bench says so instead of
running the rules against nothing.

Evaluation runs in a separate process. A pattern can backtrack catastrophically,
Python's `re` has no timeout and does not release the interpreter while it
matches, so a thread would freeze the window just the same; a process can be
stopped. `start` returns a `Job` the window polls; `run` waits for one.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from .derive import Deriver
from .expressions.evaluate import EvaluationError, evaluate_composite, evaluate_leaf
from .literals import ListLiteral, Literal, _decode_datetime
from .model import Binding, LiteralArg, Model, Validator
from .persistence import dump, load
from .pictures import ParseError, PictureError, compile_picture, parse, readable
from .stdlib import Library, standard_library

TIMEOUT = 2.0
"""Seconds before a trial is stopped. Every built-in answers in microseconds;
anything near this is a pattern that will not finish."""

PASS, FAIL, UNANSWERED = "pass", "fail", "cannot say"


class ReadError(ValueError):
    """Text that cannot be read as a value of the Type."""


@dataclass(frozen=True, slots=True)
class Verdict:
    rule: str
    origin: str
    outcome: str
    detail: str = ""
    """Why it failed, in the rule's own message, or why it could not say."""
    operands: tuple[Verdict, ...] = ()


@dataclass(frozen=True, slots=True)
class Trial:
    text: str
    read_as: str
    """How the text was read: through which Interface, or as which base type."""
    value: str = ""
    """The value it was read as, written plainly."""
    unreadable: str = ""
    verdicts: tuple[Verdict, ...] = ()
    stopped: str = ""
    """Set when the bench itself gave no answer: a timeout, or a failure."""

    @property
    def admitted(self) -> bool | None:
        """Yes, no, or — when a rule could not answer and none failed — unknown."""
        if self.unreadable or self.stopped:
            return None
        outcomes = {v.outcome for v in self.verdicts}
        if FAIL in outcomes:
            return False
        return None if UNANSWERED in outcomes else True

    @property
    def summary(self) -> str:
        if self.stopped:
            return self.stopped
        if self.unreadable:
            return f"{self.text!r} cannot be read {self.read_as}: {self.unreadable}"
        verdict = {True: "admits it", False: "refuses it", None: "cannot say for every rule"}[self.admitted]
        failed = sum(v.outcome == FAIL for v in self.verdicts)
        tail = f" — {failed} of {len(self.verdicts)} rules fail" if failed else ""
        return f"read {self.read_as}: {self.value} — the type {verdict}{tail}"


# --- reading -------------------------------------------------------------------


def _read_literal(base: str, text: str) -> Any:
    """Text as a base-type literal, the way the model file writes one."""
    stripped = text.strip()
    try:
        if base == "string":
            return text
        if base == "integer":
            return int(stripped)
        if base == "decimal":
            return Decimal(stripped)
        if base == "real":
            return float(stripped)
        if base == "boolean":
            if stripped.lower() in {"true", "false"}:
                return stripped.lower() == "true"
            raise ValueError("expected true or false")
        if base == "date":
            return dt.date.fromisoformat(stripped)
        if base == "time":
            return dt.time.fromisoformat(stripped)
        if base == "datetime":
            return _decode_datetime(stripped)
    except InvalidOperation as error:
        raise ReadError(f"not a {base}") from error
    except ValueError as error:
        raise ReadError(str(error) or f"not a {base}") from error
    raise ReadError(f"unknown base type {base}")


def reading(model: Model, type_uuid: UUID) -> str:
    """How text is read for this Type: through its Interface, or as a literal."""
    d = Deriver(model)
    item = d.types.get(type_uuid)
    found = d.effective_interface(type_uuid)
    face = next((i for i in model.interfaces if found and i.uuid == found[0]), None)
    if face is not None:
        return f"with {face.name} ({face.picture})"
    base = d.base_type_of(item.parent) if item else None
    return f"as a {base}" if base else "as nothing yet"


def read(model: Model, type_uuid: UUID, text: str) -> tuple[Any, str]:
    """The value `text` means for this Type, and how it was read."""
    d = Deriver(model)
    item = d.types.get(type_uuid)
    base = d.base_type_of(item.parent) if item else None
    if base is None:
        raise ReadError("the type has no base type yet")
    found = d.effective_interface(type_uuid)
    face = next((i for i in model.interfaces if found and i.uuid == found[0]), None)
    if face is None:
        return _read_literal(base, text), reading(model, type_uuid)
    try:
        picture = compile_picture(face.base_type, face.picture, face.decimal_point, face.group_mark)
        return parse(picture, text, face.parse_lenient), reading(model, type_uuid)
    except PictureError as error:
        raise ReadError(f"its interface {face.name} has a picture that cannot be used: {error}") from error
    except ParseError as error:
        raise ReadError(str(error)) from error


# --- judging -------------------------------------------------------------------


def _plain(literal: Literal) -> Any:
    return list(literal.values) if isinstance(literal, ListLiteral) else literal.value


def _message(template: str, arguments: dict[str, Any]) -> str:
    shown = {k: ", ".join(map(str, v)) if isinstance(v, list) else v for k, v in arguments.items()}
    try:
        return template.format(**shown)
    except (KeyError, IndexError, ValueError):
        return template


class _Judge:
    def __init__(self, model: Model, library: Library) -> None:
        self.library = library
        self.authored = {v.uuid: v for v in model.validators}

    def validator(self, uuid: UUID | None) -> Validator | None:
        if uuid is None:
            return None
        return self.library.get(uuid) or self.authored.get(uuid)

    def verdict(self, validator: Validator, value: Any, arguments: dict, message: str | None, origin: str, depth=0):
        """One rule's answer, with each operand's for a composite."""
        failure = _message(message or validator.message, arguments)
        if depth > 16:
            return Verdict(validator.name, origin, UNANSWERED, "nested too deeply")
        if not validator.is_composite:
            try:
                passed = evaluate_leaf(validator.expression, value, arguments)
            except EvaluationError as error:
                return Verdict(validator.name, origin, UNANSWERED, str(error))
            return Verdict(validator.name, origin, PASS if passed else FAIL, "" if passed else failure)

        operands: list[Verdict] = []

        def answer(uuid: UUID) -> bool:
            found = self.validator(uuid)
            if found is None:
                operands.append(Verdict(str(uuid), origin, UNANSWERED, "does not exist"))
                raise EvaluationError("an operand does not exist")
            result = self.verdict(found, value, arguments, None, origin, depth + 1)
            operands.append(result)
            if result.outcome == UNANSWERED:
                raise EvaluationError(f"{found.name} cannot say")
            return result.outcome == PASS

        try:
            passed = evaluate_composite(validator.expression, answer)
        except EvaluationError as error:
            return Verdict(validator.name, origin, UNANSWERED, str(error), tuple(operands))
        if not passed and not (message or validator.message):
            # no message of its own: report the operands that failed (spec
            # §5.5), or — when a negation failed because an operand passed —
            # the operands that should not have
            failed = [o.detail or o.rule for o in operands if o.outcome == FAIL]
            failure = "; ".join(failed) or "must not: " + ", ".join(o.rule for o in operands if o.outcome == PASS)
        return Verdict(validator.name, origin, PASS if passed else FAIL, "" if passed else failure, tuple(operands))

    def binding(self, b: Binding, value: Any, origin: str) -> Verdict:
        validator = self.validator(b.validator)
        if validator is None:
            return Verdict("(no validator)", origin, UNANSWERED, "the rule names no validator that exists")
        arguments = {k: _plain(a.literal) for k, a in b.arguments.items() if isinstance(a, LiteralArg)}
        return self.verdict(validator, value, arguments, b.message, origin)


def try_value(model: Model, type_uuid: UUID, text: str, library: Library | None = None) -> Trial:
    """Read `text` for the Type and judge it by every rule along its chain,
    inherited rules first."""
    d = Deriver(model)
    try:
        value, how = read(model, type_uuid, text)
    except ReadError as error:
        return Trial(text, reading(model, type_uuid), unreadable=str(error))
    judge = _Judge(model, library if library is not None else standard_library())
    verdicts = tuple(
        judge.binding(b, value, d.types[uuid].name)
        for uuid in reversed(d.type_chain(type_uuid))
        if uuid in d.types
        for b in d.types[uuid].validators
    )
    return Trial(text, how, readable(value), verdicts=verdicts)


# --- off the window's thread -----------------------------------------------------


def _to_wire(trial: Trial) -> dict[str, Any]:
    return asdict(trial)


def _from_wire(raw: dict[str, Any]) -> Trial:
    def verdict(v: dict[str, Any]) -> Verdict:
        return Verdict(v["rule"], v["origin"], v["outcome"], v["detail"], tuple(verdict(o) for o in v["operands"]))

    return Trial(
        raw["text"],
        raw["read_as"],
        raw["value"],
        raw["unreadable"],
        tuple(verdict(v) for v in raw["verdicts"]),
        raw["stopped"],
    )


def _main() -> None:
    """The worker: a request on standard input, a Trial on standard output.

    Its own module run with `-m`, not a `multiprocessing` child, which would
    re-run the parent's main script first — the window's, or whatever launched
    it — and fail wherever that cannot be run twice. The model travels as the
    JSON the file format already defines, so nothing here needs pickle.
    """
    request = json.loads(sys.stdin.read())
    try:
        trial = try_value(load(request["model"]), UUID(request["type"]), request["text"])
    except Exception as error:  # anything at all: the window must hear back
        trial = Trial(request.get("text", ""), "", stopped=f"the bench failed: {type(error).__name__}: {error}")
    sys.stdout.write(json.dumps(_to_wire(trial)))


class Job:
    """A trial running in its own process, which `cancel` can stop."""

    def __init__(self, model: Model, type_uuid: UUID, text: str, timeout: float = TIMEOUT) -> None:
        self.text = text
        self._deadline = time.monotonic() + timeout
        source = str(pathlib.Path(__file__).resolve().parents[1])
        path = os.pathsep.join(filter(None, [source, os.environ.get("PYTHONPATH")]))
        self._process = subprocess.Popen(
            [sys.executable, "-m", "designer_model.bench"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONPATH": path},
        )
        request = json.dumps({"model": dump(model), "type": str(type_uuid), "text": text})
        self._answer: list[Trial] = []
        # the pipes are driven from a thread so the window never waits on them;
        # waiting on a pipe releases the interpreter, unlike a regex match
        self._reader = threading.Thread(target=self._exchange, args=(request,), daemon=True)
        self._reader.start()

    def _exchange(self, request: str) -> None:
        try:
            out, err = self._process.communicate(request.encode())
        except (OSError, ValueError):
            return
        if self._process.returncode == 0 and out:
            self._answer.append(_from_wire(json.loads(out)))
        elif self._process.returncode is not None and self._process.returncode > 0:
            last = err.decode(errors="replace").strip().splitlines()[-1:] or ["no reason given"]
            self._answer.append(Trial(self.text, "", stopped=f"the bench stopped: {last[0]}"))

    def poll(self) -> Trial | None:
        """The result once there is one; None while it is still running."""
        if self._answer:
            return self._answer[0]
        if self._reader.is_alive():
            return None
        return Trial(self.text, "", stopped="the bench stopped without an answer")

    @property
    def expired(self) -> bool:
        return time.monotonic() > self._deadline

    def cancel(self) -> None:
        if self._process.poll() is None:
            self._process.kill()
        self._reader.join(timeout=1)


def start(model: Model, type_uuid: UUID, text: str, timeout: float = TIMEOUT) -> Job:
    return Job(model, type_uuid, text, timeout)


def timed_out(text: str, timeout: float = TIMEOUT) -> Trial:
    return Trial(text, "", stopped=f"no answer within {timeout:g} s — a rule's pattern may never finish")


def run(model: Model, type_uuid: UUID, text: str, timeout: float = TIMEOUT) -> Trial:
    """Start a job and wait for it: for a caller with no event loop to return to."""
    job = start(model, type_uuid, text, timeout)
    while True:
        result = job.poll()
        if result is not None:
            return result
        if job.expired:
            job.cancel()
            return timed_out(text, timeout)
        time.sleep(0.01)


if __name__ == "__main__":
    _main()
