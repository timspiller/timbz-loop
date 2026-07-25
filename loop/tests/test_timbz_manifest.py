"""Tests for the build-manifest guard.

This check exists because of a real outage: a stray `package.json` at a repo
root flipped Railway's Nixpacks builder from Python to Node and shipped an
image with no Python in it. Every other test passed while production was down.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from timbz_manifest import (  # noqa: E402
    LANGUAGE_MANIFESTS,
    MANIFESTS,
    check,
    load_required,
)

PYTHON = ["requirements.txt"]


@pytest.fixture
def repo(tmp_path):
    """A minimal repo root that should pass."""
    (tmp_path / "requirements.txt").write_text("fastapi>=0.111\n")
    return tmp_path


def test_a_healthy_python_root_passes(repo):
    assert check(repo, PYTHON) == []


def test_the_real_repo_root_passes():
    """The live check, against this repo as it actually is right now."""
    assert check(REPO_ROOT, load_required()) == []


def test_package_json_at_root_is_caught(repo):
    """The exact file that caused the outage."""
    (repo / "package.json").write_text('{"dependencies": {"brew": "^0.0.8"}}')
    problems = check(repo, PYTHON)
    assert any("package.json" in p for p in problems)
    assert any("Node" in p for p in problems)


@pytest.mark.parametrize("name", sorted(set(MANIFESTS) - {"requirements.txt"}))
def test_every_competing_manifest_is_caught(repo, name):
    (repo / name).write_text("{}")
    assert any(name in p for p in check(repo, PYTHON)), f"{name} slipped through"


def test_a_node_project_is_allowed_its_own_package_json(repo):
    """The same check serves any language — what's forbidden is whatever
    competes with what the project declares itself to be."""
    (repo / "package.json").write_text('{"name": "app"}')
    (repo / "requirements.txt").unlink()
    assert check(repo, ["package.json"]) == []


def test_missing_requirements_is_caught(repo):
    """The other direction: if requirements.txt vanishes, Nixpacks has nothing
    to detect and the build breaks just as quietly."""
    (repo / "requirements.txt").unlink()
    assert any("requirements.txt" in p for p in check(repo, PYTHON))


def test_manifests_in_subdirectories_are_fine(repo):
    """A vendored frontend may carry its own package.json. Builders only look
    at the root, so subdirectories must not trip this."""
    sub = repo / "vendor"
    sub.mkdir()
    (sub / "package.json").write_text('{"name": "extension"}')
    assert check(repo, PYTHON) == []


def test_all_problems_reported_at_once(repo):
    """One CI run should name everything wrong, not just the first thing."""
    (repo / "package.json").write_text("{}")
    (repo / "Dockerfile").write_text("FROM python\n")
    (repo / "requirements.txt").unlink()
    assert len(check(repo, PYTHON)) == 3


# -- an undeclared project must not be told its own files are wrong -----------


def test_undeclared_project_does_not_flag_its_own_manifest(repo):
    """A fresh install hasn't run /timbz-init yet. Flagging the repo's own
    requirements.txt because a config field is blank would be wrong, and the
    fastest possible way to teach someone to ignore this check."""
    assert check(repo, []) == []


def test_undeclared_project_still_catches_overrides(repo):
    """A Dockerfile or Procfile replaces the build outright, so it's suspect
    regardless of what language the project turns out to be."""
    (repo / "Dockerfile").write_text("FROM scratch\n")
    assert any("Dockerfile" in p for p in check(repo, []))


def test_declared_project_still_catches_overrides(repo):
    (repo / "Procfile").write_text("web: gunicorn\n")
    assert any("Procfile" in p for p in check(repo, PYTHON))


@pytest.mark.parametrize("name", sorted(LANGUAGE_MANIFESTS))
def test_a_project_may_declare_any_language_as_its_own(repo, name):
    """The check serves any stack: declaring a manifest makes it legitimate."""
    (repo / "requirements.txt").unlink()
    (repo / name).write_text("{}")
    assert check(repo, [name]) == []
