#!/usr/bin/env python3
"""Guardrail enforcement for loop-authored PRs.

Runs in CI on every pull request. If the head branch is a loop branch
(`timbz/*`) this fails the build when the diff breaks a rule from
`.timbz/guardrails.md`. On human branches it does nothing.

The point is that the loop's rules are not merely written down in a prompt it
could talk itself out of — they are a red X on the PR.

    python scripts/timbz_guard.py --base origin/main --head HEAD --branch timbz/12-foo

In GitHub Actions the arguments default to GITHUB_BASE_REF / GITHUB_HEAD_REF.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / ".timbz" / "config.json"

# Hardcoded on purpose — NOT read from config.
#
# The loop must not be able to unlock itself, and anything it could edit is
# something it could unlock. These prefixes cover this file too, so a loop PR
# cannot weaken this check even by rewriting the checker. Keep in sync with
# `locked_paths` in .timbz/config.json (verified below).
LOCKED_PREFIXES = (
    ".timbz/",
    ".claude/",
    ".github/",
    "scripts/timbz_",
    ".env",
    ".gitignore",
)

# Generated or vendored paths don't count against the size cap — they're real
# but not hand-written, and counting them makes a one-line style change look
# like a sprawling PR.
#
# Unlike LOCKED_PREFIXES this IS read from config, because it varies per project
# and is not a security boundary: the worst a bad entry can do is let a PR be
# larger than intended, which a human still has to approve.
DEFAULT_SIZE_EXEMPT = ("*.lock", "*.lockb", "package-lock.json")


def size_exempt_patterns(cfg: dict) -> tuple[str, ...]:
    return tuple(cfg.get("size_exempt_paths", [])) + DEFAULT_SIZE_EXEMPT


def sh(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True,
                          check=True, cwd=REPO_ROOT).stdout


def changed_files(base: str, head: str) -> list[str]:
    out = sh("git", "diff", "--name-only", f"{base}...{head}")
    return [line for line in out.splitlines() if line.strip()]


def diff_size(base: str, head: str, files: list[str],
              exempt: tuple[str, ...] = DEFAULT_SIZE_EXEMPT) -> int:
    """Added + deleted lines, ignoring generated/vendored files."""
    counted = [f for f in files if not _exempt(f, exempt)]
    if not counted:
        return 0
    out = sh("git", "diff", "--numstat", f"{base}...{head}", "--", *counted)
    total = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            added, deleted = parts[0], parts[1]
            # "-" means binary; count it as zero lines, it's caught by file cap
            total += (int(added) if added.isdigit() else 0)
            total += (int(deleted) if deleted.isdigit() else 0)
    return total


def _exempt(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)


def locked_prefixes(cfg: dict) -> tuple[str, ...]:
    """The hard list, plus any project-specific additions from config.

    Config can only ever ADD locks, never remove one — so a project can protect
    its own lint config or deploy manifest without any config being able to
    unlock the loop's own machinery. (And since `.timbz/` is in the hard list,
    a loop PR can't edit the additions either.)
    """
    return LOCKED_PREFIXES + tuple(cfg.get("extra_locked_paths", []))


def is_locked(path: str, extra: tuple[str, ...] = ()) -> bool:
    return path.startswith(LOCKED_PREFIXES + tuple(extra))


def is_protected(path: str, protected: list[str]) -> bool:
    return path in protected


# Only this identity can grant clearance. The gate workflow runs in GitHub
# Actions and labels as github-actions[bot]; the local loop runs on a personal
# token and labels as the user. The loop therefore cannot forge a clearance,
# because it cannot become the Actions bot — which is the whole reason this
# check verifies the actor rather than trusting the label's presence.
CLEARANCE_ACTOR = "github-actions[bot]"


def linked_issue(pr_body: Optional[str]) -> Optional[int]:
    """The issue a PR closes — where the clearance lives."""
    if not pr_body:
        return None
    m = re.search(r"\b(?:closes|fixes|resolves)\s+#(\d+)\b", pr_body,
                  re.IGNORECASE)
    return int(m.group(1)) if m else None


def _gh_api(path: str) -> Optional[list]:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        return None
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "timbz-guard"})
    try:
        # noqa justification: the URL is built from a hardcoded https api.github.com
        # base; `repo` and `issue` come from .timbz/config.json and a digit-only
        # regex match, so no scheme or host can be injected here.
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
            return json.loads(resp.read())
    except (urllib.error.URLError, ValueError, TimeoutError):
        return None


def clearance_granted(repo: str, issue: Optional[int], label: str) -> bool:
    """Did a real Discord 🚀 clear this issue for protected-path work?

    Fails closed on every uncertainty — no issue linked, no token, network
    error, label applied by anyone other than the gate.
    """
    if not issue or not repo:
        return False
    events = _gh_api(f"/repos/{repo}/issues/{issue}/timeline?per_page=100")
    if events is None:
        return False
    for ev in events:
        if (ev.get("event") == "labeled"
                and (ev.get("label") or {}).get("name") == label
                and (ev.get("actor") or {}).get("login") == CLEARANCE_ACTOR):
            return True
    return False


def check(files: list[str], lines: int, cfg: dict,
          cleared: bool = False) -> list[str]:
    """Return a list of violations. Empty means the PR is within its rules.

    `cleared` means an authorised approver reacted 🚀 on this issue in Discord,
    which authorises protected-path work for this issue only. It never unlocks
    the self-modification lockout or the size caps.
    """
    violations = []
    limits = cfg.get("limits", {})
    protected = cfg.get("protected_paths", [])

    locked_hits = sorted(p for p in files
                         if is_locked(p, cfg.get("extra_locked_paths", [])))
    if locked_hits:
        violations.append(
            "Self-modification lockout (guardrail 1): a loop PR may not change "
            "the loop's own configuration, skills, workflows or CI.\n"
            "      Offending paths: " + ", ".join(locked_hits) + "\n"
            "      Changes to the loop are a human job, on a non-`timbz/` branch.")

    protected_hits = sorted(p for p in files if is_protected(p, protected))
    if protected_hits and not cleared:
        violations.append(
            "Protected path (guardrail 2): a bug in these files costs real "
            "money, corrupts real data, or leaks a credential, so the loop may "
            "not change them on its own.\n"
            "      Offending paths: " + ", ".join(protected_hits) + "\n"
            "      A 🚀 on the linked issue in Discord clears this. The "
            "clearance is verified against the identity that applied it "
            "(github-actions[bot]), so it can only come from a real reaction.")

    max_files = limits.get("max_changed_files", 8)
    counted_files = [f for f in files if not _exempt(f, size_exempt_patterns(cfg))]
    if len(counted_files) > max_files:
        violations.append(
            f"Size cap (guardrail 3): {len(counted_files)} files changed, "
            f"limit is {max_files}. Split the issue.")

    max_lines = limits.get("max_changed_lines", 400)
    if lines > max_lines:
        violations.append(
            f"Size cap (guardrail 3): {lines} lines changed, limit is "
            f"{max_lines}. Split the issue.")

    return violations


def config_integrity(cfg: dict) -> list[str]:
    """The config's locked_paths must not have drifted below the hard list."""
    declared = set(cfg.get("locked_paths", []))
    missing = [p for p in locked_prefixes(cfg)
               if not any(d.startswith(p) or p.startswith(d) for d in declared)]
    if missing:
        return [f"`.timbz/config.json` locked_paths no longer covers: "
                f"{', '.join(missing)} (the hard list in timbz_guard.py wins, "
                f"but the drift should be fixed)"]
    return []


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Timbz Loop guardrail check")
    ap.add_argument("--base", default=None)
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--branch", default=None)
    ap.add_argument("--pr-body", default="",
                    help="PR body, used to find the linked issue's clearance")
    args = ap.parse_args(argv)

    branch = args.branch or os.environ.get("GITHUB_HEAD_REF", "")
    base = args.base or f"origin/{os.environ.get('GITHUB_BASE_REF', 'main')}"

    with open(CONFIG_PATH) as fh:
        cfg = json.load(fh)

    prefix = cfg.get("github", {}).get("branch_prefix", "timbz/")
    if not branch.startswith(prefix):
        print(f"'{branch or '(unknown)'}' is not a loop branch — "
              f"guardrails do not apply.")
        return 0

    files = changed_files(base, args.head)
    lines = diff_size(base, args.head, files, size_exempt_patterns(cfg))
    print(f"Loop branch '{branch}': {len(files)} file(s), {lines} line(s) "
          f"changed vs {base}")

    issue = linked_issue(args.pr_body)
    cleared = clearance_granted(cfg.get("github", {}).get("repo", ""), issue,
                                cfg.get("labels", {}).get("cleared",
                                                          "timbz:cleared"))
    if issue:
        print(f"Linked issue #{issue}: "
              + ("🚀 cleared for protected paths by an approver reaction"
                 if cleared else "no clearance"))

    violations = check(files, lines, cfg, cleared) + config_integrity(cfg)

    if not violations:
        print("✅ Within guardrails.")
        return 0

    print("\n❌ Guardrail violations:\n", file=sys.stderr)
    for v in violations:
        print(f"  - {v}\n", file=sys.stderr)
    print("See .timbz/guardrails.md.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
