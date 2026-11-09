# Designer — appendix: the export as a tree of files

A Schema's export (spec §9.6), cut into one small file per table and per
column, for programs that generate applications from the model: they read what
they need, by path, without parsing the whole export. Built in turn 203, as the
first step of an idea from turn 202: serving the model to other programs. 9P
was considered and set aside for now: the readers are programs on Linux,
Windows and macOS, a snapshot is enough, and only Linux mounts 9P without
extra software. Files on a shared folder reach all three.

---

## 1. Use

    designer-export model.json sales_schema --tree out/sales_schema

`--tree DIR` takes the place of `-o`. The gate is the export's own: a Schema
that cannot be exported writes no tree. `examples/sales_schema.tree/` is the
worked example's, generated and compared byte for byte by the tests.

---

## 2. Layout

    schema.json
    tables/<table>/table.json
    tables/<table>/columns/<column>.json

- **`schema.json`** is the export's top level: `format`
  (`designer-schema-tree`) and `format_version` (1) of the tree, then
  `export_format` and `export_format_version` of the export it was cut from,
  then `source`, `schema`, `warnings`, `tables` and `application`, as in the
  export.
- **`table.json`** is the export's table object.
- **`<column>.json`** is the export's column object.

Each object is the export's own, unchanged, with one exception: where the
export lists tables or columns, the tree lists entries pointing at their files:

    {"name": "Customer", "uuid": "e0000000-…", "path": "tables/Customer/table.json"}

The lists keep the export's order, which a directory listing does not.
Putting every `path` back in place of its entry gives the export exactly, in
the same key order (`designer_model.tree.assemble`, checked by the tests on
all three example exports). Nothing in the tree is not in the export, and
nothing in the export is missing from the tree.

A column's `uuid` is its slot's, so an inherited column (`created_at` from
`Auditable`) has the same UUID in every table that has it. The path is unique,
and the pair of table UUID and column UUID is too.

---

## 3. Paths

**Follow `path`; never build it from `name`.** A name matches
`[A-Za-z_][A-Za-z0-9_]*` (spec §3), which every system accepts as a file name,
with two exceptions, and an item hit by either is written as `<name>~<uuid>`:

- **Names Windows reserves**: `CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`,
  `LPT1`–`LPT9`, in any case. Windows refuses them as file names even with an
  extension.
- **Names that differ only in case** among siblings, such as columns `Name` and
  `name`: Windows and macOS keep them in one file. Every one of them gets the
  UUID, not all but the first, so adding a second one does not rename the
  first.

Paths are relative to the tree's root, with `/` as the separator, which Windows
reads too. The longest path in the example is 48 characters, far from
Windows's 260, but a deep target folder adds to it.

**Encoding.** UTF-8, no byte-order mark, `\n` line ends on every system, two
spaces of indent, a final newline: the same bytes everywhere, so a tree
written on Windows diffs clean against one written on Linux.

---

## 4. Snapshots

- **Replaced whole.** The tree is written into a new folder beside the target,
  then swapped in with two renames. A program reading while it is written sees
  the old tree or the new, not a mixture, and a column deleted from the model
  leaves no file behind. If the swap fails, the old tree is put back.
- **Only a tree is replaced.** A target that exists must be empty or a tree
  (its `schema.json` says `designer-schema-tree`); anything else is refused
  (exit 2), and nothing in it is touched.
- **No timestamp**, as in the export: the same model gives the same tree.
- A reader holding a file open on Windows blocks the swap: the export then
  fails and leaves the old tree in place.

---

## 5. Not built

- **A server.** 9P, or HTTP serving the same tree, if programs need live data
  rather than a snapshot. The layout is meant to be what it would serve.
- **The model's own items** — Types, Validators, Interfaces as such, rather
  than as they land on columns. The export resolves them into the columns,
  which is what a generator needs first; a generator that wants a widget per
  Type would want them as files too.
- **A tree of every Schema at once.** One `--tree` per Schema for now.
- **Writing from the app.** The command only, like `designer-ddl`.
