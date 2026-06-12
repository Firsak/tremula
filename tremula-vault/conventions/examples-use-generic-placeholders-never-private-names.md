---
scope: shared
source: manual
type: convention
---

# Examples use generic placeholders, never private names

Tremula is public from the first commit and ships to PyPI, so every committed
file is a public artifact. Sample values in docs, READMEs, `examples/`, code
comments, and packaging must be generic placeholders — `webapp`,
`webapp_frontend`, `myapp`, `example.com` — never identifiers lifted from a
user's environment.

In particular, treat anything derived from the working context as potentially
sensitive: real project/client/employer names, absolute paths, hostnames, and
internal URLs (e.g. a name read out of a `cwd` or a bug-report path). Substitute
a neutral placeholder before it lands in a tracked file; once committed it
persists in git history.

This is a confidentiality rule, not a style nit. See
[[conventions/note-granularity]] for what is durable enough to record at all.
