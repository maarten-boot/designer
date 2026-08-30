"""Attaching a rule to a Type or an Entity.

A binding names a Validator and supplies its arguments. What `value` is depends
on where the binding sits: a Type supplies its own base type, an Entity names
one of its slots. That difference decides what the dialog asks for, which is
why it is settled here rather than in the widget.

The parameter types are not guessed. `check_leaf` infers them from the
validator's own expression against the value it will be given, so `between` on
a decimal asks for two decimals and the same validator on a date asks for two
dates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from designer_model import Deriver, Model
from designer_model.commands import AddBinding, Command, Macro, RemoveBinding
from designer_model.expressions.infer import check_leaf
from designer_model.expressions.types import BASE_TYPES, UNKNOWN, ExprType, Scalar
from designer_model.model import Binding, Entity, LiteralArg, SlotArg, Type
from designer_model.stdlib import Library

from .slots import SlotError, parse_default


def base_of(kind: ExprType) -> str | None:
    """The base type a parameter wants, or None when nothing is known.

    Named rather than fetched with a default: `getattr(kind, "base", None)`
    silently returned None for every parameter, and the failure looked like a
    missing type rather than a wrong attribute.
    """
    return kind.name if isinstance(kind, Scalar) else None


VALUE = "value"


class BindingError(ValueError):
    """A binding that cannot be applied, with a reason worth showing."""


@dataclass
class BindingDraft:
    """What the dialog collected. Not yet a binding."""

    validator: UUID | None = None
    slot: UUID | None = None
    arguments: dict[str, str] = field(default_factory=dict)
    message: str = ""

    @classmethod
    def of(cls, binding: Binding) -> BindingDraft:
        supplied = {name: _as_text(argument) for name, argument in binding.arguments.items() if name != VALUE}
        chosen = binding.arguments.get(VALUE)
        return cls(
            validator=binding.validator,
            slot=chosen.slot if isinstance(chosen, SlotArg) else None,
            arguments=supplied,
            message=binding.message or "",
        )


def _as_text(argument) -> str:
    if isinstance(argument, LiteralArg):
        return str(getattr(argument.literal, "value", ""))
    return ""


# --- what a rule would be applied to -----------------------------------------


def value_type(model: Model, owner, draft: BindingDraft) -> ExprType:
    """The type `value` will have.

    UNKNOWN while the owner is unfinished, which is what keeps an incomplete
    item quiet rather than showering it with type errors it cannot yet fix.
    """
    deriver = Deriver(model)
    if isinstance(owner, Type):
        base = deriver.base_type_of(owner.parent)
        return Scalar(base) if base else UNKNOWN
    if draft.slot is None:
        return UNKNOWN
    slot = next((s for s in deriver.effective_slots(owner.uuid) if s.uuid == draft.slot), None)
    if slot is None or not slot.is_value:
        return UNKNOWN
    base = deriver.base_type_of(deriver.slot_type(slot))
    return Scalar(base) if base else UNKNOWN


def parameters_for(model: Model, library: Library, owner, draft: BindingDraft) -> dict[str, ExprType]:
    """Each parameter the chosen validator needs, and the type it needs.

    Inferred from the validator's own expression against the value it will be
    given, so the same validator asks for decimals here and dates there.
    """
    validator = _validator(model, library, draft.validator)
    if validator is None:
        return {}
    wanted: dict[str, ExprType] = {}
    for leaf in _leaves(model, library, validator):
        result = check_leaf(leaf.expression, value_type(model, owner, draft), tuple(leaf.parameters))
        for name, kind in result.parameters.items():
            if name != VALUE:
                wanted.setdefault(name, kind)
    return wanted


def _validator(model: Model, library: Library, uuid: UUID | None):
    if uuid is None:
        return None
    return library.get(uuid) or next((v for v in model.validators if v.uuid == uuid), None)


def _leaves(model: Model, library: Library, validator, depth: int = 0):
    """A composite is applied through its operands, so its arguments are
    theirs."""
    if validator is None or depth > 8:
        return
    if not validator.is_composite:
        yield validator
        return
    from designer_model.expressions.tokens import operand_uuids

    for operand in operand_uuids(validator.expression):
        yield from _leaves(model, library, _validator(model, library, operand), depth + 1)


def accepts(model: Model, library: Library, validator) -> tuple[str, ...]:
    """The base types a validator's expression will take.

    Derived, never declared. A validator does not have *a* base type:
    `max_length` takes only string, `non_negative` takes the three numeric
    ones, and `equals` takes all eight. Asking an author to pick one would
    either throw the polymorphism away or restate what the expression already
    decides — and then disagree with it.
    """
    if validator is None:
        return ()
    taken = []
    for base in BASE_TYPES:
        if all(
            not any(
                f.code.startswith("EXP")
                for f in check_leaf(leaf.expression, Scalar(base), tuple(leaf.parameters)).findings
            )
            for leaf in _leaves(model, library, validator)
        ):
            taken.append(base)
    return tuple(taken)


def fits(model: Model, library: Library, owner, draft: BindingDraft, candidate: UUID) -> bool:
    """Whether a validator can be applied to this value at all.

    A rule that cannot type-check against the value it would be given is not
    offered — the alternative is offering it and then reporting an error the
    user could not have avoided.
    """
    probe = BindingDraft(validator=candidate, slot=draft.slot)
    value = value_type(model, owner, probe)
    if value is UNKNOWN:
        return True  # nothing known to contradict
    validator = _validator(model, library, candidate)
    if validator is None:
        return False
    for leaf in _leaves(model, library, validator):
        result = check_leaf(leaf.expression, value, tuple(leaf.parameters))
        if any(f.code.startswith("EXP") for f in result.findings):
            return False
    return True


# --- checking a draft --------------------------------------------------------


def check(model: Model, library: Library, owner, draft: BindingDraft) -> None:
    if draft.validator is None:
        raise BindingError("choose a rule")
    if isinstance(owner, Entity) and draft.slot is None:
        raise BindingError("choose which slot the rule applies to")
    if not fits(model, library, owner, draft, draft.validator):
        raise BindingError("that rule cannot be applied to this value's type")
    for name, kind in parameters_for(model, library, owner, draft).items():
        text = draft.arguments.get(name, "").strip()
        if not text:
            continue  # an unsupplied argument is incomplete, not wrong
        try:
            parse_default(base_of(kind), text)
        except SlotError as error:
            raise BindingError(f"{name}: {error}") from error


def _arguments(model: Model, library: Library, owner, draft: BindingDraft) -> dict:
    built: dict[str, object] = {}
    if isinstance(owner, Entity) and draft.slot is not None:
        built[VALUE] = SlotArg(draft.slot)
    for name, kind in parameters_for(model, library, owner, draft).items():
        text = draft.arguments.get(name, "").strip()
        if not text:
            continue
        literal = parse_default(base_of(kind), text)
        if literal is not None:
            built[name] = LiteralArg(literal)
    return built


def add(model: Model, library: Library, owner, draft: BindingDraft) -> Command:
    check(model, library, owner, draft)
    binding = Binding(
        uuid=uuid4(),
        validator=draft.validator,
        arguments=_arguments(model, library, owner, draft),
        message=draft.message.strip() or None,
    )
    return AddBinding(owner.uuid, binding, label="add rule")


def edit(model: Model, library: Library, owner, binding: Binding, draft: BindingDraft) -> Command:
    """Replace rather than patch.

    A binding is small and its parts move together — changing the validator
    changes which arguments exist — so one step that swaps the whole thing is
    both simpler and a truer account of what the user did.
    """
    check(model, library, owner, draft)
    replacement = Binding(
        uuid=binding.uuid,
        validator=draft.validator,
        arguments=_arguments(model, library, owner, draft),
        message=draft.message.strip() or None,
    )
    index = owner.validators.index(binding)
    return Macro(
        "edit rule",
        [
            RemoveBinding(owner.uuid, binding, index=index),
            AddBinding(owner.uuid, replacement, index=index),
        ],
    )


def remove(owner, binding: Binding) -> Command:
    return RemoveBinding(owner.uuid, binding, index=owner.validators.index(binding), label="remove rule")


# --- describing one ----------------------------------------------------------


def describes(model: Model, library: Library, owner, binding: Binding) -> tuple[str, str, str]:
    """Name, what it applies to, and its arguments — one table row."""
    validator = _validator(model, library, binding.validator)
    name = validator.name if validator else "(none)"
    applies = ""
    chosen = binding.arguments.get(VALUE)
    if isinstance(chosen, SlotArg):
        slot = next((s for s in Deriver(model).effective_slots(owner.uuid) if s.uuid == chosen.slot), None)
        applies = slot.slot_name if slot else "(missing slot)"
    supplied = ", ".join(
        f"{name}={_as_text(argument)}" for name, argument in binding.arguments.items() if name != VALUE
    )
    return name, applies, supplied
