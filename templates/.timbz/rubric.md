# What "better" means for <PROJECT NAME>

The ideate skill reads this before proposing anything. Its job is not to generate
plausible software tasks — it's to generate things that would make **this**
project better for **these** users.

Run `/timbz-init` to have this drafted from your codebase, then edit it. The
edits matter more than the draft: this file is the difference between a loop that
proposes what your project actually needs and one that proposes a dark mode
toggle every week.

---

## Idea categories

Roughly the mix to aim for. Tune the shares to what this project actually needs —
a young codebase wants features and tests; a mature one wants hardening.

| Category | ~Share | Examples |
|---|---|---|
| **Security hardening** | 20% | auth and session edge cases, secret/credential handling, injection surfaces, rate limiting, dependency CVEs |
| **Correctness & robustness** | 20% | error paths, races, time zone and DST edges, state that survives a restart, exceptions being swallowed |
| **UI/UX & visual polish** | 25% | clarity of important state, empty and loading states, narrow layouts, contrast and accessibility, copy |
| **Code health** | 15% | lint baseline debt, oversized modules, dead code, duplicated logic |
| **Test coverage** | 15% | untested branches in the highest-risk modules |
| **Performance** | 5% | slow queries, render cost with realistic data volumes |

Don't force the mix on any single pass — but if five passes in a row all produce
styling tweaks, the loop is coasting. Go find something that matters.

## Scoring

Score every candidate 1–5 on each, then:

```
score = (impact × confidence) / effort × multiplier
```

- **Impact** — how much better is the user's life? Something silently broken that
  they're relying on is a 5. A nicer button hover is a 1.
- **Confidence** — how sure are we this is real and the fix is right? Verified by
  reading the actual code = high. "Apps usually want this" = low. Anything ≤2
  needs more research before it's proposed, not a hopeful PR.
- **Effort** — changed lines + blast radius + review burden. Mind the size cap in
  `.timbz/config.json`.
- **Multiplier** — ×1.5 for security, ×1.3 for anything touching the top two
  product values in `.timbz/project.md`, ×0.7 for pure aesthetics.

Only ideas scoring **≥ 4** get posted. Post at most `max_ideas_per_pass`.

## Every idea post must contain

- **What** — one sentence, concrete, no adjectives doing load-bearing work
- **Why it matters** — tied to a product value, with the specific file/line or
  reproduction that makes it real
- **Blast radius** — which files, which users, what breaks if it's wrong
- **Score** — the four numbers and the total, so a bad score is visible
- **What it is NOT** — the scope boundary, so 🚀 means something specific

## Hard nos — never propose these

- Rewrites, framework migrations, "let's move to <X>"
- Anything adding a runtime dependency without a stated reason it's unavoidable
- Analytics or telemetry that sends user data anywhere
- Feature ideas the loop can't verify locally — those need a human spec
- <PROJECT-SPECIFIC: architectural decisions already made deliberately that you
  don't want relitigated every week. Be explicit — this section saves you more
  time than any other.>
- Anything already rejected — i.e. matching a **closed issue labelled
  `timbz:rejected`**. Read those every pass.

## Standing backlog

Real work, already identified, always eligible:

1. <Known debt, e.g. lint rules currently suppressed as baseline debt — one rule
   per PR.>
2. <Modules that are too big and have a clear seam.>
3. <Coverage measurement, or the worst-covered high-risk area.>
