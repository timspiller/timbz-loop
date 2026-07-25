# The Timbz Loop

An autonomous improvement loop for a codebase. It **comes up with its own ideas**
for making your project better — UX, visual polish, security hardening, code
health, test coverage, correctness — specs them into hard contracts, builds them,
reviews them adversarially, and then asks you for a decision **in Discord**.

You tap ✅ on your phone. It merges and deploys.

```
Local — Claude Code /loop                    GitHub Actions — cron */5
┌────────────────────────────────┐          ┌─────────────────────────────┐
│ 1. rework   ← 🔁 / needs-work  │          │ read reactions              │
│ 2. review   ← open loop PRs    │          │ authorised reactor?         │
│ 3. ship     ← reviewed clean   │          │  ✅ → merge → deploy        │
│ 4. build    ← specced issues   │          │  ❌ → close, never again    │
│ 5. spec     ← 🚀'd ideas       │          │  🔁 → back to the loop      │
│ 6. ideate   ← when backlog thin│          │  👀 → park it               │
└──────────────┬─────────────────┘          │  🚀/👎 on idea posts        │
               │ posts                       └─────────────────────────────┘
               ▼                                        ▲
        Discord #your-loop-channel ───── reactions ─────┘
```

The thinking runs locally in a Claude Code session (subscription-priced, and you
can watch it). The approval gate runs in the cloud, so approving works from your
phone with your laptop shut. **The local loop has no merge path at all.**

---

## Why you'd trust it running unattended

Most "autonomous agent" setups rely on the agent choosing to follow its
instructions. This one doesn't.

**Self-modification lockout.** A loop PR touching `.timbz/`, `.claude/`,
`.github/`, `scripts/timbz_*` or anything in `extra_locked_paths` **hard-fails
CI**. The lock list is hardcoded in the checker, and the checker locks itself, so
the loop can't weaken its own rules even by rewriting the thing that enforces
them. Config can only *add* locks, never remove one.

**Protected paths.** The files where a bug costs real money or leaks a
credential are off-limits entirely. There's deliberately no unlock label — the
loop holds a token that could apply one to itself — so the escape hatch is the
branch name: humans build those on non-`timbz/` branches, which the gate also
refuses to merge.

**The gate fails closed.** Unknown reactor → nothing. The bot's own pre-seeded
reaction → nothing. No approvers configured → nothing. Red or still-running
check → refuses and tells you why. No checks reported at all → refuses. Wrong
base branch → refuses. Conflicting emoji resolve to the **most conservative**
action, so adding a reaction can never upgrade a decision into a merge.

**Bounded blast radius.** ~400 lines and 8 files per PR, two open loop PRs at a
time, one stage per pass. A queue you can't read is a queue you'll rubber-stamp.

**Kill switch.** `"enabled": false` in `.timbz/config.json` stops the local
driver and the cloud gate on their next tick. The loop can't flip it back.

All of it is tested — 78 tests covering the two functions that can cause a merge
to production, most of them asserting that it *declines*.

## Install

```bash
git clone https://github.com/timspiller/timbz-loop.git
cd timbz-loop
./install.sh /path/to/your/repo
```

Then, in Claude Code in that repo:

```
/timbz-init
```

`/timbz-init` reads your actual codebase and writes the project card (how to run
it, how to verify it, where things live, its conventions), the ideation rubric,
the protected paths, and a CI workflow. It reports what it had to guess so you
can correct it — and it will tell you directly if the repo isn't ready (red
tests, no CI, no safe local mode).

Then follow `.timbz/SETUP.md` — Discord bot, secrets, labels, branch protection.
About 20 minutes, once.

```
/loop 20m /timbz
```

Re-running `install.sh` upgrades the runtime and leaves your tailored config,
project card and rubric alone.

## What it installs

| Path | What |
|---|---|
| `.claude/commands/timbz.md` | the driver — one pass picks the highest-priority stage |
| `.claude/skills/timbz-ideate` | finds work worth doing and scores it |
| `.claude/skills/timbz-spec` | turns a 🚀'd idea into numbered acceptance criteria and non-goals |
| `.claude/skills/timbz-build` | implements exactly the contract, verifies, screenshots, opens the PR |
| `.claude/skills/timbz-review` | five-lens adversarial review; every finding must be confirmed |
| `.claude/skills/timbz-ship` | the Discord pitch, with evidence |
| `.claude/skills/timbz-init` | one-time tailoring to your repo |
| `.timbz/guardrails.md` | the hard rules |
| `.timbz/project.md` | your project card — what the generic skills read |
| `.timbz/rubric.md` | what "better" means here, and how ideas are scored |
| `.timbz/config.json` | channel, approvers, limits, protected paths |
| `scripts/timbz_discord.py` | Discord REST client (no gateway, no daemon) |
| `scripts/timbz_gate.py` | the approval gate — the only thing that merges |
| `scripts/timbz_guard.py` | CI enforcement of the guardrails |
| `.github/workflows/timbz-gate.yml` | the cron that reads your reactions |
| `.github/workflows/ci.yml` | the verification gate (template — tailor it) |

There is **no state file**. Pending work is discovered from GitHub labels, with
the Discord message id stamped into the issue/PR body. The queue prunes itself,
and the loop never has to write inside its own locked directory.

## Requirements

- A GitHub repo, `gh` CLI authenticated
- Claude Code
- Python 3.12+ with `httpx` (only for the three `timbz_*.py` scripts — your
  project can be in any language)
- A Discord server you can add a bot to
- CI that actually verifies your project. The gate refuses to merge a PR with no
  checks reported, so a repo without CI is a loop that can never ship.

## Prior art

The three-stage spec → build → review shape and the "agents never merge" rule
come from [Finn-loop](https://github.com/finna/Finn-loop). The Timbz Loop adds
autonomous ideation, Discord emoji approval, evidence-rich pitches with
screenshots, GitHub Issues instead of Linear, and enforcement in CI rather than
convention.
