"""Build the Designer worked example model document.

Built-in validator UUIDs are computed from the scheme in spec §5.7:
    NAMESPACE_STDLIB = uuid5(NAMESPACE_DNS, "stdlib.designer")
    builtin_uuid     = uuid5(NAMESPACE_STDLIB, canonical_name)
so the identifiers in the output are the real ones, not placeholders.
"""

import json
import uuid

NAMESPACE_STDLIB = uuid.uuid5(uuid.NAMESPACE_DNS, "stdlib.designer")


def builtin(name: str) -> str:
    return str(uuid.uuid5(NAMESPACE_STDLIB, name))


BUILTINS = {
    n: builtin(n)
    for n in [
        "max_length",
        "non_blank",
        "is_country_code",
        "is_uuid",
        "non_negative",
        "positive",
        "max_scale",
        "max_precision",
        "min_value",
        "equals",
        "in_past",
    ]
}

# Authored UUIDs are hand-assigned but well-formed v4s, grouped by kind so the
# document stays readable: c=context d=type f=property e=entity a=slot
# b=binding 7a=validator 5c=schema
C = "c0000000-0000-4000-8000-0000000000{:02d}"
D = "d0000000-0000-4000-8000-0000000000{:02d}"
F = "f0000000-0000-4000-8000-0000000000{:02d}"
E = "e0000000-0000-4000-8000-0000000000{:02d}"
A = "a0000000-0000-4000-8000-0000000000{:02d}"
B = "b0000000-0000-4000-8000-0000000000{:02d}"
V = "7a000000-0000-4000-8000-0000000000{:02d}"
S = "5c000000-0000-4000-8000-0000000000{:02d}"

# contexts
C_COMMON, C_SALES = C.format(1), C.format(2)

# authored validators
V_ORDER_NUMBER, V_ORDER_REF = V.format(1), V.format(2)

# types
D_UUID, D_SHORT_TEXT, D_COUNTRY, D_MONEY, D_POS_MONEY, D_WEIGHT, D_ORDER_NO = (
    D.format(i) for i in range(1, 8)
)

# properties
F_ID, F_NAME, F_COUNTRY, F_CREATED, F_AMOUNT, F_ORDER_NO, F_QUANTITY = (F.format(i) for i in range(1, 8))

# entities
E_AUDITABLE, E_CUSTOMER, E_ORDER, E_LINE_ITEM, E_ORDER_LINE = (E.format(i) for i in range(1, 6))

# slots
A_CREATED = A.format(1)
A_CUST_ID, A_CUST_NAME, A_CUST_COUNTRY = A.format(10), A.format(11), A.format(12)
A_ORD_NO, A_ORD_CUST, A_ORD_SHIPTO, A_ORD_TOTAL = (A.format(i) for i in range(20, 24))
A_LI_ID, A_LI_AMOUNT = A.format(30), A.format(31)
A_OL_AMOUNT, A_OL_ORDER, A_OL_QTY = A.format(40), A.format(41), A.format(42)

X_SALES = S.format(1)

T0 = "2026-08-20T09:00:00Z"
T1 = "2026-08-29T14:30:00Z"


def stamps():
    return {"created": T0, "modified": T1}


def lit(kind, value):
    return {"literal": {kind: value}}


def binding(uid, validator, arguments, message=None):
    b = {"uuid": uid, "validator": validator, "arguments": arguments}
    if message is not None:
        b["message"] = message
    return b


def value_slot(uid, name, prop, position, required=True, default=None, type_override=None):
    s = {
        "uuid": uid,
        "slot_name": name,
        "kind": "value",
        "required": required,
        "position": position,
        "property": prop,
    }
    if default is not None:
        s["default"] = default
    if type_override is not None:
        s["type_override"] = type_override
    return s


def ref_slot(uid, name, target, position, required=True, inverse_name=None, on_delete="restrict"):
    return {
        "uuid": uid,
        "slot_name": name,
        "kind": "reference",
        "required": required,
        "position": position,
        "target": target,
        "inverse_name": inverse_name,
        "on_delete": on_delete,
    }


doc = {
    "schema_version": 1,
    "library_version": 1,
    "contexts": [
        {
            "uuid": C_COMMON,
            "name": "common",
            "description": "Shared definitions available to every schema below.",
            "parent": None,
            **stamps(),
        },
        {
            "uuid": C_SALES,
            "name": "sales",
            "description": "The sales line of business.",
            "parent": C_COMMON,
            **stamps(),
        },
    ],
    "validators": [
        {
            "uuid": V_ORDER_NUMBER,
            "name": "is_order_number",
            "description": "Matches the printed order number format.",
            "context": C_SALES,
            "kind": "leaf",
            "parameters": [],
            "expression": 'regex_full_match(value, "ORD-[0-9]{6}")',
            "message": "must look like ORD-000123",
            **stamps(),
        },
        {
            "uuid": V_ORDER_REF,
            "name": "order_reference",
            "description": "Either a printed order number or an internal UUID.",
            "context": C_SALES,
            "kind": "composite",
            "parameters": [],
            # operands stored as UUIDs, displayed as names (spec §5.2)
            "expression": f"{V_ORDER_NUMBER} OR {BUILTINS['is_uuid']}",
            "message": "must be an order number or a UUID",
            **stamps(),
        },
    ],
    "types": [
        {
            "uuid": D_UUID,
            "name": "Uuid",
            "description": "A canonical UUID string.",
            "context": C_COMMON,
            "parent": {"base_type": "string"},
            "validators": [binding(B.format(1), BUILTINS["is_uuid"], {})],
            **stamps(),
        },
        {
            "uuid": D_SHORT_TEXT,
            "name": "ShortText",
            "description": "A single line of human text.",
            "context": C_COMMON,
            "parent": {"base_type": "string"},
            "validators": [
                binding(
                    B.format(2),
                    BUILTINS["max_length"],
                    {"max": lit("integer", 80)},
                    message="must be 80 characters or fewer",
                ),
                binding(B.format(3), BUILTINS["non_blank"], {}),
            ],
            **stamps(),
        },
        {
            "uuid": D_COUNTRY,
            "name": "CountryCode",
            "description": "ISO 3166-1 alpha-2 shape. Shape only, not membership.",
            "context": C_COMMON,
            "parent": {"base_type": "string"},
            "validators": [binding(B.format(4), BUILTINS["is_country_code"], {})],
            **stamps(),
        },
        {
            "uuid": D_MONEY,
            "name": "Money",
            "description": "A non-negative monetary amount.",
            "context": C_COMMON,
            "parent": {"base_type": "decimal"},
            "validators": [
                binding(B.format(5), BUILTINS["non_negative"], {}),
                binding(B.format(6), BUILTINS["max_scale"], {"s": lit("integer", 2)}),
                binding(B.format(7), BUILTINS["max_precision"], {"p": lit("integer", 12)}),
            ],
            **stamps(),
        },
        {
            "uuid": D_POS_MONEY,
            "name": "PositiveMoney",
            "description": "Money that must be greater than zero. Narrows Money.",
            "context": C_COMMON,
            "parent": {"type": D_MONEY},
            "validators": [binding(B.format(8), BUILTINS["positive"], {})],
            **stamps(),
        },
        {
            # deliberately incomplete: no parent yet (spec §3.1)
            "uuid": D_WEIGHT,
            "name": "Weight",
            "description": "Started but not finished — no parent chosen yet.",
            "context": C_COMMON,
            "parent": None,
            "validators": [],
            **stamps(),
        },
        {
            "uuid": D_ORDER_NO,
            "name": "OrderNumber",
            "description": "How an order is referred to on paper or in the system.",
            "context": C_SALES,
            "parent": {"base_type": "string"},
            "validators": [binding(B.format(9), V_ORDER_REF, {})],
            **stamps(),
        },
    ],
    "properties": [
        {
            "uuid": F_ID,
            "name": "id",
            "description": "Surrogate identifier.",
            "context": C_COMMON,
            "type": {"type": D_UUID},
            **stamps(),
        },
        {
            "uuid": F_NAME,
            "name": "name",
            "description": "Display name.",
            "context": C_COMMON,
            "type": {"type": D_SHORT_TEXT},
            **stamps(),
        },
        {
            "uuid": F_COUNTRY,
            "name": "country_code",
            "description": "A country, as an ISO code.",
            "context": C_COMMON,
            "type": {"type": D_COUNTRY},
            **stamps(),
        },
        {
            "uuid": F_CREATED,
            "name": "created_at",
            "description": "When the row was created. UTC.",
            "context": C_COMMON,
            "type": {"base_type": "datetime"},
            **stamps(),
        },
        {
            "uuid": F_AMOUNT,
            "name": "amount",
            "description": "A monetary amount.",
            "context": C_COMMON,
            "type": {"type": D_MONEY},
            **stamps(),
        },
        {
            "uuid": F_ORDER_NO,
            "name": "order_number",
            "description": "The order's own reference.",
            "context": C_SALES,
            "type": {"type": D_ORDER_NO},
            **stamps(),
        },
        {
            "uuid": F_QUANTITY,
            "name": "quantity",
            "description": "A count of units.",
            "context": C_SALES,
            "type": {"base_type": "integer"},
            **stamps(),
        },
    ],
    "entities": [
        {
            "uuid": E_AUDITABLE,
            "name": "Auditable",
            "description": "Abstract. Factors the creation stamp out of everything below.",
            "context": C_COMMON,
            "abstract": True,
            "extends": None,
            "slots": [value_slot(A_CREATED, "created_at", F_CREATED, 0)],
            # non-deterministic: no CHECK constraint can carry this (spec §5.7)
            "validators": [binding(B.format(20), BUILTINS["in_past"], {"value": {"slot": A_CREATED}})],
            "identity": [],
            "indexes": [],
            "default_order": [],
            **stamps(),
        },
        {
            "uuid": E_CUSTOMER,
            "name": "Customer",
            "description": "Someone who places orders. Lives in common so several schemas can use it.",
            "context": C_COMMON,
            "abstract": False,
            "extends": E_AUDITABLE,
            "slots": [
                value_slot(A_CUST_ID, "id", F_ID, 0),
                value_slot(A_CUST_NAME, "name", F_NAME, 1),
                value_slot(A_CUST_COUNTRY, "country_code", F_COUNTRY, 2),
            ],
            "validators": [],
            "identity": [A_CUST_ID],
            "indexes": [{"slots": [A_CUST_NAME], "unique": False}],
            "default_order": [{"slot": A_CUST_NAME, "ascending": True}],
            **stamps(),
        },
        {
            "uuid": E_ORDER,
            "name": "Order",
            "description": "A customer order.",
            "context": C_SALES,
            "abstract": False,
            "extends": E_AUDITABLE,
            "slots": [
                value_slot(A_ORD_NO, "order_number", F_ORDER_NO, 0),
                ref_slot(A_ORD_CUST, "customer", E_CUSTOMER, 1, inverse_name="orders", on_delete="restrict"),
                # slot_name overridden: the property is country_code, the slot is ship_to_country
                value_slot(A_ORD_SHIPTO, "ship_to_country", F_COUNTRY, 2),
                value_slot(A_ORD_TOTAL, "total", F_AMOUNT, 3, default=lit("decimal", "0.00")),
            ],
            "validators": [],
            "identity": [A_ORD_NO],
            "indexes": [{"slots": [A_ORD_NO], "unique": True}],
            "default_order": [{"slot": A_ORD_NO, "ascending": False}],
            **stamps(),
        },
        {
            "uuid": E_LINE_ITEM,
            "name": "LineItem",
            "description": "Abstract. Declares the identity its concrete descendants inherit.",
            "context": C_SALES,
            "abstract": True,
            "extends": E_AUDITABLE,
            "slots": [
                value_slot(A_LI_ID, "id", F_ID, 0),
                value_slot(A_LI_AMOUNT, "line_total", F_AMOUNT, 1, required=False),
            ],
            "validators": [],
            "identity": [A_LI_ID],
            "indexes": [],
            "default_order": [],
            **stamps(),
        },
        {
            "uuid": E_ORDER_LINE,
            "name": "OrderLine",
            "description": "One line of an order. Narrows the inherited line_total.",
            "context": C_SALES,
            "abstract": False,
            "extends": E_LINE_ITEM,
            "slots": [
                # narrowing override: same slot_name as the inherited slot,
                # Type narrowed Money -> PositiveMoney, required false -> true
                value_slot(A_OL_AMOUNT, "line_total", F_AMOUNT, 1, required=True, type_override=D_POS_MONEY),
                ref_slot(A_OL_ORDER, "order", E_ORDER, 2, inverse_name="lines", on_delete="cascade"),
                value_slot(A_OL_QTY, "quantity", F_QUANTITY, 3, default=lit("integer", 1)),
            ],
            "validators": [
                binding(
                    B.format(30),
                    BUILTINS["min_value"],
                    {"value": {"slot": A_OL_QTY}, "min": lit("integer", 1)},
                )
            ],
            "identity": [],
            "indexes": [],
            "default_order": [],
            **stamps(),
        },
    ],
    "schemas": [
        {
            "uuid": X_SALES,
            "name": "sales_schema",
            "description": "What ships as the sales database.",
            "context": C_SALES,
            "members": [E_CUSTOMER, E_ORDER, E_ORDER_LINE],
            "validators": [
                {
                    "uuid": B.format(40),
                    "validator": BUILTINS["equals"],
                    "anchor": E_ORDER_LINE,
                    "arguments": {
                        "value": {"path": [A_OL_ORDER, A_ORD_SHIPTO]},
                        "other": {"path": [A_OL_ORDER, A_ORD_CUST, A_CUST_COUNTRY]},
                    },
                    "message": "an order line must ship to the customer's own country",
                    "enforcement": "application",
                }
            ],
            **stamps(),
        }
    ],
}

with open("/mnt/user-data/outputs/designer-example-sales.json", "w") as fh:
    json.dump(doc, fh, indent=2)
    fh.write("\n")

print("built-in UUIDs used:")
for name, uid in sorted(BUILTINS.items()):
    print(f"  {name:16} {uid}")
