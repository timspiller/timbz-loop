#!/usr/bin/env python3
"""Guard the repo root against files that change how the app gets built.

Written after an outage. A stray `npm install` left a `package.json` at the
root; it got committed; Railway's Nixpacks builder picks its language provider
by what it finds there, chose Node over Python, and shipped an image with no
Python in it. The container came up and died with `uvicorn: command not found`.

Every test passed the whole time. Nothing in the test suite or the lint gate
looks at how the container is assembled, so nothing could have caught it.

This does. It runs on every branch — not just loop branches, because the commit
that caused the outage was written by a human.

    python scripts/timbz_manifest.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / ".timbz" / "config.json"

# Files whose presence at the ROOT makes a builder choose a language provider.
# Subdirectories are fine — a vendored frontend may carry its own package.json,
# and Nixpacks only looks at the root.
#
# Which of these are *forbidden* depends on the project: whatever it declares in
# `build.required_root_files` is what it IS, and every other language manifest
# competes with it.
LANGUAGE_MANIFESTS = {
    "package.json": "Node",
    "package-lock.json": "Node",
    "yarn.lock": "Node",
    "pnpm-lock.yaml": "Node",
    "bun.lockb": "Bun",
    "deno.json": "Deno",
    "go.mod": "Go",
    "Cargo.toml": "Rust",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "mix.exs": "Elixir",
    "pubspec.yaml": "Dart",
    "build.gradle": "Java",
    "pom.xml": "Java",
    "requirements.txt": "Python",
    "pyproject.toml": "Python",
    "Pipfile": "Python",
}

# These don't pick a language — they replace the build or start command outright,
# so they're wrong in any project that didn't ask for them, declared or not.
OVERRIDE_MANIFESTS = {
    "Dockerfile": "Docker — would override the configured builder",
    "Procfile": "overrides the configured start command",
}

MANIFESTS = {**LANGUAGE_MANIFESTS, **OVERRIDE_MANIFESTS}


def load_required(config_path: Path = CONFIG_PATH) -> list[str]:
    """Root files this project legitimately has — what it IS."""
    try:
        with open(config_path) as fh:
            return list(json.load(fh).get("build", {})
                        .get("required_root_files", []))
    except (OSError, ValueError):
        return []


def check(root: Path = REPO_ROOT,
          required: list[str] | None = None) -> list[str]:
    """Return a list of problems. Empty means the build shape is intact."""
    if required is None:
        required = load_required()
    problems = []

    for name in required:
        if not (root / name).exists():
            problems.append(
                f"`{name}` is missing from the repo root. The builder detects "
                f"this project's language from it — without it the image will "
                f"not contain the right runtime.")

    # With nothing declared we cannot know which language manifest is the
    # project's own, so we only police the overrides. Flagging a repo's own
    # requirements.txt because it hasn't filled in a config field would be
    # both wrong and the fastest way to teach someone to ignore this check.
    if required:
        forbidden = {k: v for k, v in LANGUAGE_MANIFESTS.items()
                     if k not in required}
        forbidden.update(OVERRIDE_MANIFESTS)
    else:
        forbidden = dict(OVERRIDE_MANIFESTS)

    for name, why in sorted(forbidden.items()):
        path = root / name
        if path.exists():
            declared = ", ".join(required)
            problems.append(
                f"`{name}` exists at the repo root ({why})"
                + (f", but this project declares itself as {declared}"
                   if declared else "") + ".\n"
                "      The builder picks its language provider from the root, "
                "so this changes what the production image contains.\n"
                "      If it's a stray artifact, delete it. If the project "
                "genuinely needs it, `build.required_root_files` in "
                ".timbz/config.json must be updated too — deliberately, by a "
                "human.")

    return problems


def main() -> int:
    problems = check()
    required = load_required()
    if not required:
        print("⚠️  `build.required_root_files` is not set in "
              ".timbz/config.json — this check can't tell what this project "
              "is, so it is only checking for a Dockerfile/Procfile override.")
    if not problems:
        if required:
            print(f"✅ Build manifest intact: {', '.join(required)} present, "
                  f"no competing language manifests at the root.")
        else:
            print("✅ No build overrides at the root.")
        return 0

    print("\n❌ The repo root would build differently than intended:\n",
          file=sys.stderr)
    for p in problems:
        print(f"  - {p}\n", file=sys.stderr)
    print("This check exists because green tests do not prove the container "
          "is built correctly.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
