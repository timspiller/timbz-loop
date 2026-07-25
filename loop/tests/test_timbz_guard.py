"""Tests for the loop's CI guardrail check.

`scripts/timbz_guard.py` is what turns `.timbz/guardrails.md` from a prompt the
loop could talk itself out of into a red X on the PR. These tests are the proof
that the lockout actually holds.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from timbz_guard import (  # noqa: E402
    LOCKED_PREFIXES,
    check,
    config_integrity,
    is_locked,
    is_protected,
)


@pytest.fixture
def cfg():
    return {
        "limits": {"max_changed_lines": 400, "max_changed_files": 8},
        "protected_paths": ["src/billing.py", "src/auth.py"],
        "size_exempt_paths": ["dist/*", "vendor/*"],
        "extra_locked_paths": ["ruff.toml", "railway.toml"],
        "locked_paths": list(LOCKED_PREFIXES) + ["ruff.toml", "railway.toml"],
    }


# -- the self-modification lockout ------------------------------------------


@pytest.mark.parametrize("path", [
    ".timbz/config.json",
    ".timbz/guardrails.md",
    ".timbz/rubric.md",
    ".claude/skills/timbz-build/SKILL.md",
    ".claude/commands/timbz.md",
    ".github/workflows/ci.yml",
    ".github/workflows/timbz-gate.yml",
    "scripts/timbz_gate.py",
    "scripts/timbz_guard.py",
    ".env",
    ".env.example",
    ".gitignore",
])
def test_loop_cannot_touch_its_own_machinery(path):
    """The universal set — locked in every project, no config required."""
    assert is_locked(path), f"{path} must be locked against the loop"


@pytest.mark.parametrize("path", ["ruff.toml", "railway.toml"])
def test_project_specific_locks_come_from_config(cfg, path):
    """This project also locks its lint config and deploy manifest, so the loop
    can't weaken its own gate or change how the app ships."""
    assert not is_locked(path), f"{path} is a per-project lock, not universal"
    assert any("Self-modification lockout" in v for v in check([path], 5, cfg))


def test_config_can_only_add_locks_never_remove_them(cfg):
    """A config claiming nothing is locked must still not unlock the core set."""
    cfg["extra_locked_paths"] = []
    assert any("Self-modification lockout" in v
               for v in check([".timbz/config.json"], 5, cfg))


@pytest.mark.parametrize("path", [
    "src/api.py",
    "src/ui/dashboard.js",
    "src/styles.css",
    "tests/test_api.py",
    "README.md",
    "scripts/build_something.py",  # a non-timbz script is ordinary code
])
def test_ordinary_app_code_is_not_locked(path):
    assert not is_locked(path)


def test_guard_locks_itself(cfg):
    """The checker must be inside its own locked set, or the loop could simply
    rewrite the checker and then do as it pleases."""
    violations = check(["scripts/timbz_guard.py"], 10, cfg)
    assert any("Self-modification lockout" in v for v in violations)


def test_locked_violation_names_the_offending_paths(cfg):
    violations = check([".timbz/config.json", "src/api.py"], 10, cfg)
    assert any(".timbz/config.json" in v for v in violations)


def test_disabling_ci_in_the_same_pr_is_blocked(cfg):
    """The obvious attack: weaken the checks and use the weakened checks."""
    violations = check([".github/workflows/ci.yml"], 5, cfg)
    assert any("Self-modification lockout" in v for v in violations)


# -- protected app paths -----------------------------------------------------


def test_protected_path_is_blocked(cfg):
    violations = check(["src/billing.py"], 20, cfg)
    assert any("Protected path" in v for v in violations)


def test_protected_path_has_no_label_override(cfg):
    """There is deliberately no unlock flag — the loop holds a token that could
    apply any label to itself, so the only real gate is the branch name."""
    violations = check(["src/auth.py"], 20, cfg)
    assert any("non-`timbz/` branch" in v for v in violations)


def test_is_protected_is_exact_not_prefix(cfg):
    assert is_protected("src/auth.py", cfg["protected_paths"])
    assert not is_protected("src/auth_helpers.py", cfg["protected_paths"])
    assert not is_protected("tests/test_auth.py", cfg["protected_paths"])


def test_unprotected_app_code_passes(cfg):
    assert check(["src/api.py", "src/ui/panel.js"], 120, cfg) == []


# -- size caps ---------------------------------------------------------------


def test_line_cap_enforced(cfg):
    violations = check(["src/api.py"], 401, cfg)
    assert any("401 lines changed" in v for v in violations)


def test_line_cap_boundary_is_inclusive(cfg):
    assert check(["src/api.py"], 400, cfg) == []


def test_file_cap_enforced(cfg):
    files = [f"src/f{i}.js" for i in range(9)]
    violations = check(files, 50, cfg)
    assert any("9 files changed" in v for v in violations)


def test_generated_css_does_not_count_against_the_file_cap(cfg):
    """Build output is real but not hand-written — counting it would make any
    style change look like a sprawling PR."""
    files = [f"src/f{i}.js" for i in range(8)] + ["dist/bundle.css"]
    assert check(files, 50, cfg) == []


def test_vendored_code_is_exempt(cfg):
    files = ["vendor/x.js"] * 20
    assert check(files, 50, cfg) == []


def test_all_violations_reported_together(cfg):
    """One CI run should tell you everything that's wrong, not the first thing."""
    violations = check([".timbz/config.json", "src/billing.py"], 900, cfg)
    assert len(violations) == 3


# -- config drift ------------------------------------------------------------


def test_config_integrity_passes_on_the_real_config():
    with open(REPO_ROOT / ".timbz" / "config.json") as fh:
        real = json.load(fh)
    assert config_integrity(real) == []


def test_size_exemptions_come_from_config_not_the_checker(cfg):
    """Exempt paths vary per project, so they're configurable — unlike the lock
    list, a wrong entry here only makes a PR bigger than intended, and a human
    still has to approve it."""
    cfg["size_exempt_paths"] = []
    files = [f"src/f{i}.js" for i in range(8)] + ["dist/bundle.css"]
    assert any("9 files changed" in v for v in check(files, 50, cfg))


def test_lockfiles_are_always_exempt_even_with_empty_config(cfg):
    cfg["size_exempt_paths"] = []
    files = [f"src/f{i}.js" for i in range(8)] + ["package-lock.json", "uv.lock"]
    assert check(files, 50, cfg) == []


def test_config_integrity_notices_a_weakened_lock_list():
    weakened = {"locked_paths": [".timbz/"]}  # dropped .github/, scripts/, …
    assert config_integrity(weakened)


def test_hard_list_is_authoritative_even_if_config_lies(cfg):
    """The lock list in the checker is hardcoded, not read from config, so a
    config that claims nothing is locked changes nothing."""
    cfg["locked_paths"] = []
    violations = check([".github/workflows/ci.yml"], 5, cfg)
    assert any("Self-modification lockout" in v for v in violations)
