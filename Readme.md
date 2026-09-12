# Designer

## What

A datadictionary designer for multiple schema's and multiple context's

## Why

At the beginning of my professional career,
beng a member of an international team at the Würth company,
we build from scratch,
a framework for building business applications,
on Unix with C and SQL.

After a while building applications,
you start seeing paterns that repeat themselves over and over.
At that time many of the modern tools we currently take for granted did not exist.
We started with serial terminals and later around the beginning of the 90's started working with X11.

Seeing duplicate or similar definitions in the database with slightly different naming or definitions,
it occured to me that
a verifier or a single tool holding all definitions of column names and column definitions
would greatly increase the proper definition and use of tables and columns
and reduce redundancy and errors.

I started working on a sql schema extractor,
to compare and list all unique names and definitions used in all tables.
It never came to a real tool as i moved on to the next company.
As it turned out that was Uniface now at [Rocket®Software](https://www.rocketsoftware.com/en-us/products/uniface),
where most of the ideas i had developed during the work at Würth,
was already encoded as a 4GL application builder.

However the ideas stayed and percolated in to ideas of Contexts, Nodes, Attributes, Validators.

Now with the help of Claude
and the general notion that:
`anything you can describe properly with words`,
can be modeled into code,
I build the basic data-dicionary designer.

## How

The conversiation with claude can be found in the conversation [History](./designer/HISTORY.md) i had with Claude.
