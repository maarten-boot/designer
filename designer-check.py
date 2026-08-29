"""Check a Designer model document against the structural rules in the spec.

Not the full model check — no expression typing — but enough to prove the
worked example is internally consistent: references resolve, paths are
well-formed, narrowing is real, schemas are closed, identities exist.
"""

import json
import sys

BASE_TYPES = {"integer", "real", "decimal", "boolean", "string", "datetime", "date", "time"}
MAX_PATH = 4

doc = json.load(open(sys.argv[1]))

contexts = {c["uuid"]: c for c in doc["contexts"]}
validators = {v["uuid"]: v for v in doc["validators"]}
types = {t["uuid"]: t for t in doc["types"]}
properties = {p["uuid"]: p for p in doc["properties"]}
entities = {e["uuid"]: e for e in doc["entities"]}
schemas = {s["uuid"]: s for s in doc["schemas"]}

slots = {}
for e in entities.values():
    for s in e["slots"]:
        slots[s["uuid"]] = (e, s)

findings = []


def report(sev, code, msg):
    findings.append((sev, code, msg))


def ancestors(ctx_uuid):
    seen = []
    while ctx_uuid:
        seen.append(ctx_uuid)
        ctx_uuid = contexts[ctx_uuid]["parent"]
    return seen


def visible(item_ctx, from_ctx):
    return item_ctx in ancestors(from_ctx)


def base_type_of(type_ref, depth=0):
    """Resolve a Type reference to its BaseType, or None if incomplete."""
    if type_ref is None or depth > 32:
        return None
    if "base_type" in type_ref:
        return type_ref["base_type"]
    return base_type_of(types[type_ref["type"]]["parent"], depth + 1)


def type_chain(type_uuid):
    chain, cur, depth = [], type_uuid, 0
    while cur and depth < 32:
        chain.append(cur)
        parent = types[cur]["parent"]
        cur = parent["type"] if parent and "type" in parent else None
        depth += 1
    return chain


def effective_slots(entity_uuid, depth=0):
    """Parent slots first, then own; a same-named own slot overrides."""
    e = entities[entity_uuid]
    inherited = effective_slots(e["extends"], depth + 1) if e["extends"] and depth < 32 else []
    result = {s["slot_name"]: s for s in inherited}
    for s in e["slots"]:
        result[s["slot_name"]] = s
    return list(result.values())


def inherited_slot(entity_uuid, slot_name):
    e = entities[entity_uuid]
    if not e["extends"]:
        return None
    for s in effective_slots(e["extends"]):
        if s["slot_name"] == slot_name:
            return s
    return None


# --- references resolve -----------------------------------------------------
for t in types.values():
    if t["parent"] is None:
        report("incomplete", "MOD101", f"Type {t['name']} has no parent")
    elif "type" in t["parent"] and t["parent"]["type"] not in types:
        report("error", "MOD102", f"Type {t['name']} parent does not resolve")
    if base_type_of(t["parent"]) is None and t["parent"] is not None:
        report("error", "MOD103", f"Type {t['name']} chain reaches no BaseType")

for p in properties.values():
    if p["type"] is None:
        report("incomplete", "MOD104", f"Property {p['name']} has no type")

for e in entities.values():
    for s in e["slots"]:
        if s["kind"] == "value":
            assert s["property"] in properties, f"{e['name']}.{s['slot_name']} property missing"
            if s.get("type_override") and s["type_override"] not in types:
                report("error", "MOD105", f"{e['name']}.{s['slot_name']} override does not resolve")
        else:
            target = entities[s["target"]]
            if target["abstract"]:
                report("error", "MOD401", f"{e['name']}.{s['slot_name']} targets abstract {target['name']}")
            if not visible(target["context"], e["context"]):
                report("error", "MOD402", f"{e['name']}.{s['slot_name']} target not visible")

# --- identity, inherited ----------------------------------------------------
def effective_identity(entity_uuid, depth=0):
    e = entities[entity_uuid]
    if e["identity"]:
        return e["identity"]
    if e["extends"] and depth < 32:
        return effective_identity(e["extends"], depth + 1)
    return []


for e in entities.values():
    for s in e["slots"]:
        if s["kind"] == "reference":
            if not effective_identity(s["target"]):
                report("error", "MOD403", f"{e['name']}.{s['slot_name']} target has no identity")
    if not e["abstract"] and not effective_identity(e["uuid"]):
        report("incomplete", "MOD404", f"concrete Entity {e['name']} has no identity")

# --- narrowing --------------------------------------------------------------
for e in entities.values():
    for s in e["slots"]:
        base = inherited_slot(e["uuid"], s["slot_name"])
        if base is None:
            continue
        if base["kind"] != s["kind"]:
            report("error", "MOD411", f"{e['name']}.{s['slot_name']} changes slot kind")
        if base["required"] and not s["required"]:
            report("error", "MOD412", f"{e['name']}.{s['slot_name']} widens required true->false")
        if s["kind"] == "value":
            new = s.get("type_override") or (
                properties[s["property"]]["type"].get("type")
            )
            old = base.get("type_override") or (
                properties[base["property"]]["type"].get("type")
            )
            if new and old and new != old and old not in type_chain(new):
                report("error", "MOD413", f"{e['name']}.{s['slot_name']} widens rather than narrows")

# --- abstract entities ------------------------------------------------------
descendants = {}
for e in entities.values():
    if e["extends"]:
        descendants.setdefault(e["extends"], []).append(e["uuid"])


def has_concrete_descendant(uid):
    return any(
        not entities[d]["abstract"] or has_concrete_descendant(d) for d in descendants.get(uid, [])
    )


for e in entities.values():
    if e["abstract"] and not has_concrete_descendant(e["uuid"]):
        report("warning", "MOD421", f"abstract Entity {e['name']} has no concrete descendant")

# --- schemas ----------------------------------------------------------------
for sc in schemas.values():
    members = set(sc["members"])
    for m in sc["members"]:
        e = entities[m]
        if e["abstract"]:
            report("error", "MOD501", f"{sc['name']} has abstract member {e['name']}")
        if not visible(e["context"], sc["context"]):
            report("error", "MOD502", f"{sc['name']} member {e['name']} not visible")
    # closure
    for m in sc["members"]:
        for s in effective_slots(m):
            if s["kind"] == "reference" and s["target"] not in members:
                report(
                    "warning",
                    "MOD503",
                    f"{sc['name']} not closed: {entities[m]['name']}.{s['slot_name']}"
                    f" -> {entities[s['target']]['name']}",
                )
    # validators: anchors and paths
    for b in sc["validators"]:
        if b["anchor"] not in members:
            report("error", "MOD504", f"{sc['name']} anchor is not a member")
        for param, arg in b["arguments"].items():
            if "path" not in arg:
                continue
            path = arg["path"]
            if len(path) > MAX_PATH:
                report("error", "MOD505", f"{sc['name']} path for {param} exceeds {MAX_PATH} segments")
            cur = b["anchor"]
            for i, slot_uuid in enumerate(path):
                names = {s["uuid"]: s for s in effective_slots(cur)}
                if slot_uuid not in names:
                    report("error", "MOD506", f"{sc['name']} path for {param} does not resolve at step {i}")
                    break
                s = names[slot_uuid]
                last = i == len(path) - 1
                if last and s["kind"] != "value":
                    report("error", "MOD507", f"{sc['name']} path for {param} ends on a reference slot")
                if not last:
                    if s["kind"] != "reference":
                        report("error", "MOD508", f"{sc['name']} path for {param} traverses a value slot")
                        break
                    if s["target"] not in members:
                        report("error", "MOD509", f"{sc['name']} path for {param} leaves the schema")
                    cur = s["target"]

# --- names ------------------------------------------------------------------
seen = {}
for kind, coll in [("Type", types), ("Property", properties), ("Entity", entities),
                   ("Validator", validators), ("Schema", schemas), ("Context", contexts)]:
    for it in coll.values():
        key = (it.get("context"), kind, it["name"])
        if it["name"] and key in seen:
            report("error", "MOD301", f"duplicate {kind} name {it['name']}")
        seen[key] = it["uuid"]

# --- orphans ----------------------------------------------------------------
used_types = {p["type"].get("type") for p in properties.values() if p["type"]}
used_types |= {s.get("type_override") for e in entities.values() for s in e["slots"]}
used_types |= {t["parent"]["type"] for t in types.values() if t["parent"] and "type" in t["parent"]}
for t in types.values():
    if t["uuid"] not in used_types:
        report("info", "MOD601", f"Type {t['name']} is referenced by nothing")

# --- non-deterministic bindings ---------------------------------------------
NONDET = {"in_past", "in_future", "not_in_past", "not_in_future"}
import uuid as _uuid

NS = _uuid.uuid5(_uuid.NAMESPACE_DNS, "stdlib.designer")
nondet_uuids = {str(_uuid.uuid5(NS, n)) for n in NONDET}
for e in entities.values():
    for b in e["validators"]:
        if b["validator"] in nondet_uuids:
            report("warning", "MOD602", f"{e['name']} binds a non-deterministic validator; no CHECK constraint")
for t in types.values():
    for b in t["validators"]:
        if b["validator"] in nondet_uuids:
            report("warning", "MOD602", f"Type {t['name']} binds a non-deterministic validator")

order = {"error": 0, "warning": 1, "incomplete": 2, "info": 3}
for sev, code, msg in sorted(findings, key=lambda f: (order[f[0]], f[1])):
    print(f"{sev:11} {code}  {msg}")

errors = sum(1 for f in findings if f[0] == "error")
print(f"\n{len(findings)} finding(s), {errors} error(s)")
sys.exit(1 if errors else 0)
