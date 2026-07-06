"""Add or remove a demo promo on owoyemi-of-offa's first product, to verify the
discount UI (strikethrough + label). NOT for the real demo — the autopilot creates
the real promo. Clean up with --remove.

Run: docker compose exec api sh -c "cd /app && python -m scripts.demo_promo"
     docker compose exec api sh -c "cd /app && python -m scripts.demo_promo --remove"
"""
import asyncio
import sys
import time
from sqlalchemy import select
from app.core.database import get_session_factory
from app.models.db_models import MerchantDB
from app.models.schemas import Promo
from app.services import delta as delta_svc

REMOVE = "--remove" in sys.argv
PROMO_ID = "DEMO_PROMO_STRIKE"


async def main():
    async with get_session_factory()() as db:
        m = await db.scalar(select(MerchantDB).where(MerchantDB.slug == "owoyemi-of-offa"))
        state = await delta_svc.load_state(m.id)
        if state is None:
            print("no state")
            return
        if REMOVE:
            state.active_promos.pop(PROMO_ID, None)
            print("promo removed")
        else:
            first_id = next(iter(state.products.keys()))
            first = state.products[first_id]
            state.active_promos[PROMO_ID] = Promo(
                id=PROMO_ID, product_id=first_id, discount_percent=10.0,
                label="10% off", expires_at=int(time.time() * 1000) + 3600_000,
                triggered_by="auto",
            )
            print(f"promo on {first_id} ({first.name})")
        state.version += 1
        await delta_svc.save_state(m.id, state)


if __name__ == "__main__":
    asyncio.run(main())
