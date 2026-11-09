# designer-ddl

SQL table definitions from a Designer schema export: PostgreSQL, MariaDB or
SQLite.

    designer-export model.json SCHEMA -o schema.export.json
    designer-ddl schema.export.json --dialect postgresql -o schema.sql

Each rule of the model becomes a named CHECK constraint where the database can
say exactly what the rule says. Where it cannot, the rule is left as a comment
marked `NOT ENFORCED HERE`, with the reason, and listed in the report on
standard error: enforce it in the application. Standard library only.

Documentation: https://github.com/maarten-boot/designer (appendix *ddl*).
