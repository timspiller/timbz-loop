---
name: timbz-build
description: Implement one specced Timbz Loop issue exactly to its contract, verify it fully, capture before/after screenshots, and open a PR. Also handles rework when a PR is labelled timbz:revise or timbz:needs-work. Used by the Timbz Loop.
---

# timbz-build

Implement **exactly one contract**, verify it properly, and open a PR. Nothing
more.

Read `.timbz/guardrails.md` first — the rules that will bite you here are locked
paths (1), protected paths (2), size cap (3), contract discipline (4),
verification (5) and tests (6). Then read `.timbz/project.md` for this project's
run command, verification commands, layout and conventions.

---

## Mode A — new build

### 1. Claim

```bash
gh issue list --state open --label "timbz:specced" --json number,title,body
```

Take the **oldest**. Read the whole contract — every AC and every NG.

Refuse and comment if: it has no `## Contract` section, it touches a protected
path, or the size estimate exceeds the caps. Label `timbz:needs-work` and stop.

```bash
gh issue edit <N> --add-label "timbz:building" --remove-label "timbz:specced"
git checkout main && git pull --ff-only
git checkout -b timbz/<N>-<short-slug>
```

The `timbz/` prefix is load-bearing — the gate refuses to merge anything else,
and CI applies the guardrail check based on it.

### 2. Capture "before"

If the change is visible at all, screenshot the current state first — the ship
post is far more useful with a before/after pair.

Boot the app with the "Run it locally" command from `.timbz/project.md`, drive it
with the browser tools, and save the affected view to
`/tmp/timbz-<N>-before.png`.

### 3. Implement

- **Only what the ACs require.** Nothing else. Not the adjacent bug, not the
  tempting refactor, not the typo three files over — those become new ideas you
  file at the end.
- **Match the surrounding code.** Follow the conventions in `.timbz/project.md`
  and, above that, whatever the neighbouring code already does. Do not import
  your own house style into someone else's codebase.
- **Reuse what exists.** The project card's Map section says where things live.
  Search for an existing helper before writing a new one.
- **Write the tests from the contract's test plan.** Behaviour changes ship with
  tests (guardrail 6). If something genuinely can't be tested — pure styling,
  copy — say so explicitly in the PR body rather than quietly skipping.
- **Run any build step** the project card lists for the files you touched.

### Stop conditions

Commit what you have, comment on the issue explaining precisely what you found,
label `timbz:needs-work`, and stop if:

- an AC turns out to be impossible or wrong as written
- the change can't be done without touching a protected or locked path
- you blow the size cap
- you hit something you don't understand well enough to be confident

Improvising a different feature than the one specced is the single worst thing
you can do here.

---

## Mode B — rework

Triggered by an open `timbz/*` PR labelled `timbz:revise` (the approver reacted 🔁) or
`timbz:needs-work` (the review stage failed it).

```bash
gh pr view <N> --json number,headRefName,body,comments
git checkout <headRefName> && git pull
```

Read the change request — the gate posts the approver's Discord reply as a PR comment,
and the review verdict is a PR comment too.

Address **only** what was raised. A rework that also sneaks in new scope is a
rework the approver has to re-read from scratch. Then:

```bash
gh pr edit <N> --remove-label "timbz:revise" --remove-label "timbz:needs-work"
```

Removing the verdict labels puts the PR back in the review queue, which is where
it should go — reworked code gets reviewed again, not shipped on trust.

Then run the verification gate below and push. **Stop there** — do not re-post to
Discord. The review stage runs next pass, and the ship stage posts.

---

## Verification gate — mandatory, both modes

All of it, every time, before the PR opens or the rework pushes:

1. Every command in the **Verify** section of `.timbz/project.md` — tests fully
   green with no new skips, lint clean, any build step run.
2. The guardrail check:

   ```bash
   python scripts/timbz_guard.py --base origin/main --head HEAD --branch "$(git branch --show-current)"
   ```

3. For anything user-facing, boot it with the project card's run command and
   confirm:
   - the affected view renders
   - **zero console errors** (check with the browser tools — not "probably fine")
   - screenshot the new state to `/tmp/timbz-<N>-after.png`

Making a test pass by weakening or skipping it is failing this gate, not passing
it. If you can't get green, that's a stop condition — say so.

---

## Open the PR

```bash
git push -u origin timbz/<N>-<slug>
gh pr create --base main --title "<what changed, plainly>" --body "$(cat <<'EOF'
Closes #<N>

## What changed
<2-4 sentences>

## Acceptance criteria
- [x] **AC-1** <text> — <how it's satisfied / which test proves it>
- [x] **AC-2** …

## Non-goals honoured
- **NG-1** <text> — confirmed untouched

## Verification
- tests: <n> passed
- lint: clean
- guardrails: within caps (<n> files, <n> lines)
- boot check: <views checked>, zero console errors

## Risk
<what could still go wrong, and what a reviewer should look at hardest>

## Screenshots
<before/after, or "no visible change">

## Noticed but not done
<anything you deliberately left alone — these become new ideas>
EOF
)"
```

Then file the "noticed but not done" items as new `timbz:idea` issues so they
aren't lost, and:

```bash
gh issue edit <N> --remove-label "timbz:building"
```

Do **not** add `timbz:ship-ready` — that's the review stage's call, not yours.
Do **not** post to Discord. Do **not** merge. Ever.

## Done

Report the PR number, the AC count satisfied, the diff size, and anything you
filed as a follow-up.
