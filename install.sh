#!/usr/bin/env bash
#
# Install the Timbz Loop into a target repository.
#
#   ./install.sh /path/to/your/repo
#
# Copies the loop runtime (skills, scripts, tests, guardrails, gate workflow)
# and, for anything project-specific, drops a template only if the file isn't
# already there. Re-running upgrades the runtime without clobbering your
# tailored config, project card or rubric.
#
# Afterwards: run /timbz-init in Claude Code in the target repo, then follow
# .timbz/SETUP.md.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DST="${1:-}"

if [[ -z "$DST" ]]; then
  echo "usage: ./install.sh /path/to/your/repo" >&2
  exit 64
fi
if [[ ! -d "$DST" ]]; then
  echo "error: $DST is not a directory" >&2
  exit 66
fi
if [[ ! -d "$DST/.git" ]]; then
  echo "error: $DST is not a git repository." >&2
  echo "The loop drives everything through git and GitHub — run 'git init' first." >&2
  exit 66
fi

echo "Installing the Timbz Loop into $DST"
echo

# --- runtime: always overwritten, this is the upgradeable part ---------------

copy_runtime() {
  local rel="$1"
  mkdir -p "$DST/$(dirname "$rel")"
  cp -R "$SRC/loop/$rel" "$DST/$rel"
  echo "  runtime   $rel"
}

copy_runtime ".claude/skills/timbz-ideate"
copy_runtime ".claude/skills/timbz-spec"
copy_runtime ".claude/skills/timbz-build"
copy_runtime ".claude/skills/timbz-review"
copy_runtime ".claude/skills/timbz-ship"
copy_runtime ".claude/skills/timbz-init"
copy_runtime ".claude/commands/timbz.md"
copy_runtime ".timbz/guardrails.md"
copy_runtime ".timbz/SETUP.md"
copy_runtime "scripts/timbz_discord.py"
copy_runtime "scripts/timbz_gate.py"
copy_runtime "scripts/timbz_guard.py"
copy_runtime "scripts/timbz_manifest.py"
copy_runtime "tests/test_timbz_gate.py"
copy_runtime "tests/test_timbz_guard.py"
copy_runtime "tests/test_timbz_manifest.py"
copy_runtime ".github/workflows/timbz-gate.yml"

# --- templates: never overwritten, these are yours ---------------------------

echo
copy_template() {
  local from="$1" to="$2"
  if [[ -e "$DST/$to" ]]; then
    echo "  keeping   $to (already present)"
    return
  fi
  mkdir -p "$DST/$(dirname "$to")"
  cp "$SRC/templates/$from" "$DST/$to"
  echo "  template  $to"
}

copy_template ".timbz/config.json"  ".timbz/config.json"
copy_template ".timbz/project.md"   ".timbz/project.md"
copy_template ".timbz/rubric.md"    ".timbz/rubric.md"

# CI is the loop's verification gate — without it nothing can ever be approved.
if [[ -e "$DST/.github/workflows/ci.yml" ]]; then
  echo "  keeping   .github/workflows/ci.yml (already present)"
  echo
  echo "  ! Your existing CI needs the 'guardrails' job added, or the"
  echo "    self-modification lockout is only a prompt. /timbz-init will do it."
else
  if [[ -f "$DST/package.json" ]]; then
    cp "$SRC/templates/ci/node.yml" "$DST/.github/workflows/ci.yml"
    echo "  template  .github/workflows/ci.yml (node — tailor it)"
  else
    cp "$SRC/templates/ci/python.yml" "$DST/.github/workflows/ci.yml"
    echo "  template  .github/workflows/ci.yml (python — tailor it)"
  fi
fi

# --- .env must not be committed; the bot token lives there --------------------

echo
if [[ -f "$DST/.gitignore" ]] && grep -qE '^\.env$|^\.env\b' "$DST/.gitignore"; then
  echo "  ok        .env is gitignored"
else
  echo "  ! .env is NOT in .gitignore — add it before storing the Discord bot"
  echo "    token there, or you will commit a credential."
fi

cat <<'EOF'

Installed.

Next:
  1. In Claude Code, in that repo:   /timbz-init
     Reads your codebase and writes the project card, rubric, protected paths
     and CI. Correct anything it guessed wrong — it says what it guessed.
  2. Then follow .timbz/SETUP.md for the Discord bot, secrets and labels.
  3. Dry run, then:                  /loop 20m /timbz

Nothing runs until you finish step 2 — the gate is inert with no approvers
configured, by design.
EOF
