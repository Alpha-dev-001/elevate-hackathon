"""
One-time backfill for the ledger-completeness bug fixed in
app/services/decision_engine.py::_dismiss_pending_action: before the fix,
an action auto-dismissed by the stale-TTL or priority-supersede path (as
opposed to a merchant tapping "dismiss") never got a receipt appended, so
verify_row_consistency correctly flags it as a mismatch — the ledger's last
record of that action is stale.

This does NOT rewrite any existing receipt (that would defeat the point of
a tamper-evident ledger). It only APPENDS a new receipt attesting to each
flagged action's CURRENT, real, already-true database state — the receipt
the fixed code would have written at dismiss time, written now instead.
Rows genuinely tampered with post-fix would fail the SAME way after this
runs; this only clears the pre-fix instrumentation gap.

Usage:
    docker compose exec api python -m scripts.backfill_missing_receipts <merchant_id_or_slug> [...]
    docker compose exec api python -m scripts.backfill_missing_receipts --all
"""
import asyncio
import sys

from sqlalchemy import select

from app.core.database import get_session_factory
from app.models.db_models import AgentActionDB, MerchantDB
from app.services.receipts import append_receipt, load_ledger, verify_row_consistency


async def _resolve_merchant(db, merchant_id_or_slug: str) -> str | None:
    merchant = await db.get(MerchantDB, merchant_id_or_slug)
    if merchant:
        return merchant.id
    merchant = await db.scalar(select(MerchantDB).where(MerchantDB.slug == merchant_id_or_slug))
    return merchant.id if merchant else None


async def backfill_one(db, merchant_id: str) -> int:
    receipts = await load_ledger(db, merchant_id)
    mismatches = await verify_row_consistency(db, receipts)
    backfilled = 0
    for m in mismatches:
        if "no longer exists" in m:
            continue  # nothing to attest to — the row itself is gone
        action_id = m.split("action ")[1].split(" ")[0]
        row = await db.get(AgentActionDB, action_id)
        if row is None:
            continue
        receipt = await append_receipt(db, merchant_id, row.status, action_row=row)
        if receipt is not None:
            backfilled += 1
    await db.commit()
    return backfilled


async def main(targets: list[str]) -> int:
    factory = get_session_factory()
    async with factory() as db:
        if targets == ["--all"]:
            merchant_ids = list((await db.scalars(select(MerchantDB.id))).all())
        else:
            merchant_ids = []
            for t in targets:
                mid = await _resolve_merchant(db, t)
                if not mid:
                    print(f"SKIP: no merchant found for '{t}'")
                    continue
                merchant_ids.append(mid)

        total = 0
        for mid in merchant_ids:
            n = await backfill_one(db, mid)
            if n:
                print(f"{mid}: backfilled {n} missing receipt(s)")
                total += n
        print(f"Done — {total} receipt(s) backfilled across {len(merchant_ids)} merchant(s).")
        return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m scripts.backfill_missing_receipts <merchant_id_or_slug> [...] | --all")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
