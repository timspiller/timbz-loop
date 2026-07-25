# Timbz Loop — setup

One-time wiring, about 20 minutes. Work top to bottom; the last step is a dry run
that proves it works before the loop can do anything.

If you haven't run `/timbz-init` in Claude Code yet, do that first — it fills in
`.timbz/project.md`, `.timbz/rubric.md` and `.timbz/config.json` from your actual
codebase and picks a CI workflow. Everything below assumes those exist.

---

## 1. Prerequisites

```bash
brew install gh && gh auth login     # or your platform's equivalent
gh auth status
```

Python 3.12+ with `httpx` available — the three `scripts/timbz_*.py` files need
nothing else.

## 2. Create the Discord bot

1. **discord.com/developers/applications** → **New Application** → name it.
2. **Bot** tab → **Reset Token** → copy it somewhere safe. Treat it like a
   password. You do **not** need any Privileged Gateway Intents; the loop uses
   only the REST API.
3. **OAuth2 → URL Generator** → scope **`bot`**, permissions **View Channels,
   Send Messages, Attach Files, Read Message History, Add Reactions**. Or use
   this URL with your Application ID (`101440` is exactly those five):

   ```
   https://discord.com/oauth2/authorize?client_id=<APPLICATION_ID>&scope=bot&permissions=101440
   ```

4. Authorise it into your server.
5. Create a **private** channel for the loop and make sure the bot can see it.
   Private matters: anyone who can see the channel can react. The gate ignores
   unauthorised reactors, but there's no reason to broadcast unreleased work.

### Collect three IDs

Discord → **Settings → Advanced → Developer Mode: on**, then right-click to copy:

| ID | From |
|---|---|
| **channel_id** | the loop channel |
| **approver_user_ids** | yourself (and anyone else allowed to approve) |
| **bot_user_id** | the bot in the member list |

`bot_user_id` matters: the bot pre-seeds ✅🔁❌👀 on its own posts so approving is
one tap, and the gate must know to ignore its own reactions.

## 3. Fill in the config

`.timbz/config.json`:

```json
"github": { "repo": "OWNER/REPO", "base_branch": "main" },
"discord": {
  "channel_id": "…",
  "bot_user_id": "…",
  "approver_user_ids": ["…"]
}
```

This file is locked against the loop, so only you can ever change it.

## 4. Store the token in two places

**GitHub** — Settings → Secrets and variables → Actions → New repository secret:
`DISCORD_BOT_TOKEN`.

**Locally** — append to `.env` (make sure it's gitignored):

```
DISCORD_BOT_TOKEN=your_token_here
```

## 5. Create the labels

```bash
gh label create "timbz:idea"       --color FEF3C7 --description "Loop proposal awaiting 🚀 in Discord"
gh label create "timbz:approved"   --color D1FAE5 --description "Approved in Discord, awaiting spec"
gh label create "timbz:specced"    --color A7F3D0 --description "Has a contract, ready to build"
gh label create "timbz:building"   --color BFDBFE --description "Loop is building this now"
gh label create "timbz:ship-ready" --color 86EFAC --description "Reviewed clean, pitched for ✅"
gh label create "timbz:needs-work" --color FED7AA --description "Review found blocking issues"
gh label create "timbz:revise"     --color FDE68A --description "🔁 change requested in Discord"
gh label create "timbz:hold"       --color E5E7EB --description "👀 parked — loop must not touch"
gh label create "timbz:rejected"   --color FECACA --description "👎 never propose this again"
```

## 6. Protect the base branch

Settings → Branches → add a rule for `main`:

- ✅ **Require status checks to pass** → add every job in your `ci.yml`
- ✅ **Require branches to be up to date before merging**
- ❌ Do **not** require pull request reviews — the gate merges via the Actions
  token, and a review requirement blocks it. The Discord ✅ *is* the review.

Settings → Actions → General → Workflow permissions → **Read and write**.

## 7. Dry run — before it can do anything

**a) Can the bot post?**

```bash
printf 'Timbz Loop wiring test. Ignore me.\n' > /tmp/t.md
python scripts/timbz_discord.py post --kind ship --body-file /tmp/t.md
```

The message should appear with ✅ 🔁 ❌ 👀 already on it. Note the `message_id`.

**b) Can it read your reaction back?**

Tap ✅, then:

```bash
python scripts/timbz_discord.py reactions --message-id <id>
```

Your user ID should appear under `✅`. If not, `approver_user_ids` is wrong.

**c) Is the gate inert with nothing pending?**

```bash
python scripts/timbz_gate.py --dry-run
```

Expect `Nothing pending.` Then run it in the cloud: Actions → **timbz-gate** →
Run workflow, leaving **dry run** ticked.

Delete the test message when you're done.

## 8. Start the loop

```bash
/loop 20m /timbz
```

Watch the first three or four passes. Make the first end-to-end run something
**deliberately trivial** — a copy fix, a README correction. Prove the pipe works
before you trust it with anything that matters.

---

## Running it

- **PRs:** ✅ merge & deploy · 🔁 rework (reply with what to change) · ❌ drop for
  good · 👀 park it
- **Ideas:** 🚀 build it · 👎 never propose it again
- **Stop everything:** `"enabled": false` in `.timbz/config.json`, commit, push.
  Both the local driver and the cloud gate go inert on their next tick.
- **Change the loop itself:** on a normal branch, in a normal Claude Code
  session. The loop is locked out of its own machinery on purpose.

## If something's wrong

| Symptom | Cause |
|---|---|
| Reaction does nothing | the PR/issue body is missing its `<!-- timbz-discord: ... -->` marker, or the cron hasn't fired (up to 5 min; GitHub's scheduler drifts) |
| "Nothing pending" but a post is waiting | the item lost its `timbz:idea` / `timbz:ship-ready` label |
| ✅ answered with "can't merge yet" | a check is red or still running — the gate refuses to merge unverified code by design |
| Nothing ever gets proposed | the `limits` caps are already met, or `enabled` is false |
| Loop PR fails CI on `guardrails` | it tried to touch a locked or protected path — working as intended |
