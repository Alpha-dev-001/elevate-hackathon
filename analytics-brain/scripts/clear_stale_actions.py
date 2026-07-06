"""Remove clutter from the terminal's Executed Actions log: executed agent
actions that drove 0 attributed orders (e.g. the pre-fix "Free Shipping" cards
from testing). Keeps every action that actually attributed revenue.

Run: docker compose exec api sh -c "cd /app && python -m scripts.clear_stale_actions"
     add --slug other-store to target a different store (default owoyemi-of-offa)
"""
import asyncio
import sys

from sqlalchemy import select, delete

from app.core.database import get_session_factory
from app.models.db_models import MerchantDB, AgentActionDB, OrderDB

SLUG = "owoyemi-of-offa"
if "--slug" in sys.argv:
    SLUG = sys.argv[sys.argv.index("--slug") + 1]


async def main():
    async with get_session_factory()() as db:
        m = await db.scalar(select(MerchantDB).where(MerchantDB.slug == SLUG))
        if not m:
            print(f"no merchant for slug {SLUG}")
            return

        # promo_ids that actually attributed at least one order
        attributed = {
            pa for (pa,) in (await db.execute(
                select(OrderDB.promo_applied).where(
                    OrderDB.merchant_id == m.id, OrderDB.promo_applied.isnot(None)
                )
            )).all()
        }
        # split comma-joined promo lists into individual ids
        attributed_ids = {pid.strip() for row in attributed for pid in row.split(",")}

        executed = (await db.scalars(
            select(AgentActionDB).where(
                AgentActionDB.merchant_id == m.id,
                AgentActionDB.status == "executed",
            )
        )).all()

        stale = [a for a in executed if a.promo_id not in attributed_ids]
        for a in stale:
            print(f"  removing stale executed action: {a.title!r} (promo {a.promo_id})")
        if stale:
            await db.execute(
                delete(AgentActionDB).where(AgentActionDB.id.in_([a.id for a in stale]))
            )
            await db.commit()
        print(f"cleared {len(stale)} stale action(s); kept {len(executed) - len(stale)} that attributed revenue")


if __name__ == "__main__":
    asyncio.run(main())
