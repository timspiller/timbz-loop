# Project card — <PROJECT NAME>

Everything project-specific the Timbz Loop needs. The skills in `.claude/skills/`
are generic and read this file for the concrete commands and layout, so **this is
the file you rewrite** when you drop the loop into a new repo.

Run `/timbz-init` in Claude Code to have this filled in from your actual
codebase, or write it by hand. Either way: **be accurate.** A wrong command here
means every build pass fails the verification gate, and a vague Map section means
the ideate stage proposes generic nonsense instead of things that matter.

---

## What this is

<Two or three sentences. What the software does, who uses it, and what they're
trying to accomplish. Then the stack: language, framework, datastore, frontend,
how it's deployed.>

## Run it locally

<The exact command, with any env vars that make it safe to run — a throwaway
data directory, a simulator/offline mode, a test API key. A loop pass must never
be able to touch real data or a real external account.>

```bash
<command>
```

<What URL it serves, which route is which, and anything needed on first load
(seed data, a bootstrap account — name the helper that does it).>

## Verify

Every command here must pass before the loop opens a PR. Keep this list short and
real — if a command is slow or flaky, say so.

```bash
<test command>          # must be fully green
<lint command>          # must be clean
<build/codegen step>    # ONLY when <these files> changed
```

<Anything CI additionally enforces, and whether it blocks.>

## Map

| Area | Where |
|---|---|
| <HTTP/API layer> | `<path>` |
| <core domain logic> | `<path>` |
| <persistence> | `<path>` |
| <auth / secrets / redaction> | `<path>` |
| <frontend> | `<path>` |
| <tests> | `<path>` |

<Name the two or three test files worth reading before changing behaviour.>

## Conventions

<The house style, stated as rules an outsider would otherwise break. Comment
density and what comments are for. Where helpers live. What's banned — a
framework you don't want introduced, a pattern you've deliberately avoided.
Anything load-bearing about concurrency, process model, or deploy shape.>

## Product values, in priority order

1. <The thing that must never break, and why it matters to the user.>
2. <…>
3. <…>

<Three to five. These are what the ideate stage scores against, so they need to
be specific to this product — "good UX" is useless, "the UI is read during
drawdowns so state must be unambiguous and never cheerful about a loss" is not.>

## Protected paths — the loop may not change these

`<path>`, `<path>`, `<path>`

<Why: a bug here costs money / corrupts data / leaks a credential. The loop
files an issue and stops; a human builds it on a non-`timbz/` branch. Keep in
sync with `protected_paths` in `.timbz/config.json`.>

## Deploy

<Where it deploys, what triggers a deploy, and anything that would be
catastrophic to get wrong — persistent volumes, migrations, env vars that must
exist.>
