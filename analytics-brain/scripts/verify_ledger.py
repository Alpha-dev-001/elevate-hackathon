"""
Offline verification of a merchant's Decision Ledger — proves the chain
hasn't been reordered/deleted/re-signed, and (optionally) that the
underlying AgentActionDB rows still match what was attested at the time.

Usage:
    docker compose exec api python -m scripts.verify_ledger <merchant_id_or_slug> [--chain]

--chain prints the full sequence table (event type, action, hash prefix)
so a failure's reported sequence number can be located visually against
its neighbors, and so a healthy chain is visibly a chain, not just a count.
"""
import asyncio
import sys

from sqlalchemy import select

from app.core.database import get_session_factory
from app.models.db_models import MerchantDB
from app.services.receipts import load_ledger, verify_chain, verify_row_consistency


async def _resolve_merchant(db, merchant_id_or_slug: str) -> str | None:
    merchant = await db.get(MerchantDB, merchant_id_or_slug)
    if merchant:
        return merchant.id
    merchant = await db.scalar(select(MerchantDB).where(MerchantDB.slug == merchant_id_or_slug))
    return merchant.id if merchant else None


def _print_chain(receipts) -> None:
    print()
    print(f"  {'seq':>3}  {'event':<10}  {'action':<10}  hash")
    print(f"  {'---':>3}  {'-'*10}  {'-'*10}  {'-'*10}")
    ordered = sorted(receipts, key=lambda r: r.sequence)
    for i, r in enumerate(ordered):
        action = (r.action_id or "—")[:8]
        arrow = " -> " if i < len(ordered) - 1 else "    "
        print(f"  [{r.sequence:>2}]  {r.event_type:<10}  {action:<10}  {r.entry_hash[:8]}{arrow}")
    print()


async def main(merchant_id_or_slug: str, show_chain: bool = False) -> int:
    factory = get_session_factory()
    async with factory() as db:
        merchant_id = await _resolve_merchant(db, merchant_id_or_slug)
        if not merchant_id:
            print(f"FAIL: no merchant found for '{merchant_id_or_slug}'")
            return 1

        receipts = await load_ledger(db, merchant_id)
        print(f"{len(receipts)} ledger entries for {merchant_id_or_slug}")

        if show_chain:
            _print_chain(receipts)

        valid, err = verify_chain(receipts)
        if not valid:
            print(f"FAIL: chain integrity — {err}")
            return 1
        print("PASS: chain integrity (hash linkage + signatures all verified)")

        mismatches = await verify_row_consistency(db, receipts)
        if mismatches:
            print(f"FAIL: {len(mismatches)} row-consistency mismatch(es):")
            for m in mismatches:
                print(f"  - {m}")
            return 1
        print("PASS: every attested action still matches its current database row")

        return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    show_chain = "--chain" in args
    positional = [a for a in args if a != "--chain"]
    if len(positional) != 1:
        print("usage: python -m scripts.verify_ledger <merchant_id_or_slug> [--chain]")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(positional[0], show_chain)))
