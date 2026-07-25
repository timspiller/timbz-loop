#!/usr/bin/env python3
"""The Timbz Loop approval gate.

Runs on a cron in GitHub Actions. For every Discord message the loop is waiting
on, it reads the reactions, decides whether an authorised human has answered,
and executes exactly that answer against GitHub.

This is the ONLY thing in the system that merges. It is written to fail closed:
every ambiguity, missing config, unknown reactor, red check or unexpected branch
resolves to "do nothing" rather than "probably fine".

    python scripts/timbz_gate.py --dry-run     # decide, print, touch nothing
    python scripts/timbz_gate.py               # decide and act

Environment: DISCORD_BOT_TOKEN, GITHUB_TOKEN.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Optional

import httpx

from timbz_discord import Discord, DiscordError, _load_dotenv, load_config

GITHUB_API = "https://api.github.com"

# The loop stamps the Discord message id into the issue/PR body when it posts.
# Keeping this pointer on the GitHub object rather than in a committed state
# file means the loop never has to write inside its own locked `.timbz/`
# directory, and the queue prunes itself: the labels that make something
# "pending" are the same labels the gate removes when it acts.
MARKER_RE = re.compile(r"<!--\s*timbz-discord:\s*(\{.*?\})\s*-->", re.DOTALL)

# Most conservative answer wins when several emoji are present. Someone who
# reacts ✅ and then thinks better of it and adds ❌ means ❌ — and a stray
# extra reaction must never be able to upgrade a decision into a merge.
PRECEDENCE = {
    "ship": ["reject", "hold", "revise", "merge"],
    "idea": ["kill", "promote"],
}

# Check-run conclusions that are not a red light. Anything else — including
# "action_required" and anything still running — blocks the merge.
OK_CONCLUSIONS = {"success", "neutral", "skipped"}


# ---------------------------------------------------------------------------
# Decision logic (pure — no network, no side effects, heavily tested)
# ---------------------------------------------------------------------------


def authorised_reactors(user_ids: list[str], cfg: dict) -> list[str]:
    """Filter reactors down to configured approvers.

    The bot pre-seeds every emoji on its own posts so approving is one tap, so
    its own id must be excluded or every post would instantly self-approve.
    """
    discord_cfg = cfg.get("discord", {})
    approvers = {str(u) for u in discord_cfg.get("approver_user_ids", [])}
    bot_id = str(discord_cfg.get("bot_user_id", ""))
    return [u for u in map(str, user_ids) if u in approvers and u != bot_id]


def resolve_action(entry: dict, reactions: dict[str, list[str]],
                   cfg: dict) -> Optional[dict]:
    """Decide what an entry's reactions mean.

    Returns {"action", "emoji", "by"} or None for "no decision yet".
    """
    if not cfg.get("enabled", False):
        return None  # kill switch

    kind = entry.get("kind")
    if kind not in PRECEDENCE:
        return None

    # Fail closed: with no approvers configured, nobody can approve anything.
    if not cfg.get("discord", {}).get("approver_user_ids"):
        return None

    emoji_map = cfg.get("emoji", {}).get(kind, {})

    decided: dict[str, tuple[str, str]] = {}
    for emoji, user_ids in reactions.items():
        action = emoji_map.get(emoji)
        if not action:
            continue  # an emoji we don't recognise is not a signal
        who = authorised_reactors(user_ids, cfg)
        if who:
            decided[action] = (emoji, who[0])

    for action in PRECEDENCE[kind]:
        if action in decided:
            emoji, by = decided[action]
            return {"action": action, "emoji": emoji, "by": by}
    return None


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------


class GitHub:
    def __init__(self, repo: str, token: Optional[str] = None,
                 timeout: float = 30.0):
        self.repo = repo
        _load_dotenv()
        token = token or os.environ.get("GITHUB_TOKEN", "").strip()
        if not token:
            raise RuntimeError("GITHUB_TOKEN is not set")
        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            })

    def __enter__(self) -> "GitHub":
        return self

    def __exit__(self, *exc: object) -> None:
        self._client.close()

    def _req(self, method: str, path: str, **kw: Any) -> Any:
        resp = self._client.request(method, f"{GITHUB_API}{path}", **kw)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"{method} {path} -> {resp.status_code} {resp.text[:400]}")
        return resp.json() if resp.content else None

    def pull(self, number: int) -> dict:
        return self._req("GET", f"/repos/{self.repo}/pulls/{number}")

    def issues_with_label(self, label: str) -> list[dict]:
        """Open issues *and* PRs carrying a label (GitHub treats both as issues)."""
        return self._req(
            "GET", f"/repos/{self.repo}/issues",
            params={"labels": label, "state": "open", "per_page": 100}) or []

    def issue(self, number: int) -> dict:
        return self._req("GET", f"/repos/{self.repo}/issues/{number}")

    def labels(self, number: int) -> set[str]:
        data = self.issue(number)
        return {lbl["name"] for lbl in data.get("labels", [])}

    def add_labels(self, number: int, names: list[str]) -> None:
        self._req("POST", f"/repos/{self.repo}/issues/{number}/labels",
                  json={"labels": names})

    def remove_label(self, number: int, name: str) -> None:
        try:
            self._req("DELETE",
                      f"/repos/{self.repo}/issues/{number}/labels/{name}")
        except RuntimeError:
            pass  # label wasn't there; that's the state we wanted anyway

    def comment(self, number: int, body: str) -> None:
        self._req("POST", f"/repos/{self.repo}/issues/{number}/comments",
                  json={"body": body})

    def close_issue(self, number: int, reason: str = "not_planned") -> None:
        self._req("PATCH", f"/repos/{self.repo}/issues/{number}",
                  json={"state": "closed", "state_reason": reason})

    def close_pull(self, number: int) -> None:
        self._req("PATCH", f"/repos/{self.repo}/pulls/{number}",
                  json={"state": "closed"})

    def check_conclusions(self, sha: str) -> list[tuple[str, str]]:
        """[(check name, conclusion-or-status), ...] for a commit."""
        data = self._req(
            "GET", f"/repos/{self.repo}/commits/{sha}/check-runs?per_page=100")
        out = []
        for run in data.get("check_runs", []):
            if run.get("status") != "completed":
                out.append((run["name"], f"pending:{run.get('status')}"))
            else:
                out.append((run["name"], run.get("conclusion") or "unknown"))
        return out

    def merge(self, number: int, method: str, title: str) -> dict:
        return self._req("PUT", f"/repos/{self.repo}/pulls/{number}/merge",
                         json={"merge_method": method, "commit_title": title})

    def delete_branch(self, branch: str) -> None:
        try:
            self._req("DELETE",
                      f"/repos/{self.repo}/git/refs/heads/{branch}")
        except RuntimeError:
            pass  # already gone


# ---------------------------------------------------------------------------
# Pre-flight safety checks before a merge
# ---------------------------------------------------------------------------


def merge_blockers(pr: dict, checks: list[tuple[str, str]], cfg: dict) -> list[str]:
    """Everything standing between this PR and a merge. Empty list == clear."""
    blockers = []
    gh_cfg = cfg.get("github", {})

    prefix = gh_cfg.get("branch_prefix", "timbz/")
    head = (pr.get("head") or {}).get("ref", "")
    if not head.startswith(prefix):
        blockers.append(
            f"head branch {head!r} is not a loop branch ({prefix}*)")

    base = (pr.get("base") or {}).get("ref", "")
    want_base = gh_cfg.get("base_branch", "main")
    if base != want_base:
        blockers.append(f"targets {base!r}, not {want_base!r}")

    if pr.get("draft"):
        blockers.append("PR is a draft")

    if pr.get("mergeable") is False:
        blockers.append(f"not mergeable ({pr.get('mergeable_state')})")

    if not checks:
        blockers.append("no CI checks reported — refusing to merge unverified")
    bad = [f"{name} ({res})" for name, res in checks
           if res not in OK_CONCLUSIONS]
    if bad:
        blockers.append("checks not green: " + ", ".join(bad))

    return blockers


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _approver_replies(dc: Discord, channel: str, message_id: str,
                      cfg: dict) -> str:
    """Any replies an approver wrote under the post — the 🔁 change request."""
    try:
        msgs = dc._request(  # noqa: SLF001 — internal by design, same package
            "GET", f"/channels/{channel}/messages?after={message_id}&limit=100")
    except DiscordError:
        return ""
    approvers = {str(u) for u in cfg["discord"].get("approver_user_ids", [])}
    out = []
    for m in msgs or []:
        ref = (m.get("message_reference") or {}).get("message_id")
        if str(ref) == str(message_id) and str(
                (m.get("author") or {}).get("id")) in approvers:
            content = (m.get("content") or "").strip()
            if content:
                out.append(content)
    return "\n\n".join(reversed(out))


def execute(entry: dict, decision: dict, gh: GitHub, dc: Discord,
            cfg: dict, dry_run: bool) -> str:
    """Carry out one decision. Returns a human-readable outcome line.

    Every branch is idempotent: if the target state already holds, it reports
    "already …" and does nothing. The cron runs every 5 minutes and pending.json
    is only pruned later by the local loop, so the same decision will be seen
    many times.
    """
    action = decision["action"]
    labels = cfg["labels"]
    channel = cfg["discord"]["channel_id"]
    tag = f"{entry.get('kind')} {entry.get('pr') or entry.get('issue')}"

    def say(text: str) -> None:
        if not dry_run:
            try:
                dc.reply(channel, entry["message_id"], text)
            except DiscordError as exc:
                print(f"  ! could not reply in Discord: {exc}", file=sys.stderr)

    # -- idea posts --------------------------------------------------------

    if action == "promote":
        num = int(entry["issue"])
        if labels["approved"] in gh.labels(num):
            return f"{tag}: already approved"
        if dry_run:
            return f"{tag}: WOULD label #{num} {labels['approved']}"
        # The clearance label is what lets a build touch protected paths, and
        # it is only meaningful because *this* process applies it: the gate runs
        # in Actions as github-actions[bot], an identity the local loop's token
        # cannot assume. timbz_guard.py verifies the actor, not just the label.
        gh.add_labels(num, [labels["approved"], labels["cleared"]])
        gh.remove_label(num, labels["idea"])
        gh.comment(num, "🚀 Approved in Discord by an authorised approver.\n\n"
                        "This also clears the build to touch protected paths if "
                        "the contract needs them — the clearance is verified "
                        "against the actor that applied it, so only a real "
                        "reaction can grant it.")
        say(f"🚀 Queued — issue #{num} is approved. "
            f"The loop will pick it up on the next pass.")
        return f"{tag}: promoted #{num}"

    if action == "kill":
        num = int(entry["issue"])
        if gh.issue(num).get("state") == "closed":
            return f"{tag}: already closed"
        if dry_run:
            return f"{tag}: WOULD close idea #{num}"
        gh.add_labels(num, [labels["rejected"]])
        gh.close_issue(num, reason="not_planned")
        gh.comment(num, "👎 Rejected in Discord. The ideate skill reads closed "
                        f"`{labels['rejected']}` issues and will not re-propose this.")
        say(f"👎 Dropped — issue #{num} closed. The loop won't pitch it again.")
        return f"{tag}: killed #{num}"

    # -- ship posts --------------------------------------------------------

    num = int(entry["pr"])
    pr = gh.pull(num)

    if action == "merge":
        if pr.get("merged"):
            return f"{tag}: already merged"
        if pr.get("state") != "open":
            return f"{tag}: PR is {pr.get('state')}, not merging"

        checks = gh.check_conclusions(pr["head"]["sha"])
        blockers = merge_blockers(pr, checks, cfg)
        if blockers:
            reason = "; ".join(blockers)
            if dry_run:
                return f"{tag}: WOULD REFUSE merge — {reason}"
            gh.comment(num, "✅ was given in Discord, but the gate refused to "
                            "merge:\n\n- " + "\n- ".join(blockers))
            say(f"⛔ Can't merge PR #{num} yet — {reason}")
            return f"{tag}: refused merge — {reason}"

        if dry_run:
            return f"{tag}: WOULD MERGE PR #{num} ({pr['title']})"

        result = gh.merge(num,
                          cfg["github"].get("merge_method", "squash"),
                          pr["title"])
        sha = (result or {}).get("sha", "")[:7]
        if cfg["github"].get("delete_branch_on_merge", True):
            gh.delete_branch(pr["head"]["ref"])
        say(f"✅ Merged PR #{num} as `{sha}` → "
            f"`{cfg['github']['base_branch']}`. Railway is deploying.")
        return f"{tag}: merged #{num} as {sha}"

    if action == "reject":
        if pr.get("state") != "open":
            return f"{tag}: PR already {pr.get('state')}"
        if dry_run:
            return f"{tag}: WOULD CLOSE PR #{num} and kill its idea"
        gh.comment(num, "❌ Rejected in Discord. Closing the PR; the underlying "
                        "idea is marked rejected so it won't come back.")
        gh.close_pull(num)
        gh.delete_branch(pr["head"]["ref"])
        if entry.get("issue"):
            gh.add_labels(int(entry["issue"]), [labels["rejected"]])
            gh.close_issue(int(entry["issue"]), reason="not_planned")
        say(f"❌ Closed PR #{num}. Won't be proposed again.")
        return f"{tag}: rejected #{num}"

    if action == "revise":
        if labels["revise"] in gh.labels(num):
            return f"{tag}: already flagged for revision"
        notes = _approver_replies(dc, channel, entry["message_id"], cfg)
        if dry_run:
            return (f"{tag}: WOULD flag PR #{num} for revision"
                    f"{' with notes' if notes else ' (no notes given)'}")
        gh.add_labels(num, [labels["revise"]])
        gh.remove_label(num, labels["ship_ready"])
        gh.comment(num, "🔁 Change requested in Discord.\n\n"
                        + (f"> {notes}" if notes else
                           "_No notes given — the loop should re-read the "
                           "contract and its own review verdict._"))
        say(f"🔁 Sent PR #{num} back. The loop will rework it next pass.")
        return f"{tag}: revise #{num}"

    if action == "hold":
        if labels["hold"] in gh.labels(num):
            return f"{tag}: already on hold"
        if dry_run:
            return f"{tag}: WOULD put PR #{num} on hold"
        gh.add_labels(num, [labels["hold"]])
        gh.remove_label(num, labels["ship_ready"])
        say(f"👀 PR #{num} is on hold. Nothing will happen to it until you "
            f"remove the `{labels['hold']}` label.")
        return f"{tag}: held #{num}"

    return f"{tag}: unknown action {action!r}"


# ---------------------------------------------------------------------------


def parse_marker(body: Optional[str]) -> Optional[dict]:
    """Pull the `<!-- timbz-discord: {...} -->` pointer out of an issue/PR body.

    Untrusted-input note: only the message id is ever read out of this, and it
    is used solely to address a Discord API call. Nothing in the body is
    executed, and a malformed marker means "not pending", not "guess".
    """
    if not body:
        return None
    m = MARKER_RE.search(body)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    mid = str(data.get("message_id", "")).strip()
    if not mid.isdigit():
        return None
    out = {"message_id": mid}
    if str(data.get("issue", "")).isdigit():
        out["issue"] = int(data["issue"])
    return out


def discover_pending(gh: "GitHub", cfg: dict) -> list[dict]:
    """Everything currently awaiting a reaction, read from GitHub labels.

    There is no state file. An idea is pending while it is an open issue
    labelled `timbz:idea`; a PR is pending while it is open and labelled
    `timbz:ship-ready`. Acting on either removes that label or closes the
    object, so resolved items disappear from this list on their own.
    """
    labels = cfg["labels"]
    pending: list[dict] = []

    for item in gh.issues_with_label(labels["idea"]):
        if "pull_request" in item:
            continue  # a PR wearing the idea label is not an idea post
        marker = parse_marker(item.get("body"))
        if marker:
            pending.append({"kind": "idea", "issue": item["number"],
                            "title": item.get("title", ""), **marker})

    for item in gh.issues_with_label(labels["ship_ready"]):
        if "pull_request" not in item:
            continue  # ship posts are PRs
        marker = parse_marker(item.get("body"))
        if marker:
            marker.setdefault("issue", None)
            pending.append({"kind": "ship", "pr": item["number"],
                            "title": item.get("title", ""), **marker})

    return pending


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Timbz Loop approval gate")
    ap.add_argument("--dry-run", action="store_true",
                    help="decide and print, but change nothing")
    args = ap.parse_args(argv)

    _load_dotenv()  # local runs keep the token in .env; CI passes it in the env
    cfg = load_config()

    if not cfg.get("enabled", False):
        print("Timbz Loop is disabled (.timbz/config.json enabled=false).")
        return 0

    channel = cfg["discord"]["channel_id"]
    if not channel or not cfg["discord"].get("approver_user_ids"):
        print("Discord channel_id or approver_user_ids not configured — "
              "gate is inert. See .timbz/SETUP.md.")
        return 0

    # Setup is ordered channel-ids-then-secret, so there's a window where the
    # config is complete but DISCORD_BOT_TOKEN isn't set yet. Say so once,
    # clearly, instead of raising a stack trace every five minutes.
    if not os.environ.get("DISCORD_BOT_TOKEN", "").strip():
        print("DISCORD_BOT_TOKEN is not set — gate is inert.\n"
              "  In CI: add it as a repository secret (Settings → Secrets and "
              "variables → Actions).\n"
              "  Locally: add it to .env. See .timbz/SETUP.md step 4.")
        return 0

    failures = 0
    with Discord() as dc, GitHub(cfg["github"]["repo"]) as gh:
        pending = discover_pending(gh, cfg)
        if not pending:
            print("Nothing pending.")
            return 0

        print(f"{len(pending)} pending item(s)"
              f"{' [DRY RUN]' if args.dry_run else ''}")

        for entry in pending:
            ref = f"{entry.get('kind')} msg {entry.get('message_id')}"
            try:
                emojis = list(cfg["emoji"].get(entry.get("kind"), {}))
                reactions = dc.all_reactions(channel, entry["message_id"],
                                             emojis)
                decision = resolve_action(entry, reactions, cfg)
                if not decision:
                    print(f"- {ref}: no decision yet")
                    continue
                print(f"- {ref}: {decision['emoji']} "
                      f"({decision['action']}) by {decision['by']}")
                print(f"  {execute(entry, decision, gh, dc, cfg, args.dry_run)}")
            except Exception as exc:  # one bad entry must not stall the queue
                failures += 1
                print(f"- {ref}: ERROR {exc}", file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
