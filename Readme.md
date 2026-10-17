# Designer

## What

A data dictionary designer for multiple schemas and multiple contexts.

## Why

At the beginning of my professional career,
being a member of an international team at the Würth company,
we built from scratch
a framework for building business applications,
on Unix with C and SQL.

After a while building applications,
you start seeing patterns that repeat themselves over and over.
At that time many of the modern tools we currently take for granted did not exist.
We started with serial terminals and later, around the beginning of the 90's, started working with X11.

Seeing duplicate or similar definitions in the database with slightly different naming or definitions,
it occurred to me that
a verifier or a single tool holding all definitions of column names and column definitions
would greatly increase the proper definition and use of tables and columns
and reduce redundancy and errors.

I started working on an SQL schema extractor,
to compare and list all unique names and definitions used in all tables.
It never became a real tool as I moved on to the next company.
As it turned out that was Uniface, now at [Rocket®Software](https://www.rocketsoftware.com/en-us/products/uniface),
where most of the ideas I had developed during the work at Würth
were already encoded as a 4GL application builder.

However the ideas stayed and percolated into ideas of Contexts, Nodes, Attributes, Validators.

Now with the help of Claude
and the general notion that
`anything you can describe properly with words`
can be modeled into code,
I built the basic data dictionary designer in 2 days.

## How

For educational purposes, my beginner's conversation with Claude can be found in the conversation [History](./designer/HISTORY.md).
