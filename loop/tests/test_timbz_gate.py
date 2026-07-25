"""Tests for the Timbz Loop approval gate.

`resolve_action` and `merge_blockers` are the two functions in this repo that
can cause a merge to production. Everything here is a "does it fail closed?"
test: the interesting cases are the ones where the gate must decline.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from timbz_gate import (  # noqa: E402
    merge_blockers,
    parse_marker,
    resolve_action,
)

TIM = "111111111111111111"
STRANGER = "222222222222222222"
BOT = "999999999999999999"


@pytest.fixture
def cfg():
    return {
        "enabled": True,
        "discord": {
            "channel_id": "555",
            "bot_user_id": BOT,
            "approver_user_ids": [TIM],
        },
        "emoji": {
            "idea": {"🚀": "promote", "👎": "kill"},
            "ship": {"✅": "merge", "🔁": "revise", "❌": "reject", "👀": "hold"},
        },
        "github": {"branch_prefix": "timbz/", "base_branch": "main"},
        "labels": {},
    }


SHIP = {"kind": "ship", "pr": 7, "message_id": "1"}
IDEA = {"kind": "idea", "issue": 7, "message_id": "1"}


# -- who is allowed to decide ----------------------------------------------


def test_approver_reaction_decides(cfg):
    got = resolve_action(SHIP, {"✅": [TIM]}, cfg)
    assert got == {"action": "merge", "emoji": "✅", "by": TIM}


def test_stranger_in_the_channel_cannot_merge(cfg):
    """Anyone who can see the channel can react. Only approvers count."""
    assert resolve_action(SHIP, {"✅": [STRANGER]}, cfg) is None


def test_bot_own_seeded_reaction_is_not_approval(cfg):
    """The bot pre-seeds every emoji so approving is one tap — if its own
    reaction counted, every post would merge itself the moment it was made."""
    assert resolve_action(SHIP, {"✅": [BOT]}, cfg) is None


def test_bot_id_wins_even_if_bot_is_listed_as_approver(cfg):
    cfg["discord"]["approver_user_ids"] = [TIM, BOT]
    assert resolve_action(SHIP, {"✅": [BOT]}, cfg) is None
    assert resolve_action(SHIP, {"✅": [BOT, TIM]}, cfg)["by"] == TIM


def test_approver_among_strangers_still_decides(cfg):
    assert resolve_action(SHIP, {"✅": [STRANGER, TIM]}, cfg)["action"] == "merge"


# -- fail-closed conditions -------------------------------------------------


def test_kill_switch_stops_everything(cfg):
    cfg["enabled"] = False
    assert resolve_action(SHIP, {"✅": [TIM]}, cfg) is None


def test_no_approvers_configured_means_nobody_can_approve(cfg):
    cfg["discord"]["approver_user_ids"] = []
    assert resolve_action(SHIP, {"✅": [TIM]}, cfg) is None


def test_no_reactions_is_no_decision(cfg):
    assert resolve_action(SHIP, {}, cfg) is None


def test_unrecognised_emoji_is_not_a_signal(cfg):
    assert resolve_action(SHIP, {"🎉": [TIM], "🔥": [TIM]}, cfg) is None


def test_unknown_kind_is_ignored(cfg):
    assert resolve_action({"kind": "nonsense"}, {"✅": [TIM]}, cfg) is None


def test_ship_emoji_on_an_idea_post_does_nothing(cfg):
    """✅ has no meaning on an idea post; only 🚀 / 👎 do."""
    assert resolve_action(IDEA, {"✅": [TIM]}, cfg) is None


# -- precedence: the most conservative answer wins ---------------------------


@pytest.mark.parametrize("reactions,expected", [
    ({"✅": [TIM], "❌": [TIM]}, "reject"),
    ({"✅": [TIM], "👀": [TIM]}, "hold"),
    ({"✅": [TIM], "🔁": [TIM]}, "revise"),
    ({"🔁": [TIM], "❌": [TIM]}, "reject"),
    ({"✅": [TIM], "🔁": [TIM], "👀": [TIM], "❌": [TIM]}, "reject"),
])
def test_conflicting_reactions_take_the_safest_action(cfg, reactions, expected):
    """Changing your mind by adding an emoji must never upgrade to a merge."""
    assert resolve_action(SHIP, reactions, cfg)["action"] == expected


def test_stranger_veto_does_not_count_either(cfg):
    """A stranger's ❌ must not block a merge any more than their ✅ grants one."""
    assert resolve_action(SHIP, {"✅": [TIM], "❌": [STRANGER]}, cfg)["action"] == "merge"


@pytest.mark.parametrize("reactions,expected", [
    ({"🚀": [TIM]}, "promote"),
    ({"👎": [TIM]}, "kill"),
    ({"🚀": [TIM], "👎": [TIM]}, "kill"),
])
def test_idea_post_actions(cfg, reactions, expected):
    assert resolve_action(IDEA, reactions, cfg)["action"] == expected


# -- pre-merge safety checks -------------------------------------------------


def _pr(**over):
    pr = {
        "head": {"ref": "timbz/12-tidy-empty-state", "sha": "abc123"},
        "base": {"ref": "main"},
        "draft": False,
        "mergeable": True,
        "mergeable_state": "clean",
    }
    pr.update(over)
    return pr


GREEN = [("ci", "success"), ("guardrails", "success")]


def test_clean_pr_with_green_checks_has_no_blockers(cfg):
    assert merge_blockers(_pr(), GREEN, cfg) == []


def test_non_loop_branch_is_refused(cfg):
    """Protected-path work happens on human branches; the gate must never be
    able to ship one by emoji."""
    blockers = merge_blockers(_pr(head={"ref": "hotfix/x", "sha": "a"}), GREEN, cfg)
    assert any("not a loop branch" in b for b in blockers)


def test_pr_targeting_another_branch_is_refused(cfg):
    blockers = merge_blockers(_pr(base={"ref": "some-other-branch"}), GREEN, cfg)
    assert any("not 'main'" in b for b in blockers)


def test_draft_is_refused(cfg):
    assert any("draft" in b for b in merge_blockers(_pr(draft=True), GREEN, cfg))


def test_conflicted_pr_is_refused(cfg):
    blockers = merge_blockers(_pr(mergeable=False, mergeable_state="dirty"),
                              GREEN, cfg)
    assert any("not mergeable" in b for b in blockers)


def test_no_checks_at_all_is_refused(cfg):
    """A repo with CI misconfigured must not read as 'nothing failed'."""
    blockers = merge_blockers(_pr(), [], cfg)
    assert any("no CI checks" in b for b in blockers)


def test_failing_check_is_refused(cfg):
    blockers = merge_blockers(_pr(), [("ci", "failure")], cfg)
    assert any("ci (failure)" in b for b in blockers)


def test_still_running_check_is_refused(cfg):
    blockers = merge_blockers(_pr(), [("ci", "pending:in_progress")], cfg)
    assert any("ci (pending:in_progress)" in b for b in blockers)


def test_action_required_check_is_refused(cfg):
    blockers = merge_blockers(_pr(), [("ci", "action_required")], cfg)
    assert any("action_required" in b for b in blockers)


def test_skipped_and_neutral_checks_are_acceptable(cfg):
    assert merge_blockers(_pr(), [("a", "skipped"), ("b", "neutral")], cfg) == []


def test_blockers_accumulate(cfg):
    blockers = merge_blockers(
        _pr(head={"ref": "wip", "sha": "a"}, draft=True), [("ci", "failure")], cfg)
    assert len(blockers) == 3


# -- the Discord pointer stamped into issue/PR bodies ------------------------


def test_marker_round_trip():
    body = 'Some PR body.\n\n<!-- timbz-discord: {"message_id": "12345", "issue": 8} -->'
    assert parse_marker(body) == {"message_id": "12345", "issue": 8}


@pytest.mark.parametrize("body", [
    None,
    "",
    "no marker here",
    '<!-- timbz-discord: {not json} -->',
    '<!-- timbz-discord: {"message_id": "not-a-number"} -->',
    '<!-- timbz-discord: {"issue": 8} -->',
])
def test_unusable_markers_mean_not_pending(body):
    """A malformed pointer must drop the item out of the queue, never make the
    gate guess which message it was supposed to read."""
    assert parse_marker(body) is None
