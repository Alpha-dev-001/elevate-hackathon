from __future__ import annotations
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Literal, Any, Optional
from enum import Enum
import re
import secrets


# ─── Enums ────────────────────────────────────────────────────────────────────

class EventType(str, Enum):
    VIEW = "view"
    HOVER = "hover"
    CART_ADD = "cart_add"
    CART_REMOVE = "cart_remove"
    PURCHASE = "purchase"
    ABANDON = "abandon"

class ActionType(str, Enum):
    PRICE_ADJUST = "price_adjust"
    PROMO_TRIGGER = "promo_trigger"
    LAYOUT_SHIFT = "layout_shift"
    QR_CAMPAIGN = "qr_campaign"
    ALERT = "alert"

class RiskLevel(str, Enum):
    SAFE = "safe"
    MODERATE = "moderate"
    REVIEW = "review"

class Urgency(str, Enum):
    ROUTINE = "routine"
    MODERATE = "moderate"
    URGENT = "urgent"

class AnomalyType(str, Enum):
    VELOCITY_SPIKE = "velocity_spike"
    LOW_STOCK_SURGE = "low_stock_surge"
    DEAD_PRODUCT = "dead_product"

class LayoutVariant(str, Enum):
    STANDARD = "standard"
    PROMO_HEAVY = "promo_heavy"
    MINIMAL = "minimal"

class PatchOp(str, Enum):
    ADD = "add"
    REMOVE = "remove"
    REPLACE = "replace"
    MOVE = "move"
    COPY = "copy"
    TEST = "test"

class StoreCategory(str, Enum):
    FASHION = "fashion"
    ELECTRONICS = "electronics"
    FOOD = "food"
    BEAUTY = "beauty"
    HOME = "home"
    SPORTS = "sports"
    OTHER = "other"

class OnboardingStatus(str, Enum):
    STORE_INFO = "store_info"
    LOGO_UPLOAD = "logo_upload"
    BRAND_REVIEW = "brand_review"
    PRODUCTS = "products"
    LIVE = "live"

class OrderStatus(str, Enum):
    PENDING = "pending"      # placed, not yet paid (no real gateway in demo)
    PAID = "paid"            # payment simulated/confirmed
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class AgentActionType(str, Enum):
    FLASH_SALE = "flash_sale"
    LAYOUT_MORPH = "layout_morph"
    SCARCITY_PRICE = "scarcity_price"
    RECOVERY_OFFER = "recovery_offer"
    COPY_REWRITE = "copy_rewrite"
    DUPLICATE_MERGE = "duplicate_merge"

class AgentActionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DISMISSED = "dismissed"
    EXECUTED = "executed"


# ─── 1. The Eyes: qwen-vl-max output ─────────────────────────────────────────

class LogoAnalysis(BaseModel):
    primary_colors: list[str] = Field(..., description="Hex codes extracted from logo")
    secondary_colors: list[str] = Field(default_factory=list)
    mood: str = Field(..., description="e.g., 'bold', 'minimalist', 'playful'")
    style: str = Field(..., description="e.g., 'geometric', 'organic', 'vintage'")
    geometry_notes: str = Field(..., description="Notes on shapes, lines, symmetry")


# ─── 2. The Brain: qwen-max output ───────────────────────────────────────────

class BrandPalette(BaseModel):
    primary: str
    secondary: str
    accent: str
    background: str
    text: str

class BrandTypography(BaseModel):
    display_font: str    # e.g. 'Syne'
    body_font: str       # e.g. 'Inter'

class BrandIconSet(BaseModel):
    logo_mark: str = Field(..., description="SVG string for simplified logo mark")
    store_icon: str = Field(..., description="SVG string for browser tab / favicon")

class BrandColors(BaseModel):
    primary: str
    accent: str
    background: str
    surface: str
    text: str
    text_muted: str

class BrandTypographyToken(BaseModel):
    display_font: str
    body_font: str
    scale: Literal["compact", "balanced", "editorial"] = "balanced"
    letter_spacing: Literal["tight", "normal", "wide"] = "normal"
    weight: Literal["light", "regular", "medium", "bold"] = "regular"

class BrandLayoutToken(BaseModel):
    style: Literal["editorial", "bold-grid", "minimal-dark", "warm-craft"]
    hero_type: Literal["full-bleed", "text-forward", "split", "texture-bg"]
    product_grid: Literal["2col-featured", "3col-equal", "masonry"]
    card_style: Literal["borderless", "outlined", "elevated", "colored-bg"]
    border_radius: Literal["2px", "8px", "16px", "24px"]
    spacing: Literal["compact", "balanced", "generous"]
    category_style: Literal["pill", "underline-tab", "minimal-text"]

class BrandToken(BaseModel):
    store_name: str
    tagline: str
    colors: BrandColors
    typography: BrandTypographyToken
    layout: BrandLayoutToken
    mood: str
    industry_hint: str
    brand_voice: str
    layout_dsl: "LayoutDSL | None" = None   # populated by generate_layout_dsl()


# ─── Sprint 3: LayoutDSL ──────────────────────────────────────────────────────
from datetime import datetime, timezone


class SectionType(str, Enum):
    hero = "hero"
    product_grid = "product_grid"
    banner = "banner"
    story = "story"

class HeroVariant(str, Enum):
    full_bleed_image = "full-bleed-image"
    editorial_stacked = "editorial-stacked"
    minimal_wordmark = "minimal-wordmark"
    split_50_50 = "split-50-50"

class ProductGridVariant(str, Enum):
    masonry_4col = "masonry-4col"
    featured_2col = "featured-2col"
    horizontal_scroll = "horizontal-scroll"
    single_spotlight = "single-spotlight"

class BannerVariant(str, Enum):
    scroll_ticker = "scroll-ticker"
    static_strip = "static-strip"
    announcement_bar = "announcement-bar"

class StoryVariant(str, Enum):
    full_bleed_text = "full-bleed-text"
    split_image_story = "split-image-story"
    quote_callout = "quote-callout"

class ProductCardVariant(str, Enum):
    hover_reveal_text = "hover-reveal-text"
    colored_bg_card = "colored-bg-card"
    editorial_horizontal = "editorial-horizontal"
    borderless_floating = "borderless-floating"
    polaroid_card = "polaroid-card"
    image_below_text = "image-below-text"

class NavStyle(str, Enum):
    underline_tabs = "underline-tabs"
    pill_nav = "pill-nav"
    sidebar_text = "sidebar-text"
    sticky_tabs = "sticky-tabs"
    minimal_text = "minimal-text"


class LayoutSection(BaseModel):
    type: SectionType
    variant: str  # validated against the type's enum by layout_dsl.coerce_variant
    props: dict[str, Any] = Field(default_factory=dict)

class LayoutGlobalConfig(BaseModel):
    nav_style: NavStyle
    product_card: ProductCardVariant
    color_mode: Literal["light", "dark", "auto"] = "auto"
    corner_radius: Literal["none", "sm", "md", "lg", "full"] = "md"
    density: Literal["sparse", "normal", "dense"] = "normal"
    # "Shared autonomy" — where the add-to-cart affordance lives is a DSL choice,
    # not a hardcoded fix. Qwen picks a default; the merchant overrides in the builder.
    add_to_cart: Literal["drawer-only", "card-hover", "card-always", "none"] = "drawer-only"
    # Every page composes per store, not just the landing. The product detail and
    # cart presentations are DSL choices too.
    product_detail: Literal["gallery-split", "editorial-stacked", "minimal-centered"] = "gallery-split"
    cart_style: Literal["slide-panel", "full-sheet"] = "slide-panel"

class LayoutDSL(BaseModel):
    sections: list[LayoutSection] = Field(min_length=2, max_length=5)
    global_config: LayoutGlobalConfig
    custom_css: str = ""


class MemoryEntry(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    action_type: str
    trigger: str
    outcome: str
    merchant_behavior: str          # approved | dismissed | approved_then_modified
    notes: str = ""


BrandToken.model_rebuild()   # resolve the forward ref to LayoutDSL


class GeneratedBrand(BaseModel):
    store_name: str
    tagline: str
    palette: BrandPalette
    typography: BrandTypography
    brand_voice_profile: str = Field(
        ..., description="Tone and style guidelines — used for product description generation"
    )
    icons: BrandIconSet
    layout_variant: LayoutVariant = LayoutVariant.STANDARD
    suggested_categories: list[str] = Field(default_factory=list)


# ─── 3. The Interceptor: Pre-authored defense ─────────────────────────────────

class BrandGuardRule(BaseModel):
    rule_id: str
    field: str           # which UI field triggers this: "accent", "primary", "layout_variant"
    description: str
    warning_message: str = Field(
        ...,
        description="Qwen's own words — first person, references specific hex values it chose"
    )

class BrandGuardRules(BaseModel):
    allowed_color_palette: list[str] = Field(
        ..., description="Hex codes safe to use — frontend checks instantly, no round-trip"
    )
    forbidden_combinations: list[str] = Field(default_factory=list)
    rules: list[BrandGuardRule]


# ─── 4. The Core Brand Package ────────────────────────────────────────────────

class BrandPackage(BaseModel):
    """
    Single combined object — one Redis write, one WebSocket payload.
    analysis + brand + guards travel together always.
    """
    analysis: LogoAnalysis
    brand: GeneratedBrand
    guards: BrandGuardRules


# ─── 5. Merchant ──────────────────────────────────────────────────────────────

class MerchantBase(BaseModel):
    email: EmailStr
    store_name: str

class MerchantCreate(MerchantBase):
    password: str = Field(min_length=8, max_length=72)  # 72 = bcrypt input limit
    category: StoreCategory = StoreCategory.OTHER
    description: str = ""

class MerchantLogin(BaseModel):
    email: EmailStr
    password: str

class Merchant(MerchantBase):
    id: str
    slug: str
    logo_url: str = ""  # empty until the logo upload step
    category: StoreCategory
    brand_package: Optional[BrandPackage] = None
    onboarding_status: OnboardingStatus = OnboardingStatus.STORE_INFO
    is_live: bool = False

class MerchantInDB(Merchant):
    hashed_password: str    # never returned in API responses


# ─── Per-brand customers (RBAC: role=customer, scoped to one store) ────────────

class CustomerCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    name: str = Field(min_length=1, max_length=120)

class CustomerLogin(BaseModel):
    email: EmailStr
    password: str

class Customer(BaseModel):
    id: str
    merchant_id: str
    store_slug: str
    email: EmailStr
    name: str
    role: Literal["customer"] = "customer"


# ─── 6. Product ───────────────────────────────────────────────────────────────

class ProductBase(BaseModel):
    name: str
    price: float = Field(gt=0)
    stock: int = Field(ge=0)
    image_url: Optional[str] = None
    category: Optional[str] = None

class ProductCreate(ProductBase):
    cost_price: float = Field(gt=0)

class Product(ProductBase):
    id: str
    merchant_id: str
    cost_price: float
    description: Optional[str] = None    # generated by qwen-max
    qwen_generated: bool = False
    is_pending: bool = False             # vision-created, awaiting merchant approval
    is_featured: bool = False
    featured_label: Optional[str] = None

class ProductUpdate(BaseModel):
    """Partial product edit — every field optional, only provided ones change.
    Price changes run through the interceptor (margin floor / below-cost)."""
    name: Optional[str] = None
    price: Optional[float] = Field(default=None, gt=0)
    cost_price: Optional[float] = Field(default=None, gt=0)
    stock: Optional[int] = Field(default=None, ge=0)
    category: Optional[str] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None


# ─── 7. Slug Generator ────────────────────────────────────────────────────────

def generate_slug(store_name: str, *, suffix: bool = False) -> str:
    """Slug from store name — clean by default, collision suffix on demand.

    "Emma Fashion" → "emma-fashion", or "emma-fashion-a3f2" when suffix=True.
    Caller checks the DB for collisions and retries with suffix=True.
    """
    slug = re.sub(r'[^a-z0-9]+', '-', store_name.lower()).strip('-') or "store"
    if suffix:
        return f"{slug}-{secrets.token_hex(2)}"
    return slug


# ─── 8. Telemetry ─────────────────────────────────────────────────────────────

class CustomerEvent(BaseModel):
    session_id: str
    product_id: str
    event_type: EventType
    timestamp: int
    metadata: dict[str, Any] = Field(default_factory=dict)

class Anomaly(BaseModel):
    type: AnomalyType
    product_id: Optional[str] = None
    severity: Literal["low", "medium", "high"]
    detected_at: int
    context: dict[str, Any] = Field(default_factory=dict)

class TelemetrySnapshot(BaseModel):
    captured_at: int
    active_session_count: int
    product_velocity: dict[str, float]
    hot_products: list[str]
    anomalies: list[Anomaly]


# ─── 9. Business Profile & Constraints ───────────────────────────────────────

class BusinessConstraints(BaseModel):
    min_profit_margin_percent: float = Field(ge=0, le=100, default=15.0)
    max_discount_percent: float = Field(ge=0, le=100, default=40.0)
    min_price: dict[str, float] = Field(default_factory=dict)
    accessibility_level: Literal["AA", "AAA"] = "AA"

class BusinessProfile(BaseModel):
    merchant_id: str
    store_name: str
    constraints: BusinessConstraints
    products: list[Product]


# ─── 10. Delta / JSON Patch ───────────────────────────────────────────────────

class JsonPatch(BaseModel):
    op: PatchOp
    path: str
    value: Any = None
    from_path: Optional[str] = Field(None, alias="from")

    model_config = {"populate_by_name": True}


# ─── 11. Proposed Actions & Decisions ────────────────────────────────────────

class ProposedAction(BaseModel):
    id: str
    type: ActionType
    label: str
    description: str
    patch: list[JsonPatch]
    risk_level: RiskLevel
    estimated_revenue_delta: Optional[float] = None

class QwenDecision(BaseModel):
    reasoning: str
    proposed_actions: list[ProposedAction]
    urgency: Urgency
    estimated_impact: str


# ─── 12. System State ────────────────────────────────────────────────────────

class Promo(BaseModel):
    id: str
    product_id: str
    discount_percent: float = Field(ge=0, le=100)
    label: str
    expires_at: int
    triggered_by: Literal["merchant", "auto"]

class RecoveryOffer(BaseModel):
    """Order-level cart-recovery discount — set when the merchant approves a
    `recovery_offer` agent action. Unlike a Promo it targets NO product: the
    browse grid stays at full price and only an existing cart's *total* drops.
    Applied to the subtotal at cart-read time; expiry is enforced there so a
    stale state can never resurrect it. `promo_id` mirrors the AgentAction's
    promo_id so a checkout under this offer still attributes to that action."""
    percent: float = Field(gt=0, le=90)
    label: str
    expires_at: int
    promo_id: str = ""
    triggered_by: Literal["merchant", "auto"] = "auto"

class LayoutConfig(BaseModel):
    hero_product_id: Optional[str] = None
    featured_category: Optional[str] = None
    banner_text: Optional[str] = None
    color_accent: Optional[str] = None
    layout_variant: LayoutVariant = LayoutVariant.STANDARD

class QRCampaign(BaseModel):
    id: str
    product_id: str
    promo_id: Optional[str] = None
    scan_count: int = 0
    created_at: int
    expires_at: Optional[int] = None
    deep_link_url: str

class SystemState(BaseModel):
    version: int = 0
    last_updated: int
    products: dict[str, Product]
    active_promos: dict[str, Promo] = Field(default_factory=dict)
    layout_config: LayoutConfig = Field(default_factory=LayoutConfig)
    qr_campaigns: dict[str, QRCampaign] = Field(default_factory=dict)
    recovery: Optional[RecoveryOffer] = None   # active order-level cart-recovery discount

class AgentAction(BaseModel):
    id: str
    merchant_id: str
    promo_id: str
    action_type: AgentActionType
    trigger: str
    title: str
    description: str
    estimated_gmv: float
    estimated_confidence: float
    payload: dict[str, Any]
    brand_check: str
    reasoning: str = ""
    status: AgentActionStatus = AgentActionStatus.PENDING
    created_at: int
    approved_at: Optional[int] = None
    executed_at: Optional[int] = None


# ─── 13. WebSocket Events ────────────────────────────────────────────────────

class WSEventType(str, Enum):
    # Server → Client
    BRAND_READY = "brand_ready"
    DECISION_READY = "decision_ready"
    STATE_UPDATED = "state_updated"
    ANOMALY_DETECTED = "anomaly_detected"
    ACTION_CLAMPED = "action_clamped"
    ACTION_BLOCKED = "action_blocked"
    BRAND_WARNING = "brand_warning"
    SNAPSHOT_UPDATE = "snapshot_update"
    AGENT_ACTION = "agent_action"
    ACTION_EXPIRED = "action_expired"
    QWEN_FALLBACK = "qwen_fallback"
    # Client → Server
    APPROVE_ACTION = "approve_action"
    REJECT_ACTION = "reject_action"
    STAGE_PREVIEW = "stage_preview"
    ROLLBACK = "rollback"
    CUSTOMER_EVENT = "customer_event"
    BRAND_TWEAK = "brand_tweak"

class WSMessage(BaseModel):
    event: WSEventType
    payload: dict[str, Any]
    merchant_id: str
    timestamp: int


# ─── 14. Validation Results ───────────────────────────────────────────────────

class Violation(BaseModel):
    rule: str
    severity: Literal["warning", "blocked"]
    message: str
    original_value: Any = None
    clamped_value: Any = None

class ValidationResult(BaseModel):
    valid: bool
    action: ProposedAction
    violations: list[Violation]
    clamped_patches: Optional[list[JsonPatch]] = None

class BrandWarning(BaseModel):
    rule_id: str
    field: str
    severity: Literal["info", "warning"]
    message: str               # Qwen's own words
    proposed_value: Any


# ─── 15. Onboarding API shapes ────────────────────────────────────────────────

class STSTokenResponse(BaseModel):
    access_key_id: str
    access_key_secret: str
    security_token: str
    expiration: str
    bucket: str
    region: str
    object_key: str

class PresignedUploadRequest(BaseModel):
    """Frontend asks for a one-shot upload URL for a logo of this content type."""
    content_type: str

class PresignedUploadResponse(BaseModel):
    """A presigned PUT URL the browser uploads straight to. `required_headers`
    MUST be sent verbatim on the PUT or OSS returns SignatureNotMatch."""
    upload_url: str
    public_url: str
    object_key: str
    required_headers: dict[str, str]

class LogoSubmitRequest(BaseModel):
    """Step 2 -> 3: the authenticated merchant hands us the OSS URL of their
    uploaded logo. Store info already lives on the merchant from signup, so the
    URL is all we need to kick off brand generation."""
    logo_oss_url: str


class OnboardingStartRequest(BaseModel):
    store_name: str
    category: StoreCategory
    description: str
    logo_oss_url: str

class BrandReadyEvent(BaseModel):
    event: str = "brand_ready"
    merchant_id: str
    brand_package: BrandPackage
    store_shell_url: str

class ProductCSVRow(BaseModel):
    name: str
    price: float
    stock: int
    image_url: str = ""
    category: str = ""

class ProductBatchCreate(BaseModel):
    """CSV drop — rows carry no cost_price, so the router derives a default
    margin. One qwen-max call writes every description."""
    products: list[ProductCSVRow]

class BatchDescriptionRequest(BaseModel):
    merchant_id: str
    products: list[ProductCSVRow]
    brand_voice_profile: str

class BatchDescriptionResponse(BaseModel):
    descriptions: dict[str, str]   # product name → description


class VisionBatchRequest(BaseModel):
    """Drop a batch of product image URLs — each gets one qwen-vl-max pass."""
    image_urls: list[str] = Field(..., max_length=50)


class VisionBatchProduct(BaseModel):
    """One product drafted from a photo — includes confidence for CatalogReview."""
    product: Product
    confident: bool = True


class VisionBatchResponse(BaseModel):
    products: list[VisionBatchProduct]
    failed_urls: list[str] = []


class DuplicateGroup(BaseModel):
    """Products sharing the same image — grouped for dedup decisions."""
    image_url: str
    product_ids: list[str]
    names: list[str]
    qwen_generated: bool  # True if all products in the group were Qwen-created
    auto_resolved: bool   # True if the system already handled it (Qwen dupes)


class DeduplicateReport(BaseModel):
    """Result of a catalog deduplication pass."""
    auto_merged: list[DuplicateGroup]   # Qwen-generated duplicates already resolved
    needs_review: list[DuplicateGroup]  # Merchant-written duplicates — human decides
    total_scanned: int
    total_duplicates: int


class DeltaExecution(BaseModel):
    action_id: str
    patches: list[JsonPatch]
    executed_at: int
    executed_by: Literal["merchant", "auto"]
    rollback_available: bool = True


# ─── 16. Public storefront payload ────────────────────────────────────────────
# Customer-facing — deliberately omits cost_price/margin and any internal fields.

class PublicProduct(BaseModel):
    id: str
    name: str
    price: float                          # effective price (after active promo)
    compare_at_price: Optional[float] = None   # original price when discounted — struck through
    promo_label: Optional[str] = None          # active promo's label, if any
    description: Optional[str] = None
    image_url: Optional[str] = None
    category: Optional[str] = None
    available: bool   # stock > 0 — never expose exact stock or cost
    is_featured: bool = False
    featured_label: Optional[str] = None

class PublicStore(BaseModel):
    store_name: str
    slug: str
    merchant_id: str = ""   # opaque room id for the storefront WebSocket (live state pushes)
    logo_url: str = ""   # merchant's real uploaded logo; "" falls back to generated SVG mark
    tagline: str
    palette: BrandPalette
    typography: BrandTypography
    icons: BrandIconSet
    layout: LayoutConfig
    products: list[PublicProduct]
    promos: list[Promo] = Field(default_factory=list)
    recovery: Optional[RecoveryOffer] = None  # active cart-recovery banner (order-level)
    categories: list[str] = Field(default_factory=list)  # for storefront filter chips
    brand_token: Optional[BrandToken] = None


# ─── 17. Sprint 2 — Commerce: cart, checkout, orders ─────────────────────────
# The store can transact. Cart lives in Redis (ephemeral, price snapshot taken
# at add-time); orders are durable in Postgres. Guest-first checkout.

class CartItem(BaseModel):
    product_id: str
    name: str
    unit_price: float          # SNAPSHOT — the effective price when added; never re-derived
    qty: int = Field(gt=0)
    image_url: Optional[str] = None
    line_total: float          # round(unit_price * qty, 2)

class Cart(BaseModel):
    session_id: str
    merchant_id: str
    items: list[CartItem] = Field(default_factory=list)
    subtotal: float = 0.0            # sum of line_totals, before any recovery discount
    item_count: int = 0
    # Order-level recovery discount overlaid at read time from SystemState.recovery.
    # Never snapshotted onto lines — recomputed on every read so it can expire.
    discount_percent: float = 0.0
    discount_label: Optional[str] = None
    discount_expires_at: Optional[int] = None
    discount_amount: float = 0.0     # round(subtotal * percent / 100, 2)
    total: float = 0.0               # subtotal - discount_amount
    updated_at: int

class CartMutation(BaseModel):
    """Add/set a line. qty is the absolute desired quantity for set ops, or the
    amount to add for add ops — the route decides. session_id identifies the
    guest cart (frontend generates + persists it in localStorage)."""
    session_id: str = Field(min_length=8)
    product_id: str
    qty: int = Field(default=1)

class OrderCustomer(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    note: str = ""

class OrderItem(BaseModel):
    product_id: str
    name: str
    unit_price: float          # snapshot honored from cart
    qty: int = Field(gt=0)
    line_total: float

class CheckoutRequest(BaseModel):
    session_id: str = Field(min_length=8)
    customer: OrderCustomer

class Order(BaseModel):
    id: str
    merchant_id: str
    session_id: str
    items: list[OrderItem]
    subtotal: float
    total: float
    status: OrderStatus
    customer_name: str
    customer_email: str
    promo_applied: Optional[str] = None
    created_at: int

class OrderStatusUpdate(BaseModel):
    status: OrderStatus


# ─── 18. Sprint 2 — Merchant pricing controls: promos + constraints ──────────

class PromoCreate(BaseModel):
    product_id: str
    discount_percent: float = Field(gt=0, le=100)
    label: str = Field(min_length=1, max_length=80)
    duration_minutes: int = Field(default=1440, gt=0, le=43200)  # default 24h, max 30d

class ConstraintsUpdate(BaseModel):
    """Merchant tunes the interceptor's Layer 2 floors. All optional — only
    provided fields change."""
    min_profit_margin_percent: Optional[float] = Field(default=None, ge=0, le=100)
    max_discount_percent: Optional[float] = Field(default=None, ge=0, le=100)
    min_price: Optional[dict[str, float]] = None
    accessibility_level: Optional[Literal["AA", "AAA"]] = None


# ─── 19. Sprint 2 — Qwen observes: catalog pricing review (read-only) ─────────
# qwen-max reviews names/categories/prices only — never cost, never PII — and
# flags possible pricing issues. Surfaced to the merchant; NEVER auto-applied.

class PricingFlag(BaseModel):
    product_id: str
    name: str
    severity: Literal["low", "medium", "high"]
    issue: str                 # what Qwen noticed
    suggestion: str            # what Qwen would consider — advisory only

class CatalogReview(BaseModel):
    flags: list[PricingFlag] = Field(default_factory=list)
    summary: str               # one-line overall read of the catalog
    reviewed_count: int
    generated_at: int
