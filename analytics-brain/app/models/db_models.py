"""
Database models — persistent source of truth.
Redis is the fast layer. Postgres is what survives a restart.
"""
from sqlalchemy import String, Float, Integer, BigInteger, Boolean, JSON, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
import time


class ReceiptDB(Base):
    """Tamper-evident audit trail — one row per autopilot lifecycle event
    (proposed/blocked/approved/dismissed/executed/blocked_at_execution).
    Hash-chained per merchant (entry_hash covers prev_hash + body, so
    reordering or deleting an entry breaks every entry after it) and
    HMAC-signed (so a chain can't be silently regenerated without the
    server's key). Verified offline by scripts/verify_receipts.py."""
    __tablename__ = "receipts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(
        ForeignKey("merchants.id"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    action_id: Mapped[str | None] = mapped_column(String, nullable=True)
    body: Mapped[dict] = mapped_column(JSON, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String, nullable=False)
    entry_hash: Mapped[str] = mapped_column(String, nullable=False)
    signature: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[int] = mapped_column(
        BigInteger, default=lambda: int(time.time() * 1000)
    )

    __table_args__ = (
        UniqueConstraint("merchant_id", "sequence", name="uq_receipts_merchant_sequence"),
    )


class ProductPriceHistoryDB(Base):
    """One row per product per UTC day — the durable history a pricing
    decision reasons over. Redis's behavior-event list (Keys.events) is
    capped and TTL'd for real-time anomaly detection only; this table is
    what makes "this product's history" mean something that survives past
    an hour. Written daily by pricing_signals.rollup_daily_signals."""
    __tablename__ = "product_price_history"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    date: Mapped[str] = mapped_column(String, nullable=False)  # "YYYY-MM-DD", UTC
    views: Mapped[int] = mapped_column(Integer, default=0)
    cart_adds: Mapped[int] = mapped_column(Integer, default=0)
    purchases: Mapped[int] = mapped_column(Integer, default=0)
    price_active: Mapped[float] = mapped_column(Float, nullable=False)
    # "normal" | "suspect" — set by pricing_signals.flag_suspicious_signals.
    # Suspect days are excluded from the pricing prompt rather than "corrected".
    signal_quality: Mapped[str] = mapped_column(String, default="normal")
    # Deliberately present but empty in v1 — a later signal (detail-view opens,
    # dwell time) can land here without another migration. Not read by v1 code.
    extra_signals: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("product_id", "date", name="uq_price_history_product_date"),
    )


class AutopilotTrustDB(Base):
    """Graduated-autonomy trust counter per (merchant, product, action_type).
    Read/written by autopilot_trust.py on every PRICE_REBALANCE outcome.
    Missing row == streak 0 == always gates; never defaults to trusted."""
    __tablename__ = "autopilot_trust"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(
        ForeignKey("merchants.id"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    streak: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[int] = mapped_column(
        BigInteger, default=lambda: int(time.time() * 1000)
    )

    __table_args__ = (
        UniqueConstraint(
            "merchant_id", "product_id", "action_type",
            name="uq_trust_merchant_product_type",
        ),
    )


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
    qwen_memory: Mapped[dict] = mapped_column(JSON, default=lambda: {"entries": []})
    # Unmet point-and-edit intents → Qwen proposes new config when one recurs.
    capability_requests: Mapped[dict] = mapped_column(JSON, default=dict)
    # Store-wide search demand — every storefront search query, aggregated,
    # so the merchant sees what customers are asking for even if nothing
    # matched. Same shape as capability_requests.
    search_queries: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))

    products: Mapped[list["ProductDB"]] = relationship(back_populates="merchant")
    orders: Mapped[list["OrderDB"]] = relationship(back_populates="merchant")


class CustomerDB(Base):
    """A store's customer. Scoped to one merchant — the same email may register
    at different stores (RBAC: role=customer, isolated per brand)."""
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("merchant_id", "email", name="uq_customer_store_email"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))


class ProductDB(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(Float, nullable=False)
    cost_price: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = mapped_column(String, default="")
    image_urls: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    qwen_generated_description: Mapped[bool] = mapped_column(Boolean, default=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    featured_label: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))

    merchant: Mapped["MerchantDB"] = relationship(back_populates="products")


class BrandProfileDB(Base):
    __tablename__ = "brand_profiles"

    merchant_id: Mapped[str] = mapped_column(
        ForeignKey("merchants.id"), primary_key=True
    )
    logo_analysis: Mapped[dict] = mapped_column(JSON, nullable=False)
    generated_brand: Mapped[dict] = mapped_column(JSON, nullable=False)
    brand_tokens: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # brand_guard_rules live inside generated_brand JSON
    created_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    updated_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))


class OrderDB(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    items: Mapped[list] = mapped_column(JSON, nullable=False)
    subtotal: Mapped[float] = mapped_column(Float, default=0.0)
    total: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    customer_name: Mapped[str] = mapped_column(String, default="")
    customer_email: Mapped[str] = mapped_column(String, default="")
    promo_applied: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    updated_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))

    merchant: Mapped["MerchantDB"] = relationship(back_populates="orders")


class PromoDB(Base):
    """Durable promo. SystemState.active_promos (Redis) is the hot-reload copy;
    this is what survives a Redis flush so the merchant's promos persist."""
    __tablename__ = "promos"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String, nullable=False)
    discount_percent: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    triggered_by: Mapped[str] = mapped_column(String, default="merchant")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))


class BusinessProfileDB(Base):
    """Durable interceptor constraints (margin floor / discount ceiling / per-
    product min price). Cached in Redis at Keys.profile for fast reads."""
    __tablename__ = "business_profiles"

    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), primary_key=True)
    constraints: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))


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


class AgentActionDB(Base):
    __tablename__ = "agent_actions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(
        ForeignKey("merchants.id"), nullable=False, index=True
    )
    promo_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    trigger: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    estimated_gmv: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    brand_check: Mapped[str] = mapped_column(String, nullable=False)
    constraint_check: Mapped[str] = mapped_column(String, nullable=False, default="")
    reasoning: Mapped[str] = mapped_column(Text, default="")
    # What Qwen actually saw when it made this call — catalog snapshot,
    # prior-outcome memory, discount ceiling — captured at decision time so
    # the Decision Trace page can show inputs alongside the reasoning
    # output, not just the outcome. See decision_engine.run_decision_cycle.
    context_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[int] = mapped_column(
        BigInteger, default=lambda: int(time.time() * 1000)
    )
    approved_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    executed_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    merchant_behavior: Mapped[str | None] = mapped_column(String, nullable=True)
    trigger_description: Mapped[str | None] = mapped_column(Text, nullable=True)
