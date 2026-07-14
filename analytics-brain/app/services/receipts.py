"""
The Decision Ledger — a tamper-evident record of every autopilot lifecycle
event, chained per merchant.

Unlike a one-shot CLI tool's audit log (write once, done), Elevate's
autopilot runs continuously for the store's whole life, and the store
already has a primary record of what happened: AgentActionDB. So this
ledger's job isn't to be a second copy of that history — it's to make the
EXISTING history tamper-evident. Each entry attests to a row's real field
values at the moment of a status transition (not a separately-authored
copy), so a later check can recompute the hash from the row as it exists
in the DB right now and catch a silent edit to history, not just a
reordered or deleted log entry.

Also unlike a local CLI's JSONL file: this runs on Alibaba Cloud Function
Compute, where local disk does not survive between invocations. Postgres
is the only honest place for this to live.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.core.config import get_settings
from app.models.db_models import ReceiptDB, AgentActionDB

logger = logging.getLogger(__name__)

GENESIS_HASH = "genesis"


def _canonical_json(obj: dict) -> str:
    """Deterministic serialization — same body always hashes the same way,
    regardless of dict key insertion order."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _hmac_key() -> bytes:
    """A dedicated signing key if one is configured; otherwise a key
    domain-separated from jwt_secret (never jwt_secret reused directly —
    a different secret for a different purpose) so this doesn't force a
    new mandatory env var just to ship the ledger."""
    settings = get_settings()
    if settings.receipt_hmac_secret:
        return settings.receipt_hmac_secret.encode()
    return hashlib.sha256(f"{settings.jwt_secret}:receipts".encode()).digest()


def _entry_hash(prev_hash: str, body: dict) -> str:
    return hashlib.sha256(f"{prev_hash}|{_canonical_json(body)}".encode()).hexdigest()


def _sign(entry_hash: str) -> str:
    return hmac.new(_hmac_key(), entry_hash.encode(), hashlib.sha256).hexdigest()


def _row_body(row: AgentActionDB) -> dict:
    """The real, current field values being attested to — not a
    separately-authored summary. A future consistency check recomputes
    this from the row as it exists then, and compares to what's stored
    here now."""
    return {
        "action_id": row.id,
        "status": row.status,
        "action_type": row.action_type,
        "payload": row.payload,
        "constraint_check": row.constraint_check,
        "brand_check": row.brand_check,
    }


async def append_receipt(
    db: "AsyncSession",
    merchant_id: str,
    event_type: str,
    *,
    action_row: AgentActionDB | None = None,
    note: str = "",
) -> ReceiptDB | None:
    """Append one entry to this merchant's ledger. Never raises — an audit
    trail write failing must not block the real decision/approval flow it's
    observing, same discipline as outcome_observer elsewhere in this codebase.

    Pass `action_row` whenever a real AgentActionDB row exists for this
    event (proposed, approved, dismissed, executed, blocked_at_execution) —
    the entry attests to that row's actual content. Pass only `note` for
    the one case with no row at all: a proposal blocked at decision time,
    before any AgentActionDB row is ever created.
    """
    try:
        last = await db.scalar(
            select(ReceiptDB)
            .where(ReceiptDB.merchant_id == merchant_id)
            .order_by(ReceiptDB.sequence.desc())
            .limit(1)
        )
        prev_hash = last.entry_hash if last else GENESIS_HASH
        sequence = (last.sequence + 1) if last else 0

        body = _row_body(action_row) if action_row is not None else {"note": note}
        entry_hash = _entry_hash(prev_hash, body)

        receipt = ReceiptDB(
            id=str(uuid4()),
            merchant_id=merchant_id,
            sequence=sequence,
            event_type=event_type,
            action_id=action_row.id if action_row is not None else None,
            body=body,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
            signature=_sign(entry_hash),
            created_at=int(time.time() * 1000),
        )
        db.add(receipt)
        await db.flush()
        return receipt
    except Exception as e:  # noqa: BLE001 — the ledger must never block the real flow
        logger.warning("[receipts] failed to append %s receipt for %s: %s", event_type, merchant_id, e)
        return None


def verify_chain(receipts: list[ReceiptDB]) -> tuple[bool, str | None]:
    """Pure chain-integrity check: hash linkage + signatures, in sequence
    order. Catches reordering, deletion, or insertion of receipts. Does NOT
    check whether the underlying AgentActionDB rows still match what was
    attested — that's verify_row_consistency, a separate, DB-coupled check,
    since it needs live rows to compare against."""
    if not receipts:
        return True, None
    ordered = sorted(receipts, key=lambda r: r.sequence)
    expected_prev = GENESIS_HASH
    for r in ordered:
        if r.prev_hash != expected_prev:
            return False, f"sequence {r.sequence}: prev_hash mismatch (chain broken or reordered)"
        recomputed = _entry_hash(r.prev_hash, r.body)
        if recomputed != r.entry_hash:
            return False, f"sequence {r.sequence}: entry_hash mismatch (body was altered after signing)"
        if _sign(r.entry_hash) != r.signature:
            return False, f"sequence {r.sequence}: signature invalid (entry_hash or signature was tampered with)"
        expected_prev = r.entry_hash
    return True, None


async def verify_row_consistency(db: "AsyncSession", receipts: list[ReceiptDB]) -> list[str]:
    """For every receipt that attests to a real AgentActionDB row, recompute
    the attested body from the row's CURRENT content and compare. Returns a
    list of human-readable mismatches (empty means every still-existing row
    matches what the ledger attested at the time). This is the check unique
    to a continuously-operating store: it catches someone quietly editing
    history in the merchant's own database after the fact, not just
    tampering with the receipt log itself."""
    mismatches: list[str] = []
    for r in receipts:
        if r.action_id is None:
            continue
        row = await db.get(AgentActionDB, r.action_id)
        if row is None:
            mismatches.append(f"sequence {r.sequence}: action {r.action_id} no longer exists")
            continue
        if _row_body(row) != r.body:
            mismatches.append(
                f"sequence {r.sequence}: action {r.action_id} content has changed since this receipt was written"
            )
    return mismatches


async def load_ledger(db: "AsyncSession", merchant_id: str) -> list[ReceiptDB]:
    result = await db.execute(
        select(ReceiptDB)
        .where(ReceiptDB.merchant_id == merchant_id)
        .order_by(ReceiptDB.sequence.asc())
    )
    return list(result.scalars().all())
