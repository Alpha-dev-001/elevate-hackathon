"""
Product persistence helpers — shared by the products router and onboarding
publish (which seeds SystemState from whatever products already exist).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import ProductDB
from app.models.schemas import Product

# CSV rows carry no cost price; assume a 40% margin so the interceptor's margin
# math has something real to work with. The merchant can correct it later.
DEFAULT_COST_RATIO = 0.6


def db_to_product(row: ProductDB) -> Product:
    return Product(
        id=row.id,
        merchant_id=row.merchant_id,
        name=row.name,
        price=row.price,
        stock=row.stock,
        image_url=row.image_urls[0] if row.image_urls else None,
        category=row.category or None,
        cost_price=row.cost_price,
        description=row.description or None,
        qwen_generated=row.qwen_generated_description,
        is_pending=not row.is_active,
        is_featured=row.is_featured,
        featured_label=row.featured_label,
    )


async def load_products(db: AsyncSession, merchant_id: str) -> list[ProductDB]:
    rows = await db.scalars(
        select(ProductDB)
        .where(ProductDB.merchant_id == merchant_id, ProductDB.is_active.is_(True))
        .order_by(ProductDB.created_at)
    )
    return list(rows)


async def products_state_map(db: AsyncSession, merchant_id: str) -> dict[str, Product]:
    """The {product_id: Product} shape SystemState.products expects."""
    return {row.id: db_to_product(row) for row in await load_products(db, merchant_id)}
