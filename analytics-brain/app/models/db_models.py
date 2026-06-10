"""
Database models — persistent source of truth.
Redis is the fast layer. Postgres is what survives a restart.
"""
from sqlalchemy import String, Float, Integer, BigInteger, Boolean, JSON, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
import time


class MerchantDB(Base):
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    store_name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String, default="other")
    description: Mapped[str] = mapped_column(Text, default="")
    logo_url: Mapped[str | None] = mapped_column(String)
    onboarding_status: Mapped[str] = mapped_column(String, default="store_info")
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))

    products: Mapped[list["ProductDB"]] = relationship(back_populates="merchant")
    orders: Mapped[list["OrderDB"]] = relationship(back_populates="merchant")


class ProductDB(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(Float, nullable=False)
    cost_price: Mapped[float] = mapped_column(Float, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = mapped_column(String, default="")
    image_urls: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    qwen_generated_description: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))

    merchant: Mapped["MerchantDB"] = relationship(back_populates="products")


class BrandProfileDB(Base):
    __tablename__ = "brand_profiles"

    merchant_id: Mapped[str] = mapped_column(
        ForeignKey("merchants.id"), primary_key=True
    )
    logo_analysis: Mapped[dict] = mapped_column(JSON, nullable=False)
    generated_brand: Mapped[dict] = mapped_column(JSON, nullable=False)
    # brand_guard_rules live inside generated_brand JSON
    created_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    updated_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))


class OrderDB(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    items: Mapped[list] = mapped_column(JSON, nullable=False)
    total: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    promo_applied: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))

    merchant: Mapped["MerchantDB"] = relationship(back_populates="orders")


class DeltaLogDB(Base):
    """
    Persistent delta audit trail.
    Redis keeps last 100 for speed. Postgres keeps everything forever.
    """
    __tablename__ = "delta_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merchant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    action_id: Mapped[str] = mapped_column(String, nullable=False)
    patches: Mapped[list] = mapped_column(JSON, nullable=False)
    executed_by: Mapped[str] = mapped_column(String, nullable=False)
    executed_at: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
