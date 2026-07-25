---
name: timbz-ship
description: Post a reviewed, ship-ready Timbz Loop PR to Discord with evidence and screenshots so it can be approved with a ✅ emoji reaction. Stamps the Discord message id onto the PR so the approval gate can find it. Used by the Timbz Loop as the final stage before human approval.
---

# timbz-ship

Ask the approver for a decision. Your only job is to give them **everything they
need to answer in thirty seconds on a phone**, and then get out of the way.

You do not merge. Reacting ✅ is what merges, via
`.github/workflows/timbz-gate.yml`.

## 1. Pick the PR

```bash
gh pr list --state open --label "timbz:ship-ready" --json number,title,body,url
```

Take the oldest whose body does **not** already contain a
`<!-- timbz-discord: ... -->` marker. A PR that already has one has already been
pitched — leave it alone.

Gather:

```bash
gh pr view <N> --json number,title,body,url,additions,deletions,changedFiles
gh pr checks <N>
gh pr view <N> --comments        # the review verdict
gh issue view <linked> --json body   # the contract
```

## 2. Sanity-check before pitching

Do not post if any of these are true — instead remove `timbz:ship-ready`, add
`timbz:needs-work`, comment why, and stop:

- CI checks are failing or still running
- the review verdict was NEEDS-WORK, or has open 🔴 blocking findings
- the PR has merge conflicts
- the head branch isn't `timbz/*`, or the base isn't `main`

The gate would refuse all of these anyway, but a ✅ that silently does nothing is
worse than never asking.

## 3. Write the post

Discord caps at 2000 characters and the approver is reading on a phone. Be ruthless.
Lead with what it does; the diff is a link away.

```
🚢 **<plain-English title — what this does for the trader>**

<2 sentences: what changed and why it's better. No jargon, no filenames.>

**Contract:** <n>/<n> acceptance criteria met
**Review:** ✅ clean  |  ⚠️ <n> non-blocking note(s)
**Checks:** ✅ tests <n> · lint · guardrails · boot
**Size:** <n> files, +<a>/-<d>
**Risk:** <one clause — the honest one, not the reassuring one>

<the single most useful thing a reviewer should look at hardest>

<pr url>

✅ merge & deploy  ·  🔁 rework (reply with what to change)  ·  ❌ drop  ·  👀 hold
```

If there are 🟡 non-blocking findings, name the most important one in a line.
**Never** describe a PR as clean when the review raised something — the whole
value of this post is that the approver can trust it.

## 4. Post it with screenshots

Attach the before/after images the build stage captured. A visual change pitched
without a screenshot is asking the approver to open a laptop, which means it'll sit until
tomorrow.

```bash
python scripts/timbz_discord.py post --kind ship --body-file /tmp/ship.md \
  --image /tmp/timbz-<N>-before.png \
  --image /tmp/timbz-<N>-after.png
```

`--kind ship` pre-seeds ✅ 🔁 ❌ 👀 on the message so approving is one tap. (The
bot's own reactions are ignored by the gate — see `authorised_reactors()`.)

## 5. Stamp the marker — do not skip this

The command prints `{"message_id": "..."}`. Without this marker on the PR, the
gate cannot find the message and **no reaction will ever do anything**.

```bash
gh pr edit <N> --body "$(gh pr view <N> --json body -q .body)

<!-- timbz-discord: {\"message_id\": \"<id>\", \"issue\": <linked issue #>} -->"
```

Then verify it landed:

```bash
gh pr view <N> --json body -q .body | grep timbz-discord
```

If the stamp failed, reply in the thread saying the pitch is void and re-post
next pass. A live-looking approval request that can't be actioned is the worst
outcome this stage has.

## Done

Report the PR number, the Discord message id, and confirm the marker is on the
PR.

## Never

- Merge, or enable auto-merge
- Post a PR whose review said needs-work
- Oversell. If the risk is medium, say medium. the approver is approving from a phone on
  the strength of your summary — everything downstream depends on it being
  accurate.
