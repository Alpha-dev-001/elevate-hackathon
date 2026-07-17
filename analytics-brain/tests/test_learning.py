"""Per-role learning signal — the measurable half of the cognitive loop.

Each QwenRole accrues a quantified stance from how the merchant has actually
resolved that role's past proposals: how many were kept vs dismissed, and — for
discount-bearing roles — the discount level the merchant keeps vs the level they
reject. That stance is rendered into a directive injected into the role's next
prompt, so proposals measurably shift toward what this specific store accepts.
A stateless one-shot agent cannot produce any of this; it has no yesterday.

These tests pin the pure aggregation + rendering. The async DB glue
(load_role_learning) is thin and covered by the integration suite.
"""
from app.services.learning import (
    MIN_SIGNAL,
    RoleLearning,
    compute_role_learning,
    render_learned_stance,
)


def _rec(status, behavior=None, discount=None):
    payload = {}
    if discount is not None:
        payload["discount_percent"] = discount
    return {"status": status, "merchant_behavior": behavior, "payload": payload}


# ── Signal threshold ───────────────────────────────────────────────────────

def test_below_min_signal_yields_no_stance():
    recs = [_rec("approved", "approved")] * (MIN_SIGNAL - 1)
    learning = compute_role_learning(recs, "pricing_strategist")
    assert not learning.has_signal
    assert render_learned_stance(learning) == ""


def test_pending_actions_are_not_counted_as_resolved():
    recs = [_rec("pending")] * 5
    learning = compute_role_learning(recs, "pricing_strategist")
    assert learning.n_resolved == 0
    assert render_learned_stance(learning) == ""


# ── Classification ─────────────────────────────────────────────────────────

def test_approval_rate_computed_from_kept_vs_dismissed():
    recs = [
        _rec("approved", "approved"),
        _rec("executed"),
        _rec("approved", "approved"),
        _rec("dismissed", "dismissed"),
    ]
    learning = compute_role_learning(recs, "pricing_strategist")
    assert learning.n_resolved == 4
    assert learning.n_approved == 3
    assert learning.n_dismissed == 1
    assert learning.approval_rate == 0.75


def test_executed_status_counts_as_approved():
    learning = compute_role_learning([_rec("executed")] * 3, "pricing_strategist")
    assert learning.n_approved == 3


def test_approved_then_modified_counts_as_approved():
    recs = [_rec("approved", "approved_then_modified")] * 3
    learning = compute_role_learning(recs, "sales_rep")
    assert learning.n_approved == 3


# ── The discount-gap directive: proposals shift toward what's kept ─────────

def test_discount_gap_produces_a_lead_with_directive():
    recs = [
        _rec("approved", "approved", discount=8),
        _rec("executed", discount=10),
        _rec("dismissed", "dismissed", discount=30),
        _rec("dismissed", "dismissed", discount=40),
    ]
    learning = compute_role_learning(recs, "pricing_strategist")
    assert learning.approved_avg_discount == 9
    assert learning.dismissed_avg_discount == 35
    stance = render_learned_stance(learning)
    assert "lead with about 9%" in stance
    assert "2 of 4" in stance  # 2 kept out of 4 resolved


def test_small_discount_gap_does_not_trigger_the_directive():
    # 11 kept vs 12 dismissed: within noise, no confident "lead with" claim.
    recs = [
        _rec("approved", "approved", discount=11),
        _rec("approved", "approved", discount=11),
        _rec("dismissed", "dismissed", discount=12),
    ]
    stance = render_learned_stance(compute_role_learning(recs, "pricing_strategist"))
    assert "lead with about" not in stance


# ── Approval-rate stances for roles without a discount lever ───────────────

def test_high_approval_rate_says_stay_the_course():
    learning = compute_role_learning([_rec("approved", "approved")] * 4, "inventory_overseer")
    stance = render_learned_stance(learning)
    assert "stay the course" in stance


def test_low_approval_rate_warns_to_be_selective():
    recs = [_rec("approved", "approved")] + [_rec("dismissed", "dismissed")] * 3
    learning = compute_role_learning(recs, "inventory_overseer")
    assert learning.approval_rate == 0.25
    stance = render_learned_stance(learning)
    assert "strong signal" in stance


def test_stance_names_the_role_and_the_counts():
    learning = compute_role_learning([_rec("approved", "approved")] * 3, "sales_rep")
    stance = render_learned_stance(learning)
    assert "sales_rep" in stance
    assert "3 of 3" in stance


# ── Priority arbitration — reuses RoleLearning, doesn't reinvent it ────────

from app.services.learning import compute_effective_priority


class TestComputeEffectivePriority:
    def test_no_learning_returns_default(self):
        assert compute_effective_priority(20, None) == 20

    def test_below_min_signal_returns_default(self):
        learning = compute_role_learning([_rec("approved", "approved")] * (MIN_SIGNAL - 1), "pricing_strategist")
        assert compute_effective_priority(20, learning) == 20

    def test_high_approval_rate_adds_bonus(self):
        learning = compute_role_learning([_rec("approved", "approved")] * 3, "pricing_strategist")
        assert compute_effective_priority(20, learning) == 30

    def test_low_approval_rate_subtracts_penalty(self):
        learning = compute_role_learning([_rec("dismissed", "dismissed")] * 3, "pricing_strategist")
        assert compute_effective_priority(20, learning) == 10

    def test_mixed_rate_with_signal_stays_at_default(self):
        # 4 resolved (above MIN_SIGNAL) at a genuine 0.5 rate — between the
        # 0.34/0.75 boundaries — so this exercises the real "mixed rate"
        # branch, not the below-signal short-circuit test_below_min_signal
        # already covers. (Two records would return default via has_signal,
        # never touching the rate comparison at all.)
        recs = [_rec("approved", "approved")] * 2 + [_rec("dismissed", "dismissed")] * 2
        learning = compute_role_learning(recs, "pricing_strategist")
        assert compute_effective_priority(20, learning) == 20
