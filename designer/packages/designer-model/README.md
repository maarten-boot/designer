# designer-model

The data model behind Designer, a tool for authoring a data dictionary: validation
rules, types, fields, record structures and the schemas that group them.

Standard library only and free of any interface. It loads and saves model files,
runs the model check, evaluates rules, and exports a Schema as a self-contained
JSON document. Two commands come with it:

    designer-check model.json [--level everything] [--json]
    designer-export model.json SCHEMA [-o schema.export.json]

The desktop application is `designer-app`. Documentation, the specification and
worked examples: https://github.com/maarten-boot/designer
