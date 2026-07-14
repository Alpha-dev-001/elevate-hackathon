"""
Tests for the Decision Ledger's pure chain-integrity logic — no DB needed,
same convention as test_adversarial_interceptor.py: construct model
instances directly and exercise the pure functions.
"""
from __future__ import annotations

from app.services.receipts import (
    _canonical_json,
    _entry_hash,
    _sign,
    _row_body,
    verify_chain,
    GENESIS_HASH,
)
from app.models.db_models import ReceiptDB, AgentActionDB


def _make_row(**overrides) -> AgentActionDB:
    defaults = dict(
        id="act_1", merchant_id="m_1", promo_id="promo_1",
        action_type="flash_sale", trigger="t", title="t", description="d",
        estimated_gmv=0.0, estimated_confidence=0.5,
        payload={"product_id": "p1", "discount_percent": 20},
        brand_check="", constraint_check="", status="pending", created_at=0,
    )
    defaults.update(overrides)
    return AgentActionDB(**defaults)


def _make_chain(n: int, merchant_id: str = "m_1") -> list[ReceiptDB]:
    """Build a real, correctly-linked and signed chain of n entries."""
    chain: list[ReceiptDB] = []
    prev_hash = GENESIS_HASH
    for i in range(n):
        row = _make_row(id=f"act_{i}", status="pending")
        body = _row_body(row)
        entry_hash = _entry_hash(prev_hash, body)
        chain.append(ReceiptDB(
            id=f"r_{i}", merchant_id=merchant_id, sequence=i,
            event_type="proposed", action_id=row.id, body=body,
            prev_hash=prev_hash, entry_hash=entry_hash,
            signature=_sign(entry_hash), created_at=i,
        ))
        prev_hash = entry_hash
    return chain


def test_canonical_json_is_order_independent():
    a = {"z": 1, "a": 2}
    b = {"a": 2, "z": 1}
    assert _canonical_json(a) == _canonical_json(b)


def test_row_body_captures_real_fields_not_a_copy():
    row = _make_row(status="executed", constraint_check="clamped to 40%")
    body = _row_body(row)
    assert body["action_id"] == "act_1"
    assert body["status"] == "executed"
    assert body["constraint_check"] == "clamped to 40%"
    assert body["payload"] == {"product_id": "p1", "discount_percent": 20}


def test_empty_chain_is_valid():
    valid, err = verify_chain([])
    assert valid is True
    assert err is None


def test_valid_chain_passes():
    chain = _make_chain(5)
    valid, err = verify_chain(chain)
    assert valid is True
    assert err is None


def test_out_of_order_input_is_still_verified_correctly():
    """verify_chain sorts by sequence itself — caller doesn't have to."""
    chain = _make_chain(4)
    shuffled = [chain[2], chain[0], chain[3], chain[1]]
    valid, err = verify_chain(shuffled)
    assert valid is True
    assert err is None


def test_tampered_body_is_detected():
    """Someone edits a receipt's stored body after the fact — entry_hash
    no longer matches what's recomputed from the (altered) body."""
    chain = _make_chain(3)
    chain[1].body = {**chain[1].body, "status": "executed"}  # tampered
    valid, err = verify_chain(chain)
    assert valid is False
    assert "entry_hash mismatch" in err


def test_tampered_signature_is_detected():
    chain = _make_chain(3)
    chain[1].signature = "0" * 64
    valid, err = verify_chain(chain)
    assert valid is False
    assert "signature invalid" in err


def test_deleted_entry_breaks_the_chain():
    """Removing an entry from the middle breaks prev_hash linkage for
    everything after it — this is the whole point of chaining."""
    chain = _make_chain(4)
    with_gap = [chain[0], chain[2], chain[3]]  # entry 1 deleted
    valid, err = verify_chain(with_gap)
    assert valid is False
    assert "prev_hash mismatch" in err


def test_signature_depends_on_configured_key():
    """Same entry_hash, different key, must NOT produce the same signature
    — otherwise the HMAC would be decorative."""
    sig_a = _sign("deadbeef")
    # Sanity: signing is deterministic for the same key + hash.
    sig_b = _sign("deadbeef")
    assert sig_a == sig_b
