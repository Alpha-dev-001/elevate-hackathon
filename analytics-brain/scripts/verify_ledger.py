"""
Offline verification of a merchant's Decision Ledger — proves the chain
hasn't been reordered/deleted/re-signed, and (optionally) that the
underlying AgentActionDB rows still match what was attested at the time.

Usage:
    docker compose exec api python -m scripts.verify_ledger <merchant_id_or_slug>
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


async def main(merchant_id_or_slug: str) -> int:
    factory = get_session_factory()
    async with factory() as db:
        merchant_id = await _resolve_merchant(db, merchant_id_or_slug)
        if not merchant_id:
            print(f"FAIL: no merchant found for '{merchant_id_or_slug}'")
            return 1

        receipts = await load_ledger(db, merchant_id)
        print(f"{len(receipts)} ledger entries for {merchant_id_or_slug}")

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
    if len(sys.argv) != 2:
        print("usage: python -m scripts.verify_ledger <merchant_id_or_slug>")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
