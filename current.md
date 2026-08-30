Where things stand: 628 tests, everything green, and the editor is complete against the specification.
Every column exists, every item kind is editable, and no read-only summaries remain.

What's left, in the order I'd take it:

1. Schema export.
The deliverable, and the reason you raised it.
It's designed in outline but not built, and I still have four decisions outstanding from when you asked — you never confirmed them, and I shouldn't build on my own guesses.
They were: errors and incomplete items block while warnings don't; constraints resolved rather than referenced; one schema per file; JSON now with YAML as a serialiser swap.
The picture engine is ready to feed it.

2. The three interface checks.
`INT202`, `INT401`, `INT402` are specified and marked as not implemented.
`INT202` is the interesting one — the round trip over the values a Type actually admits, which is where we found `X(3)U` is sound with `is_uppercase` and lossy without.
Small, and it makes the picture engine's best idea real.

3. Phase 4 proper: the test bench (try a sample value against a Type and see which rules pass), the Preferences dialog, deprecation handling.

But my actual recommendation is none of those yet.

You said several turns ago you wanted to "start experimenting with building a test model", and then kept finding my bugs instead — the column widths, the breadcrumb, the log level, the built-in message.
Every one came from you using it, and each was a class of problem I couldn't have found by reasoning.
The tool is now complete enough to model something real.

Build a model of something you actually need.
That will tell us whether the export is even shaped right before I build it,
  and it will surface the shapes the tool makes awkward,
  which is a different and more valuable category than the things it gets wrong.

If you'd rather I keep building, say which of the three and I'll start.
But I'd bet a session of your modelling is worth more than a session of my coding right now.
