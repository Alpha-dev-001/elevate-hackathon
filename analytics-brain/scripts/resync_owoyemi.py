"""Refresh the live Redis SystemState for owoyemi-of-offa from Postgres.
Run after editing products directly in the DB (the storefront reads state.products).

Run: docker compose exec api sh -c "cd /app && python -m scripts.resync_owoyemi"
"""
import asyncio
from sqlalchemy import select
from app.core.database import get_session_factory
from app.models.db_models import MerchantDB
from app.services.products import products_state_map
from app.services import delta as delta_svc


async def main():
    async with get_session_factory()() as db:
        m = await db.scalar(select(MerchantDB).where(MerchantDB.slug == "owoyemi-of-offa"))
        if not m:
            print("no owoyemi-of-offa merchant")
            return
        state = await delta_svc.load_state(m.id)
        if state is None:
            print("no live state — publish first")
            return
        state.products = await products_state_map(db, m.id)
        state.version += 1
        await delta_svc.save_state(m.id, state)
        print("resynced products:", len(state.products))


if __name__ == "__main__":
    asyncio.run(main())
