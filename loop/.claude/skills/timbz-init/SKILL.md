---
name: timbz-init
description: Tailor a freshly installed Timbz Loop to this repository — write the project card, the ideation rubric, protected paths, size exemptions and CI, by reading the actual codebase. Run once after install.sh, before the first loop pass.
---

# timbz-init

The Timbz Loop was just installed here. Its skills are generic; your job is to
make them fit **this** repository.

Everything you write in this pass is read by every subsequent pass, so accuracy
compounds. A wrong verify command means every build fails the gate. A vague Map
section means the ideate stage proposes generic nonsense. Get it right and the
loop is genuinely useful on day one.

This is a research-heavy pass. Take your time; it happens once.

## 1. Read the repository properly

Not the README — the code. Establish:

- **What this software does and who uses it.** What are they trying to
  accomplish, and what's the worst thing that could go wrong for them?
- **The stack** — language, framework, datastore, frontend approach, test
  framework, package manager, how it deploys.
- **How to run it locally**, and critically: is there a safe mode? A simulator,
  an offline flag, a fixture database? The loop must never be able to touch real
  data or a live external account. If there's no safe mode, say so loudly — it's
  the single most important thing to add before running the loop unattended.
- **How to test and lint it.** Run the commands. Do they actually pass right
  now? If tests are red or lint is noisy on a clean checkout, the loop can never
  open a PR — fixing that is prerequisite work, and you should say so.
- **The layout** — where the API lives, the domain logic, persistence, auth and
  secrets, the frontend, the tests.
- **The conventions** — read several files and characterise the house style
  honestly. Comment density and purpose. Where helpers live. What's deliberately
  absent (no ORM? no framework? no build step?) — those absences are decisions,
  and the loop needs to know not to relitigate them.
- **Existing CI**, if any.

Ask the user anything you genuinely can't determine — especially the product
values and what's off-limits. Two or three good questions here are worth more
than an hour of guessing.

## 2. Write `.timbz/project.md`

Replace every `<placeholder>` in the template. Rules:

- **Commands must be copy-pasteable and verified.** Run each one before you
  write it down.
- The Map table names real paths that exist.
- Conventions are stated as rules an outsider would otherwise break — not
  platitudes. "Comments explain why, not what" is useful. "Write clean code" is
  not.
- **Product values are the highest-leverage thing in the file.** Three to five,
  specific to this product, ordered. "Good UX" is worthless. "The UI is read
  during a drawdown, so state must be unambiguous and never cheerful about a
  loss" tells the loop exactly what to propose and what to reject.

## 3. Choose the protected paths

The files where a bug costs real money, corrupts real data, or leaks a
credential. Typically: auth, session handling, crypto/secrets, payment or
billing, the persistence layer, anything enforcing a limit someone relies on.

Write them into `protected_paths` in `.timbz/config.json` **and** the matching
section of `.timbz/project.md`. The loop may read and reason about these, and
file issues against them, but may never open a PR touching them.

Err on the side of protecting more. It's cheap — the loop just files an issue
instead — and it's the difference between an autonomous loop you can leave
running and one you can't.

## 4. Fill in the rest of the config

- `github.repo` — `OWNER/REPO` (`gh repo view --json nameWithOwner`)
- `github.base_branch` — usually `main`; confirm it's what deploys
- `size_exempt_paths` — generated and vendored paths (build output, bundled CSS,
  `vendor/`). These are real files but not hand-written, and counting them makes
  a one-line change look sprawling.
- `extra_locked_paths` — project-specific things the loop must never edit: the
  lint config, the deploy manifest, anything that would let it weaken its own
  gate. Config can only *add* locks, never remove one.
- `limits` — the defaults (400 lines / 8 files / 2 open PRs) are sensible. Lower
  them for a codebase where review is expensive.

Leave the Discord fields blank; those are the human's job in `.timbz/SETUP.md`.

## 5. Write `.timbz/rubric.md`

Tune the category mix to what this project actually needs — a young codebase
wants features and tests, a mature one wants hardening.

The **Hard nos** section is the one that saves the most time. Fill it with the
architectural decisions already made deliberately that you don't want
relitigated every week. Read the code and the git history for these: a comment
saying "single worker on purpose", a rejected dependency, a pattern consistently
avoided.

Populate **Standing backlog** with real debt you found in step 1 — suppressed
lint rules, oversized modules, missing coverage. Naming three concrete things
here means the loop's first passes are useful instead of exploratory.

## 6. Install CI

If the repo has no CI, copy the closest template from the loop package's
`templates/ci/` to `.github/workflows/ci.yml` and tailor it: the real install
command, the real test and lint commands, a boot check that actually boots this
app.

If CI already exists, leave it alone but **add the `guardrails` job** from the
template — without it, the self-modification lockout is only a prompt, and a
prompt is not a guardrail.

Then verify the CI commands work locally.

## 7. Report

Tell the user:

- what you learned about the project, briefly
- the protected paths you chose and why
- anything you had to guess, flagged clearly so they can correct it
- **prerequisite problems**: red tests, no safe local mode, no CI, no test suite
  at all. Be direct — these block the loop, and it's much better to say so now
  than to have every pass fail mysteriously.
- next step: `.timbz/SETUP.md` for the Discord wiring

## Never

- Invent a command you didn't run
- Write a project card full of hedged generalities — an inaccurate card is worse
  than an obviously incomplete one, because the loop will trust it
- Leave `<placeholder>` text anywhere
- Fill in the Discord credentials; those are the human's to hold
