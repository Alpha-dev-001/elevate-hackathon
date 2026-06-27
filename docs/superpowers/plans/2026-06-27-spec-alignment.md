# Spec Alignment Plan — docs/read.md → Codebase

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the existing Sprint-1 codebase with the richer docs/read.md spec — adding layout DNA variants, the Qwen decision engine, merchant terminal UI, and attribution dashboard without breaking what already works.

**Architecture:** Keep all existing infrastructure (auth, OSS upload, cart, orders, WS manager, Redis keys). Add `BrandToken` as the richer brand shape (alongside existing `GeneratedBrand` for backward compat), `AgentActionDB` as the new autonomous decision table, and five new services/routers for the behavior → anomaly → decision → approve loop. On the frontend, wrap the storefront in a `StoreShell` that reads `brand_token.layout.style` to select one of four visually distinct layouts; add a merchant terminal page that shows the live brain.

**Tech Stack:** FastAPI · PostgreSQL (SQLAlchemy async) · Redis · Qwen-Max · Next.js 15 · Framer Motion · Tailwind CSS · Zod · Zustand

## Global Constraints

- Python `analytics-brain/app/` — source root; imports use `app.*`
- TypeScript `storefront-ui/` — Next.js 15 App Router; `@/` maps to `storefront-ui/`
- Never add `cost_price` / margins to any customer-facing payload
- All Qwen calls use `response_format: {"type": "json_object"}` and `_qwen_chat()` from `brand.py`
- Redis keys all go through `app.core.redis.Keys` — never hardcode key strings
- No new routers without registering in `main.py`
- Commits: `[sprint-2] <description>` format
- Backend test command: `docker compose exec api pytest analytics-brain/tests/ -v`
- API base: `http://localhost:9000` (local), `https://bms-backend-brain.cn-hongkong.fcapp.run` (prod)

---

## Task 1: Data Layer — BrandToken + AgentAction schemas

**Files:**
- Modify: `analytics-brain/app/models/schemas.py` (add ~80 lines after line 45)
- Modify: `analytics-brain/app/models/db_models.py` (add AgentActionDB + brand_tokens column)
- Modify: `analytics-brain/app/main.py` (add ALTER TABLE in startup)
- Modify: `storefront-ui/types/schemas.ts` (add BrandToken, AgentAction types)

**Interfaces:**
- Produces: `BrandToken`, `AgentAction`, `AgentActionType`, `AgentActionStatus` Pydantic models consumed by Tasks 2–3
- Produces: same Zod types consumed by Tasks 4–5

- [ ] **Step 1: Add BrandToken + AgentAction schemas to `analytics-brain/app/models/schemas.py`**

Insert after the existing `LayoutVariant` enum (after line ~47) and after the `AnomalyType` enum block:

```python
# ─── New for spec alignment ────────────────────────────────────────────────────

class AgentActionType(str, Enum):
    FLASH_SALE = "flash_sale"
    LAYOUT_MORPH = "layout_morph"
    SCARCITY_PRICE = "scarcity_price"
    RECOVERY_OFFER = "recovery_offer"
    COPY_REWRITE = "copy_rewrite"

class AgentActionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DISMISSED = "dismissed"
    EXECUTED = "executed"
```

Then add the BrandToken models after the existing `BrandIconSet` block (after `class BrandIconSet`):

```python
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
```

Then add `AgentAction` after the `SystemState` block:

```python
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
    status: AgentActionStatus = AgentActionStatus.PENDING
    created_at: int
    approved_at: Optional[int] = None
    executed_at: Optional[int] = None
```

Also add `AGENT_ACTION = "agent_action"` to the `WSEventType` enum.

Also add `brand_token: Optional[BrandToken] = None` to `PublicStore`:
```python
class PublicStore(BaseModel):
    store_name: str
    slug: str
    tagline: str
    palette: BrandPalette
    typography: BrandTypography
    icons: BrandIconSet
    layout: LayoutConfig
    products: list[PublicProduct]
    promos: list[Promo] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    brand_token: Optional[BrandToken] = None   # ← add this line
```

- [ ] **Step 2: Add `AgentActionDB` to `analytics-brain/app/models/db_models.py`**

Append at the end of the file:

```python
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
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[int] = mapped_column(
        BigInteger, default=lambda: int(time.time() * 1000)
    )
    approved_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    executed_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
```

Also add `brand_tokens` column to `BrandProfileDB` (insert after `generated_brand` line):
```python
brand_tokens: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

- [ ] **Step 3: Register new table + column in `analytics-brain/app/main.py` startup**

In the `_ORDER_COLUMNS` list in `startup()`, add two more entries:
```python
_SCHEMA_PATCHES = [
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS subtotal DOUBLE PRECISION DEFAULT 0",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_name VARCHAR DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_email VARCHAR DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS updated_at BIGINT DEFAULT 0",
    "ALTER TABLE brand_profiles ADD COLUMN IF NOT EXISTS brand_tokens JSONB",
]
```

Rename the variable from `_ORDER_COLUMNS` to `_SCHEMA_PATCHES` and update the loop to iterate over `_SCHEMA_PATCHES`. Also update the `create_all` call so the new `agent_actions` table is created.

- [ ] **Step 4: Add BrandToken + AgentAction to `storefront-ui/types/schemas.ts`**

Append before the `// ─── Inferred Types` section:

```typescript
// ─── BrandToken (spec-aligned layout DNA) ─────────────────────────────────

export const BrandColorsSchema = z.object({
  primary: z.string(),
  accent: z.string(),
  background: z.string(),
  surface: z.string(),
  text: z.string(),
  text_muted: z.string(),
})

export const BrandTypographyTokenSchema = z.object({
  display_font: z.string(),
  body_font: z.string(),
  scale: z.enum(['compact', 'balanced', 'editorial']).default('balanced'),
  letter_spacing: z.enum(['tight', 'normal', 'wide']).default('normal'),
  weight: z.enum(['light', 'regular', 'medium', 'bold']).default('regular'),
})

export const BrandLayoutTokenSchema = z.object({
  style: z.enum(['editorial', 'bold-grid', 'minimal-dark', 'warm-craft']),
  hero_type: z.enum(['full-bleed', 'text-forward', 'split', 'texture-bg']),
  product_grid: z.enum(['2col-featured', '3col-equal', 'masonry']),
  card_style: z.enum(['borderless', 'outlined', 'elevated', 'colored-bg']),
  border_radius: z.enum(['2px', '8px', '16px', '24px']),
  spacing: z.enum(['compact', 'balanced', 'generous']),
  category_style: z.enum(['pill', 'underline-tab', 'minimal-text']),
})

export const BrandTokenSchema = z.object({
  store_name: z.string(),
  tagline: z.string(),
  colors: BrandColorsSchema,
  typography: BrandTypographyTokenSchema,
  layout: BrandLayoutTokenSchema,
  mood: z.string(),
  industry_hint: z.string(),
  brand_voice: z.string(),
})

// ─── AgentAction ─────────────────────────────────────────────────────────────

export const AgentActionTypeSchema = z.enum([
  'flash_sale', 'layout_morph', 'scarcity_price', 'recovery_offer', 'copy_rewrite',
])

export const AgentActionStatusSchema = z.enum([
  'pending', 'approved', 'dismissed', 'executed',
])

export const AgentActionSchema = z.object({
  id: z.string(),
  merchant_id: z.string(),
  promo_id: z.string(),
  action_type: AgentActionTypeSchema,
  trigger: z.string(),
  title: z.string(),
  description: z.string(),
  estimated_gmv: z.number(),
  estimated_confidence: z.number(),
  payload: z.record(z.any()),
  brand_check: z.string(),
  status: AgentActionStatusSchema,
  created_at: z.number(),
  approved_at: z.number().nullable().optional(),
  executed_at: z.number().nullable().optional(),
})
```

Also update `PublicStoreSchema` to add `brand_token`:
```typescript
export const PublicStoreSchema = z.object({
  store_name: z.string(),
  slug: z.string(),
  tagline: z.string(),
  palette: BrandPaletteSchema,
  typography: BrandTypographySchema,
  icons: BrandIconSetSchema,
  layout: LayoutConfigSchema,
  products: z.array(PublicProductSchema),
  promos: z.array(PromoSchema).default([]),
  categories: z.array(z.string()).default([]),
  brand_token: BrandTokenSchema.nullable().optional(),   // ← add
})
```

Add to the inferred types section:
```typescript
export type BrandColors = z.infer<typeof BrandColorsSchema>
export type BrandTypographyToken = z.infer<typeof BrandTypographyTokenSchema>
export type BrandLayoutToken = z.infer<typeof BrandLayoutTokenSchema>
export type BrandToken = z.infer<typeof BrandTokenSchema>
export type AgentActionType = z.infer<typeof AgentActionTypeSchema>
export type AgentActionStatus = z.infer<typeof AgentActionStatusSchema>
export type AgentAction = z.infer<typeof AgentActionSchema>
```

- [ ] **Step 5: Restart API and verify tables exist**

```bash
docker compose restart api
docker compose logs api --tail 30
```

Expected output includes: `Database tables synced` with no errors.

Then verify in DB:
```bash
docker compose exec db psql -U elevate -d elevate -c "\d agent_actions"
docker compose exec db psql -U elevate -d elevate -c "\d brand_profiles"
```

Expected: `agent_actions` table exists, `brand_profiles` has `brand_tokens` column.

- [ ] **Step 6: Commit**

```bash
git add analytics-brain/app/models/schemas.py analytics-brain/app/models/db_models.py analytics-brain/app/main.py storefront-ui/types/schemas.ts
git commit -m "[sprint-2] data layer: BrandToken + AgentAction schemas"
```

---

## Task 2: Brand Engine — BrandToken generation + seed products

**Files:**
- Modify: `analytics-brain/app/services/brand.py` (new BRAND_TOKEN_PROMPT, new `generate_brand_token()`, new `generate_seed_products()`)
- Modify: `analytics-brain/app/routers/onboarding.py` (store brand_tokens after generation)
- Modify: `analytics-brain/app/routers/store.py` (return brand_token in PublicStore)
- Create: `analytics-brain/app/routers/dev.py` (re-generate brand for existing stores)
- Modify: `analytics-brain/app/main.py` (register dev router)

**Interfaces:**
- Produces: `generate_brand_token(analysis, store_name, category) -> BrandToken`
- Produces: `generate_seed_products(store_name, brand_voice, industry_hint) -> list[dict]`
- Produces: `GET /api/store/{slug}` now includes `brand_token` field
- Produces: `POST /api/dev/regenerate-brand/{slug}` dev endpoint

- [ ] **Step 1: Add `BRAND_TOKEN_PROMPT` constant to `analytics-brain/app/services/brand.py`**

Insert after the existing `ICON_GENERATION_PROMPT` constant:

```python
BRAND_TOKEN_PROMPT = """You are a world-class brand strategist and creative director.
You receive a logo analysis and store details. Return ONLY a valid JSON object — no prose, no markdown.

{
  "store_name": "<unchanged from input>",
  "tagline": "<short, punchy — under 8 words>",
  "colors": {
    "primary": "<dominant brand color hex>",
    "accent": "<secondary/highlight hex>",
    "background": "<ideal store background hex>",
    "surface": "<card/panel background hex>",
    "text": "<primary text hex>",
    "text_muted": "<muted secondary text hex>"
  },
  "typography": {
    "display_font": "<Google Font name for headings>",
    "body_font": "<Google Font name for body>",
    "scale": "<compact|balanced|editorial>",
    "letter_spacing": "<tight|normal|wide>",
    "weight": "<light|regular|medium|bold>"
  },
  "layout": {
    "style": "<editorial|bold-grid|minimal-dark|warm-craft>",
    "hero_type": "<full-bleed|text-forward|split|texture-bg>",
    "product_grid": "<2col-featured|3col-equal|masonry>",
    "card_style": "<borderless|outlined|elevated|colored-bg>",
    "border_radius": "<2px|8px|16px|24px>",
    "spacing": "<compact|balanced|generous>",
    "category_style": "<pill|underline-tab|minimal-text>"
  },
  "mood": "<luxury-heritage|bold-playful|minimal-premium|organic-craft|tech-forward>",
  "industry_hint": "<fashion|beauty|food|tech|home|sport|other>",
  "brand_voice": "<3-6 word tone description e.g. refined, unhurried, quietly confident>"
}

Layout style guide — pick the ONE that matches this logo's visual DNA:
- editorial: serif font, muted luxury palette → Vogue/Net-a-Porter feel
- bold-grid: bright accent, sans-serif, playful logo → Glossier/Fenty feel  
- minimal-dark: dark/monochrome logo, tech premium → SSENSE/Rick Owens feel
- warm-craft: earthy tones, organic elements → Aesop/Graza feel

Be opinionated. Make this store unmistakable. Pure JSON. Nothing else."""


SEED_PRODUCTS_PROMPT = """You are generating realistic seed products for a new store.

Store: {store_name}
Industry: {industry_hint}
Brand voice: {brand_voice}

Generate exactly 6 products that would fit this store naturally. Return ONLY JSON:

[
  {{
    "name": "<product name>",
    "price": <realistic price as number>,
    "stock": <50-200>,
    "category": "<category>",
    "description": "<2-3 sentences in the brand voice>",
    "image_url": ""
  }}
]

Prices should reflect the brand's price point (luxury = higher, craft = mid, bold = accessible).
All 6 must be realistic products this specific store would actually sell.
Pure JSON array. Nothing else."""
```

- [ ] **Step 2: Add `generate_brand_token()` to `analytics-brain/app/services/brand.py`**

Add after the existing `generate_icons()` function:

```python
async def generate_brand_token(
    analysis: LogoAnalysis,
    store_name: str,
    category: str,
) -> BrandToken:
    """qwen-max produces the full BrandToken — layout DNA, typography, colors.

    Separate from generate_brand() so both can run from the onboarding flow
    without needing to change the existing GeneratedBrand path (keeps the
    interceptor and guard system working unchanged).
    """
    from app.models.schemas import BrandToken  # avoid circular at module load

    context = json.dumps({
        "store_name": store_name,
        "category": category,
        "logo_analysis": analysis.model_dump(),
    })

    raw = await _qwen_chat(
        model=get_settings().qwen_model,
        messages=[
            {"role": "system", "content": BRAND_TOKEN_PROMPT},
            {"role": "user", "content": context},
        ],
        max_tokens=1500,
        temperature=0.4,
        timeout=75.0,
    )

    data = _extract_json(raw)
    data["store_name"] = store_name  # never let Qwen rename

    try:
        return BrandToken.model_validate(data)
    except ValueError as e:
        raise BrandGenerationError(f"BrandToken failed schema validation: {e!s}") from e


async def generate_seed_products(
    store_name: str,
    brand_voice: str,
    industry_hint: str,
) -> list[dict]:
    """qwen-max generates 6 industry-appropriate seed products for the demo.

    Returns raw dicts (name, price, stock, category, description, image_url)
    ready to insert as ProductDB rows. Falls back to empty list on failure so
    it never blocks the onboarding flow.
    """
    prompt = SEED_PRODUCTS_PROMPT.format(
        store_name=store_name,
        industry_hint=industry_hint,
        brand_voice=brand_voice,
    )

    try:
        raw = await _qwen_chat(
            model=get_settings().qwen_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.6,
            timeout=60.0,
        )
        # Seed products come back as a JSON array, not an object
        text = raw.strip()
        # Strip markdown fences
        text = _FENCE_RE.sub("", text)
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end > start:
            products = json.loads(text[start:end + 1])
            if isinstance(products, list):
                return products[:6]
    except Exception as e:
        logger.warning(f"[brand] seed products generation failed: {e}")
    return []
```

- [ ] **Step 3: Update `analytics-brain/app/routers/onboarding.py` to store `brand_tokens`**

Find the section in `onboarding.py` where `BrandPackage` is stored in `BrandProfileDB`. After the existing `generated_brand` save, add parallel generation of `brand_token`:

```python
# After existing brand generation, run BrandToken generation concurrently with icons
from app.services.brand import generate_brand_token, generate_seed_products

brand_token, seed_products_raw = await asyncio.gather(
    generate_brand_token(pkg.analysis, merchant.store_name, merchant.category),
    generate_seed_products(
        store_name=merchant.store_name,
        brand_voice=pkg.brand.brand_voice_profile,
        industry_hint=pkg.brand.suggested_categories[0] if pkg.brand.suggested_categories else "other",
    ),
    return_exceptions=True,
)

# Store brand_tokens if generation succeeded
if isinstance(brand_token, BrandToken):
    brand_profile.brand_tokens = brand_token.model_dump()
    await db.commit()

# Insert seed products if store has no products yet
existing_count = await db.scalar(
    select(func.count()).where(ProductDB.merchant_id == merchant.id)
)
if existing_count == 0 and isinstance(seed_products_raw, list):
    for raw_p in seed_products_raw:
        if not isinstance(raw_p, dict) or not raw_p.get("name"):
            continue
        db.add(ProductDB(
            id=str(uuid4()),
            merchant_id=merchant.id,
            name=str(raw_p.get("name", "Product"))[:255],
            description=str(raw_p.get("description", "")),
            price=float(raw_p.get("price", 10.0)),
            cost_price=float(raw_p.get("price", 10.0)) * 0.5,
            stock=int(raw_p.get("stock", 100)),
            category=str(raw_p.get("category", ""))[:100],
            image_urls=[],
            qwen_generated_description=True,
        ))
    await db.commit()
```

You'll need to import `asyncio`, `uuid4`, `func` from sqlalchemy, and `ProductDB` at the top of the file if not already present.

- [ ] **Step 4: Update `analytics-brain/app/routers/store.py` to return `brand_token`**

In `get_public_store()`, after building the `PublicStore` response, add `brand_token`:

```python
# Load brand_token from brand_profile if available
brand_token_data = None
brand_profile_row = await db.get(BrandProfileDB, merchant.id)
if brand_profile_row and brand_profile_row.brand_tokens:
    try:
        from app.models.schemas import BrandToken
        brand_token_data = BrandToken.model_validate(brand_profile_row.brand_tokens)
    except (ValueError, TypeError):
        pass

return PublicStore(
    store_name=merchant.store_name,
    slug=merchant.slug,
    tagline=pkg.brand.tagline,
    palette=pkg.brand.palette,
    typography=pkg.brand.typography,
    icons=pkg.brand.icons,
    layout=layout,
    products=products,
    promos=promos,
    categories=categories,
    brand_token=brand_token_data,   # ← add
)
```

- [ ] **Step 5: Create `analytics-brain/app/routers/dev.py`**

```python
"""
Dev-only endpoints — regenerate brand data for existing stores.
Only registered in development. Never reachable in production.
"""
from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.db_models import MerchantDB, BrandProfileDB, ProductDB
from app.models.schemas import BrandToken
from app.services.brand import generate_brand_token, generate_seed_products, analyze_logo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dev", tags=["dev"])


@router.post("/regenerate-brand/{slug}")
async def regenerate_brand(slug: str, db: AsyncSession = Depends(get_db)):
    """Re-generate BrandToken for an existing store using its current logo URL.
    Use this to upgrade existing Haree / Crest stores to the BrandToken schema.
    """
    merchant = await db.scalar(select(MerchantDB).where(MerchantDB.slug == slug))
    if not merchant:
        raise HTTPException(status_code=404, detail="Store not found")
    if not merchant.logo_url:
        raise HTTPException(status_code=422, detail="Store has no logo URL")

    brand_profile = await db.get(BrandProfileDB, merchant.id)
    if not brand_profile:
        raise HTTPException(status_code=422, detail="Store has no brand profile yet")

    logger.info(f"[dev] Regenerating BrandToken for {slug}")

    analysis = await analyze_logo(merchant.logo_url)
    brand_token = await generate_brand_token(analysis, merchant.store_name, merchant.category)

    brand_profile.brand_tokens = brand_token.model_dump()
    await db.commit()

    logger.info(f"[dev] BrandToken saved for {slug}: layout.style={brand_token.layout.style}")
    return {"ok": True, "slug": slug, "layout_style": brand_token.layout.style, "brand_token": brand_token.model_dump()}
```

- [ ] **Step 6: Register dev router in `analytics-brain/app/main.py`**

```python
from app.routers import ws, upload, auth, onboarding, products, store, shop, merchant, dev

# In the startup section, add:
if settings.app_env == "development":
    app.include_router(dev.router)
```

- [ ] **Step 7: Restart API and regenerate Haree + Crest**

```bash
docker compose restart api
docker compose logs api --tail 20
```

Then re-generate:
```bash
curl -X POST http://localhost:9000/api/dev/regenerate-brand/haree
curl -X POST http://localhost:9000/api/dev/regenerate-brand/crest
```

Expected response includes `"ok": true` and a `"layout_style"` field with one of the four variants. Log which style Qwen chose for each store.

Verify with:
```bash
curl http://localhost:9000/api/store/haree | python -m json.tool | grep -A 20 '"brand_token"'
```

- [ ] **Step 8: Commit**

```bash
git add analytics-brain/app/services/brand.py analytics-brain/app/routers/onboarding.py analytics-brain/app/routers/store.py analytics-brain/app/routers/dev.py analytics-brain/app/main.py
git commit -m "[sprint-2] brand engine: BrandToken generation + seed products"
```

---

## Task 3: Decision Engine — Behavior events + Qwen autonomous decisions

**Files:**
- Modify: `analytics-brain/app/core/redis.py` (add `Keys.events()`)
- Create: `analytics-brain/app/services/behavior_tracker.py`
- Create: `analytics-brain/app/services/decision_engine.py`
- Create: `analytics-brain/app/routers/behavior.py`
- Create: `analytics-brain/app/routers/agent.py`
- Create: `analytics-brain/app/routers/dashboard.py`
- Modify: `analytics-brain/app/main.py` (register three new routers)
- Modify: `storefront-ui/lib/api.ts` (add behavior/agent/dashboard calls)

**Interfaces:**
- Produces: `POST /api/behavior/event/{slug}` — ingest customer event
- Produces: `GET /api/agent/actions/{slug}/pending` → `{ actions: AgentAction[] }`
- Produces: `POST /api/agent/actions/{action_id}/approve` → `{ action: AgentAction }`
- Produces: `POST /api/agent/actions/{action_id}/dismiss` → `{ action: AgentAction }`
- Produces: `POST /api/behavior/simulate/{slug}` — trigger demo scenario
- Produces: `GET /api/dashboard/{slug}` → attribution data

- [ ] **Step 1: Add `Keys.events()` to `analytics-brain/app/core/redis.py`**

Add inside the `Keys` class after `Keys.cart`:
```python
@staticmethod
def events(merchant_id: str) -> str:
    return f"elevate:{merchant_id}:events"
```

Also add to `TTL`:
```python
EVENTS = 3600  # 1 hour — behavior events; only need last N for decision cycle
```

- [ ] **Step 2: Create `analytics-brain/app/services/behavior_tracker.py`**

```python
"""
Behavior event ingestion and anomaly threshold checking.
Anomaly detection is deterministic (env-var thresholds) — no statistics.
"""
from __future__ import annotations

import json
import os
import time
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

ANOMALY_THRESHOLD = int(os.getenv("ANOMALY_THRESHOLD", "5"))
ANOMALY_WINDOW_SECONDS = int(os.getenv("ANOMALY_WINDOW_SECONDS", "30"))


async def push_event(redis: "Redis", merchant_id: str, event: dict) -> None:
    """Append a behavior event to the Redis list and trim to 500."""
    from app.core.redis import Keys, TTL
    key = Keys.events(merchant_id)
    await redis.lpush(key, json.dumps(event))
    await redis.ltrim(key, 0, 499)
    await redis.expire(key, TTL.EVENTS)


async def count_abandons_in_window(redis: "Redis", merchant_id: str) -> int:
    """Count abandon events in the last ANOMALY_WINDOW_SECONDS seconds."""
    from app.core.redis import Keys
    key = Keys.events(merchant_id)
    raw_events = await redis.lrange(key, 0, 99)
    now = time.time()
    count = 0
    for raw in raw_events:
        try:
            ev = json.loads(raw)
            if (
                ev.get("event_type") == "abandon"
                and now - float(ev.get("timestamp", 0)) < ANOMALY_WINDOW_SECONDS
            ):
                count += 1
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return count


async def count_views_in_window(redis: "Redis", merchant_id: str) -> int:
    """Count view events in the last ANOMALY_WINDOW_SECONDS seconds."""
    from app.core.redis import Keys
    key = Keys.events(merchant_id)
    raw_events = await redis.lrange(key, 0, 99)
    now = time.time()
    count = 0
    for raw in raw_events:
        try:
            ev = json.loads(raw)
            if (
                ev.get("event_type") == "view"
                and now - float(ev.get("timestamp", 0)) < ANOMALY_WINDOW_SECONDS
            ):
                count += 1
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return count


def anomaly_description(abandon_count: int, view_count: int) -> str | None:
    """Return a human-readable anomaly description or None if no anomaly."""
    if abandon_count >= ANOMALY_THRESHOLD:
        return f"Cart abandon surge: {abandon_count} abandons in {ANOMALY_WINDOW_SECONDS}s — customers are leaving without buying"
    if view_count >= ANOMALY_THRESHOLD * 4:
        return f"Velocity spike: {view_count} views in {ANOMALY_WINDOW_SECONDS}s — products going viral"
    return None
```

- [ ] **Step 3: Create `analytics-brain/app/services/decision_engine.py`**

```python
"""
Qwen decision engine — reads store state + behavior anomaly, fires one action.
Called when behavior_tracker detects an anomaly threshold crossing.
"""
from __future__ import annotations

import json
import logging
import secrets
import time
from uuid import uuid4
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import AgentAction, AgentActionStatus, WSEventType
from app.models.db_models import AgentActionDB, MerchantDB, BrandProfileDB, ProductDB
from app.services.brand import _qwen_chat, _extract_json, BrandGenerationError
from app.core.ws_manager import manager
from app.core.config import get_settings

logger = logging.getLogger(__name__)

DECISION_PROMPT = """You are the autonomous commerce brain for "{store_name}".
Brand mood: {mood} | Voice: {brand_voice}
Brand rules (never violate): {brand_rules_summary}

Current products: {products_summary}
Behavior anomaly: {anomaly_description}

Decide ONE action. Return ONLY this JSON:
{{
  "action_type": "<flash_sale|layout_morph|scarcity_price|recovery_offer|copy_rewrite>",
  "trigger": "<1 sentence: what caused this>",
  "title": "<merchant-facing card title, max 8 words>",
  "description": "<merchant-facing description, max 20 words>",
  "estimated_gmv": <estimated revenue impact as number>,
  "estimated_confidence": <0.0-1.0>,
  "payload": {{
    "flash_sale fields if action_type=flash_sale": {{
      "discount_percent": 15,
      "duration_minutes": 30,
      "target": "best_seller"
    }},
    "layout_morph fields if action_type=layout_morph": {{
      "new_grid": "2col-featured",
      "reason": "highlight trending product"
    }},
    "recovery_offer fields if action_type=recovery_offer": {{
      "offer": "free_shipping",
      "message": "Come back — we saved your cart"
    }}
  }},
  "brand_check": "<confirm this respects brand rules or flag conflict>"
}}

The merchant approves before execution. Make it compelling.
Return ONLY JSON."""


async def run_decision_cycle(
    merchant_id: str,
    anomaly_desc: str,
    db: "AsyncSession",
    redis: "Redis",
) -> AgentAction | None:
    """Run a full Qwen decision cycle and persist + broadcast the result.

    Returns the created AgentAction or None if:
    - there is already a pending action (one at a time)
    - Qwen returns garbage we can't trust
    """
    from sqlalchemy import select

    # Gate: only one pending action at a time per store
    existing = await db.scalar(
        select(AgentActionDB)
        .where(AgentActionDB.merchant_id == merchant_id)
        .where(AgentActionDB.status == "pending")
    )
    if existing:
        logger.info(f"[decision] skipping cycle — pending action already exists for {merchant_id}")
        return None

    merchant = await db.get(MerchantDB, merchant_id)
    if not merchant:
        return None

    brand_profile = await db.get(BrandProfileDB, merchant_id)
    brand_voice = "professional, friendly"
    mood = "balanced"
    brand_rules_summary = "maintain brand integrity"
    if brand_profile:
        gb = brand_profile.generated_brand or {}
        brand_voice = gb.get("brand", {}).get("brand_voice_profile", brand_voice)
        mood = gb.get("brand", {}).get("layout_variant", mood)
        guards = gb.get("guards", {})
        rules = guards.get("rules", [])
        brand_rules_summary = "; ".join(r.get("description", "") for r in rules[:3]) or brand_rules_summary

    products_result = await db.execute(
        select(ProductDB)
        .where(ProductDB.merchant_id == merchant_id)
        .where(ProductDB.is_active == True)
        .limit(10)
    )
    products = products_result.scalars().all()
    products_summary = ", ".join(
        f"{p.name} (${p.price}, stock: {p.stock})" for p in products
    ) or "no products yet"

    prompt = DECISION_PROMPT.format(
        store_name=merchant.store_name,
        mood=mood,
        brand_voice=brand_voice,
        brand_rules_summary=brand_rules_summary,
        products_summary=products_summary,
        anomaly_description=anomaly_desc,
    )

    try:
        raw = await _qwen_chat(
            model=get_settings().qwen_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.5,
            timeout=45.0,
        )
        data = _extract_json(raw)
    except BrandGenerationError as e:
        logger.error(f"[decision] Qwen failed for {merchant_id}: {e}")
        return None

    promo_id = f"ELEV_{merchant_id[:4].upper()}_{secrets.token_hex(3).upper()}"
    now = int(time.time() * 1000)

    action_db = AgentActionDB(
        id=str(uuid4()),
        merchant_id=merchant_id,
        promo_id=promo_id,
        action_type=data.get("action_type", "flash_sale"),
        trigger=str(data.get("trigger", anomaly_desc))[:500],
        title=str(data.get("title", "Action ready"))[:200],
        description=str(data.get("description", ""))[:500],
        estimated_gmv=float(data.get("estimated_gmv", 0) or 0),
        estimated_confidence=min(1.0, float(data.get("estimated_confidence", 0.7) or 0.7)),
        payload=data.get("payload") or {},
        brand_check=str(data.get("brand_check", ""))[:500],
        status="pending",
        created_at=now,
    )
    db.add(action_db)
    await db.commit()
    await db.refresh(action_db)

    action = AgentAction(
        id=action_db.id,
        merchant_id=action_db.merchant_id,
        promo_id=action_db.promo_id,
        action_type=action_db.action_type,
        trigger=action_db.trigger,
        title=action_db.title,
        description=action_db.description,
        estimated_gmv=action_db.estimated_gmv,
        estimated_confidence=action_db.estimated_confidence,
        payload=action_db.payload,
        brand_check=action_db.brand_check,
        status=AgentActionStatus(action_db.status),
        created_at=action_db.created_at,
    )

    # Push to merchant terminal via WebSocket
    from app.models.schemas import WSMessage
    await manager.push_to_terminal(
        merchant_id,
        WSMessage(
            event=WSEventType.AGENT_ACTION,
            payload={"action": action.model_dump()},
            merchant_id=merchant_id,
            timestamp=now,
        ),
    )

    logger.info(f"[decision] fired {action.action_type} action {action.id} for {merchant_id}")
    return action
```

- [ ] **Step 4: Create `analytics-brain/app/routers/behavior.py`**

```python
"""
Behavior event ingestion — customer browse events flow in here.
Anomaly detection triggers the decision cycle automatically.
"""
from __future__ import annotations

import time
import logging

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.models.db_models import MerchantDB
from app.services.behavior_tracker import (
    push_event,
    count_abandons_in_window,
    count_views_in_window,
    anomaly_description,
)
from app.services.decision_engine import run_decision_cycle

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/behavior", tags=["behavior"])


class BehaviorEventIn(BaseModel):
    event_type: str   # view | add_to_cart | abandon | purchase | search
    product_id: str = ""
    session_id: str
    timestamp: float = 0.0  # unix seconds; defaults to now if 0


@router.post("/event/{slug}")
async def ingest_event(
    slug: str,
    event: BehaviorEventIn,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    merchant = await db.scalar(select(MerchantDB).where(MerchantDB.slug == slug))
    if not merchant:
        raise HTTPException(status_code=404, detail="Store not found")

    ts = event.timestamp if event.timestamp > 0 else time.time()
    redis = await get_redis()

    await push_event(redis, merchant.id, {
        "event_type": event.event_type,
        "product_id": event.product_id,
        "session_id": event.session_id,
        "timestamp": ts,
    })

    # Check anomaly thresholds in background so ingest returns immediately
    async def _check():
        abandons = await count_abandons_in_window(redis, merchant.id)
        views = await count_views_in_window(redis, merchant.id)
        desc = anomaly_description(abandons, views)
        if desc:
            await run_decision_cycle(merchant.id, desc, db, redis)

    background.add_task(_check)
    return {"ok": True}


# ─── Simulation ───────────────────────────────────────────────────────────────

DEMO_SCENARIO = [
    {"event_type": "view",        "product_id": "__first__", "delay": 0.0},
    {"event_type": "view",        "product_id": "__first__", "delay": 0.3},
    {"event_type": "add_to_cart", "product_id": "__first__", "delay": 0.6},
    {"event_type": "abandon",     "product_id": "__first__", "delay": 1.0},
    {"event_type": "view",        "product_id": "__first__", "delay": 1.2},
    {"event_type": "abandon",     "product_id": "__first__", "delay": 1.5},
    {"event_type": "abandon",     "product_id": "__first__", "delay": 1.8},
    {"event_type": "abandon",     "product_id": "__first__", "delay": 2.1},
    {"event_type": "abandon",     "product_id": "__first__", "delay": 2.4},
    {"event_type": "view",        "product_id": "__first__", "delay": 2.7},
]


@router.post("/simulate/{slug}")
async def simulate_activity(
    slug: str,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Fire a pre-scripted event sequence that crosses the abandon anomaly threshold.
    Used by the merchant terminal 'Simulate customer activity' button for the demo.
    """
    import asyncio

    merchant = await db.scalar(select(MerchantDB).where(MerchantDB.slug == slug))
    if not merchant:
        raise HTTPException(status_code=404, detail="Store not found")

    # Get first product id for the scenario
    from app.models.db_models import ProductDB
    first_product = await db.scalar(
        select(ProductDB)
        .where(ProductDB.merchant_id == merchant.id)
        .where(ProductDB.is_active == True)
    )
    product_id = first_product.id if first_product else "demo-product"

    async def _run_scenario():
        redis = await get_redis()
        now = time.time()
        for i, ev in enumerate(DEMO_SCENARIO):
            event_data = {
                "event_type": ev["event_type"],
                "product_id": product_id,
                "session_id": f"demo-session-{i}",
                "timestamp": now + ev["delay"],
            }
            await push_event(redis, merchant.id, event_data)
            await asyncio.sleep(0.1)

        # Run anomaly check after scenario completes
        abandons = await count_abandons_in_window(redis, merchant.id)
        views = await count_views_in_window(redis, merchant.id)
        desc = anomaly_description(abandons, views)
        if desc:
            from sqlalchemy.ext.asyncio import AsyncSession
            from app.core.database import get_engine
            async with AsyncSession(get_engine()) as session:
                await run_decision_cycle(merchant.id, desc, session, redis)

    background.add_task(_run_scenario)
    return {"ok": True, "scenario": "cart_abandon_surge", "events": len(DEMO_SCENARIO)}
```

- [ ] **Step 5: Create `analytics-brain/app/routers/agent.py`**

```python
"""
Agent action management — pending, approve, dismiss.
Approve executes the payload and broadcasts the store update via WebSocket.
"""
from __future__ import annotations

import time
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.db_models import AgentActionDB, MerchantDB, ProductDB, PromoDB
from app.models.schemas import AgentAction, AgentActionStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])


def _to_schema(row: AgentActionDB) -> AgentAction:
    return AgentAction(
        id=row.id,
        merchant_id=row.merchant_id,
        promo_id=row.promo_id,
        action_type=row.action_type,
        trigger=row.trigger,
        title=row.title,
        description=row.description,
        estimated_gmv=row.estimated_gmv,
        estimated_confidence=row.estimated_confidence,
        payload=row.payload,
        brand_check=row.brand_check,
        status=AgentActionStatus(row.status),
        created_at=row.created_at,
        approved_at=row.approved_at,
        executed_at=row.executed_at,
    )


@router.get("/actions/{slug}/pending")
async def get_pending_actions(slug: str, db: AsyncSession = Depends(get_db)):
    merchant = await db.scalar(select(MerchantDB).where(MerchantDB.slug == slug))
    if not merchant:
        raise HTTPException(status_code=404, detail="Store not found")

    result = await db.execute(
        select(AgentActionDB)
        .where(AgentActionDB.merchant_id == merchant.id)
        .where(AgentActionDB.status == "pending")
        .order_by(AgentActionDB.created_at.desc())
    )
    rows = result.scalars().all()
    return {"actions": [_to_schema(r).model_dump() for r in rows]}


@router.post("/actions/{action_id}/approve")
async def approve_action(action_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(AgentActionDB, action_id)
    if not row:
        raise HTTPException(status_code=404, detail="Action not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail=f"Action is already {row.status}")

    now = int(time.time() * 1000)
    row.status = "approved"
    row.approved_at = now

    # Execute payload — apply flash_sale as a promo, layout_morph updates state, etc.
    await _execute_payload(row, db)

    row.status = "executed"
    row.executed_at = int(time.time() * 1000)
    await db.commit()

    # Broadcast store update to all WS connections
    await _broadcast_state_update(row.merchant_id)

    return {"action": _to_schema(row).model_dump()}


@router.post("/actions/{action_id}/dismiss")
async def dismiss_action(action_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(AgentActionDB, action_id)
    if not row:
        raise HTTPException(status_code=404, detail="Action not found")
    row.status = "dismissed"
    await db.commit()
    return {"action": _to_schema(row).model_dump()}


async def _execute_payload(row: AgentActionDB, db: AsyncSession) -> None:
    """Apply the action's payload to the live store state."""
    from app.services import delta as delta_svc
    from app.models.schemas import Promo

    payload = row.payload or {}

    if row.action_type == "flash_sale":
        discount = float(payload.get("discount_percent", 15))
        duration = int(payload.get("duration_minutes", 30))
        expires_at = int(time.time() * 1000) + duration * 60 * 1000

        state = await delta_svc.load_state(row.merchant_id)
        if state:
            promo = Promo(
                id=row.promo_id,
                product_id=list(state.products.keys())[0] if state.products else "all",
                discount_percent=discount,
                label=f"Flash Sale — {int(discount)}% off",
                expires_at=expires_at,
                triggered_by="auto",
            )
            state.active_promos[row.promo_id] = promo
            await delta_svc.save_state(row.merchant_id, state)

    elif row.action_type == "layout_morph":
        state = await delta_svc.load_state(row.merchant_id)
        if state:
            new_grid = payload.get("new_grid")
            if new_grid:
                from app.models.schemas import LayoutVariant
                try:
                    state.layout_config.layout_variant = LayoutVariant(new_grid)
                except ValueError:
                    pass
            await delta_svc.save_state(row.merchant_id, state)

    # recovery_offer, scarcity_price, copy_rewrite — log for now, extend post-hackathon
    else:
        logger.info(f"[agent] action type {row.action_type} logged but not auto-applied")


async def _broadcast_state_update(merchant_id: str) -> None:
    from app.core.ws_manager import manager
    from app.models.schemas import WSMessage, WSEventType
    from app.services import delta as delta_svc

    state = await delta_svc.load_state(merchant_id)
    if not state:
        return

    import json
    msg = WSMessage(
        event=WSEventType.STATE_UPDATED,
        payload={"state": json.loads(state.model_dump_json()), "source": "agent"},
        merchant_id=merchant_id,
        timestamp=int(time.time() * 1000),
    )
    await manager.push_to_all(merchant_id, msg)
```

- [ ] **Step 6: Create `analytics-brain/app/routers/dashboard.py`**

```python
"""
Attribution dashboard — shows what the AI drove and what the fee would be.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.db_models import AgentActionDB, MerchantDB, OrderDB

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

ELEVATE_FEE_RATE = 0.10  # 10% of attributed GMV


@router.get("/{slug}")
async def get_dashboard(slug: str, db: AsyncSession = Depends(get_db)):
    merchant = await db.scalar(select(MerchantDB).where(MerchantDB.slug == slug))
    if not merchant:
        raise HTTPException(status_code=404, detail="Store not found")

    # All orders for this store
    all_orders = await db.scalars(
        select(OrderDB).where(OrderDB.merchant_id == merchant.id)
    )
    orders = list(all_orders)
    total_gmv = sum(float(o.total) for o in orders)

    # Executed actions with their attributed orders
    executed = await db.scalars(
        select(AgentActionDB)
        .where(AgentActionDB.merchant_id == merchant.id)
        .where(AgentActionDB.status == "executed")
        .order_by(AgentActionDB.executed_at.desc())
    )
    actions = list(executed)

    # Build promo_id → orders map
    promo_to_orders: dict[str, list[OrderDB]] = {}
    for order in orders:
        if order.promo_applied:
            promo_to_orders.setdefault(order.promo_applied, []).append(order)

    action_rows = []
    elevate_attributed_gmv = 0.0

    for action in actions:
        attributed = promo_to_orders.get(action.promo_id, [])
        attributed_gmv = sum(float(o.total) for o in attributed)
        fee = round(attributed_gmv * ELEVATE_FEE_RATE, 2)
        elevate_attributed_gmv += attributed_gmv

        action_rows.append({
            "promo_id": action.promo_id,
            "action_type": action.action_type,
            "title": action.title,
            "trigger": action.trigger,
            "estimated_gmv": action.estimated_gmv,
            "executed_at": action.executed_at,
            "attributed_orders": len(attributed),
            "attributed_gmv": round(attributed_gmv, 2),
            "fee": fee,
        })

    return {
        "store_name": merchant.store_name,
        "total_gmv": round(total_gmv, 2),
        "elevate_attributed_gmv": round(elevate_attributed_gmv, 2),
        "elevate_fee": round(elevate_attributed_gmv * ELEVATE_FEE_RATE, 2),
        "actions": action_rows,
    }
```

- [ ] **Step 7: Register new routers in `analytics-brain/app/main.py`**

```python
from app.routers import ws, upload, auth, onboarding, products, store, shop, merchant, dev, behavior, agent, dashboard

app.include_router(behavior.router)
app.include_router(agent.router)
app.include_router(dashboard.router)
```

- [ ] **Step 8: Write test for behavior event endpoint**

Create `analytics-brain/tests/test_behavior.py`:

```python
"""Test behavior event ingestion — no Qwen calls, no WS, just Redis writes."""
import pytest
import httpx

BASE = "http://localhost:9000"


def test_behavior_event_ingest():
    resp = httpx.post(
        f"{BASE}/api/behavior/event/haree",
        json={
            "event_type": "view",
            "product_id": "test-product",
            "session_id": "test-session-001",
            "timestamp": 1751000000.0,
        },
        timeout=5,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True


def test_get_pending_actions_empty():
    resp = httpx.get(f"{BASE}/api/agent/actions/haree/pending", timeout=5)
    assert resp.status_code == 200, resp.text
    assert "actions" in resp.json()


def test_dashboard():
    resp = httpx.get(f"{BASE}/api/dashboard/haree", timeout=5)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "total_gmv" in data
    assert "actions" in data
```

- [ ] **Step 9: Run tests and verify**

```bash
docker compose restart api
docker compose logs api --tail 20
docker compose exec api pytest analytics-brain/tests/test_behavior.py -v
```

Expected: 3 tests PASS.

Verify simulate endpoint:
```bash
curl -X POST http://localhost:9000/api/behavior/simulate/haree
```

Expected: `{"ok": true, "scenario": "cart_abandon_surge", "events": 10}`

Wait ~5 seconds (background task), then check for a pending action:
```bash
curl http://localhost:9000/api/agent/actions/haree/pending
```

Expected: `{"actions": [{"action_type": "...", "title": "...", ...}]}`

- [ ] **Step 10: Commit**

```bash
git add analytics-brain/app/core/redis.py analytics-brain/app/services/behavior_tracker.py analytics-brain/app/services/decision_engine.py analytics-brain/app/routers/behavior.py analytics-brain/app/routers/agent.py analytics-brain/app/routers/dashboard.py analytics-brain/app/main.py analytics-brain/tests/test_behavior.py
git commit -m "[sprint-2] decision engine: behavior events + Qwen autonomous actions"
```

---

## Task 4: Frontend — Layout Variant System

**Files:**
- Create: `storefront-ui/components/store/StoreShell.tsx`
- Create: `storefront-ui/components/store/HeroSection.tsx`
- Create: `storefront-ui/components/store/CategoryNav.tsx`
- Modify: `storefront-ui/components/storefront/ProductGrid.tsx` (add 3 grid + 4 card variants)
- Modify: `storefront-ui/components/storefront/ProductCard.tsx` (add 4 card variants)
- Modify: `storefront-ui/components/storefront/Storefront.tsx` (use BrandToken + StoreShell)
- Modify: `storefront-ui/lib/api.ts` (add behavior/agent/dashboard API methods)

**Interfaces:**
- Consumes: `PublicStore.brand_token` from Task 2
- Produces: `StoreShell` — themed wrapper injecting CSS vars from BrandToken
- Produces: `HeroSection` — 4 variants: full-bleed | text-forward | split | texture-bg
- Produces: `CategoryNav` — 3 variants: pill | underline-tab | minimal-text
- Produces: Updated `ProductGrid` — 3 grid variants
- Produces: Updated `ProductCard` — 4 card variants

- [ ] **Step 1: Create `storefront-ui/components/store/StoreShell.tsx`**

```tsx
'use client'

import { useEffect } from 'react'
import type { BrandToken } from '@/types/schemas'

interface StoreShellProps {
  brandToken: BrandToken
  children: React.ReactNode
}

/**
 * Injects BrandToken CSS variables into :root for this store.
 * All layout-variant-aware children read from these variables.
 * The data-layout attribute drives Tailwind/CSS selector variants.
 */
export function StoreShell({ brandToken, children }: StoreShellProps) {
  const { colors, typography, layout } = brandToken

  // Load Google Fonts for this store's brand
  useEffect(() => {
    const fams = [typography.display_font, typography.body_font]
      .filter(Boolean)
      .map((f) => `family=${f.trim().replace(/\s+/g, '+')}:wght@300;400;500;600;700`)
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = `https://fonts.googleapis.com/css2?${fams.join('&')}&display=swap`
    document.head.appendChild(link)
    return () => { document.head.removeChild(link) }
  }, [typography.display_font, typography.body_font])

  const cssVars = {
    '--s-primary': colors.primary,
    '--s-accent': colors.accent,
    '--s-bg': colors.background,
    '--s-surface': colors.surface,
    '--s-text': colors.text,
    '--s-text-muted': colors.text_muted,
    '--s-display': `'${typography.display_font}', serif`,
    '--s-body': `'${typography.body_font}', sans-serif`,
    '--s-radius': layout.border_radius,
    '--s-spacing': layout.spacing === 'compact' ? '1rem' : layout.spacing === 'generous' ? '2.5rem' : '1.5rem',
    '--s-letter-spacing': layout.letter_spacing === 'tight' ? '-0.02em' : layout.letter_spacing === 'wide' ? '0.08em' : '0',
    background: colors.background,
    color: colors.text,
    fontFamily: `'${typography.body_font}', sans-serif`,
    minHeight: '100vh',
  } as React.CSSProperties

  return (
    <div
      style={cssVars}
      data-layout={layout.style}
      data-spacing={layout.spacing}
    >
      {children}
    </div>
  )
}
```

- [ ] **Step 2: Create `storefront-ui/components/store/HeroSection.tsx`**

```tsx
'use client'

import { motion, useReducedMotion } from 'framer-motion'
import type { BrandToken } from '@/types/schemas'

interface HeroSectionProps {
  brandToken: BrandToken
  storeName: string
  tagline: string
  logoMark: string
}

export function HeroSection({ brandToken, storeName, tagline, logoMark }: HeroSectionProps) {
  const prefersReduced = useReducedMotion()
  const fade = { initial: { opacity: 0, y: prefersReduced ? 0 : 20 }, animate: { opacity: 1, y: 0 } }
  const { layout, colors, typography } = brandToken

  if (layout.hero_type === 'full-bleed') {
    return (
      <motion.header {...fade} transition={{ duration: 0.6, ease: [0.4, 0, 0.2, 1] }}
        className="relative w-full flex flex-col items-center justify-center text-center py-24 px-6"
        style={{ background: `linear-gradient(160deg, ${colors.primary}22 0%, ${colors.background} 60%)` }}
      >
        <div className="w-20 h-20 mb-6 [&>svg]:w-full [&>svg]:h-full"
          dangerouslySetInnerHTML={{ __html: logoMark }} />
        <h1 className="text-4xl md:text-6xl font-bold tracking-tight mb-4"
          style={{ fontFamily: 'var(--s-display)', letterSpacing: 'var(--s-letter-spacing)' }}>
          {storeName}
        </h1>
        <p className="text-lg max-w-md" style={{ color: colors.text_muted }}>{tagline}</p>
      </motion.header>
    )
  }

  if (layout.hero_type === 'text-forward') {
    return (
      <motion.header {...fade} transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
        className="py-20 px-6 max-w-3xl mx-auto">
        <p className="text-sm font-mono uppercase tracking-widest mb-4" style={{ color: colors.accent }}>
          {brandToken.mood.replace('-', ' ')}
        </p>
        <h1 className="text-5xl md:text-7xl font-bold leading-none mb-6"
          style={{ fontFamily: 'var(--s-display)', letterSpacing: 'var(--s-letter-spacing)' }}>
          {storeName}
        </h1>
        <p className="text-xl" style={{ color: colors.text_muted }}>{tagline}</p>
      </motion.header>
    )
  }

  if (layout.hero_type === 'split') {
    return (
      <motion.header {...fade} transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
        className="flex flex-col md:flex-row items-center gap-8 py-16 px-6">
        <div className="flex-1">
          <h1 className="text-4xl md:text-5xl font-bold mb-4"
            style={{ fontFamily: 'var(--s-display)', letterSpacing: 'var(--s-letter-spacing)' }}>
            {storeName}
          </h1>
          <p className="text-lg" style={{ color: colors.text_muted }}>{tagline}</p>
        </div>
        <div className="w-32 h-32 [&>svg]:w-full [&>svg]:h-full"
          dangerouslySetInnerHTML={{ __html: logoMark }} />
      </motion.header>
    )
  }

  // texture-bg
  return (
    <motion.header {...fade} transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
      className="relative w-full text-center py-20 px-6 overflow-hidden"
      style={{ background: `radial-gradient(ellipse at 50% 0%, ${colors.primary}33 0%, ${colors.background} 70%)` }}
    >
      <div className="relative z-10">
        <div className="w-16 h-16 mx-auto mb-5 [&>svg]:w-full [&>svg]:h-full"
          dangerouslySetInnerHTML={{ __html: logoMark }} />
        <h1 className="text-4xl md:text-5xl font-bold mb-3"
          style={{ fontFamily: 'var(--s-display)', letterSpacing: 'var(--s-letter-spacing)' }}>
          {storeName}
        </h1>
        <p style={{ color: colors.accent }}>{tagline}</p>
      </div>
    </motion.header>
  )
}
```

- [ ] **Step 3: Create `storefront-ui/components/store/CategoryNav.tsx`**

```tsx
'use client'

import type { BrandToken } from '@/types/schemas'

interface CategoryNavProps {
  categories: string[]
  active: string | null
  onSelect: (cat: string | null) => void
  brandToken: BrandToken
}

export function CategoryNav({ categories, active, onSelect, brandToken }: CategoryNavProps) {
  if (categories.length === 0) return null
  const { layout, colors } = brandToken
  const style = layout.category_style

  if (style === 'pill') {
    return (
      <div className="flex flex-wrap gap-2 mb-8">
        {['All', ...categories].map((c) => {
          const isActive = c === 'All' ? active === null : active === c
          return (
            <button key={c} onClick={() => onSelect(c === 'All' ? null : c)}
              className="px-4 py-1.5 rounded-full text-sm font-medium transition-colors"
              style={isActive
                ? { background: colors.accent, color: colors.background }
                : { background: colors.surface, color: colors.text_muted, border: `1px solid ${colors.text_muted}44` }
              }>
              {c}
            </button>
          )
        })}
      </div>
    )
  }

  if (style === 'underline-tab') {
    return (
      <div className="flex gap-6 mb-8 border-b" style={{ borderColor: `${colors.text}22` }}>
        {['All', ...categories].map((c) => {
          const isActive = c === 'All' ? active === null : active === c
          return (
            <button key={c} onClick={() => onSelect(c === 'All' ? null : c)}
              className="pb-3 text-sm font-medium transition-colors relative"
              style={{ color: isActive ? colors.text : colors.text_muted }}>
              {c}
              {isActive && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5"
                  style={{ background: colors.accent }} />
              )}
            </button>
          )
        })}
      </div>
    )
  }

  // minimal-text
  return (
    <div className="flex gap-5 mb-8">
      {['All', ...categories].map((c) => {
        const isActive = c === 'All' ? active === null : active === c
        return (
          <button key={c} onClick={() => onSelect(c === 'All' ? null : c)}
            className="text-xs uppercase tracking-widest font-mono transition-colors"
            style={{ color: isActive ? colors.text : colors.text_muted }}>
            {c}
          </button>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 4: Update `storefront-ui/components/storefront/ProductGrid.tsx` — add grid variant support**

The file currently renders a single grid layout. Update it to accept a `gridVariant` prop and render one of three layouts:

```tsx
// Add at top of file (after existing imports):
import type { BrandToken } from '@/types/schemas'

// Update the props interface to add:
interface ProductGridProps {
  products: PublicProduct[]
  logoMark: string
  slug: string
  emptyLabel: string
  emptySub: string
  gridVariant?: '2col-featured' | '3col-equal' | 'masonry'
  cardStyle?: 'borderless' | 'outlined' | 'elevated' | 'colored-bg'
  brandToken?: BrandToken | null
}
```

Inside the component, branch on `gridVariant`:

```tsx
// 2col-featured: first product spans 2 columns
if (gridVariant === '2col-featured' && products.length > 0) {
  const [featured, ...rest] = products
  return (
    <div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div className="md:col-span-2">
          <ProductCard product={featured} slug={slug} cardStyle={cardStyle} featured brandToken={brandToken} />
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {rest.map((p) => (
          <ProductCard key={p.id} product={p} slug={slug} cardStyle={cardStyle} brandToken={brandToken} />
        ))}
      </div>
    </div>
  )
}

// masonry: variable height via CSS columns
if (gridVariant === 'masonry') {
  return (
    <div className="columns-2 md:columns-3 gap-4 space-y-4">
      {products.map((p) => (
        <div key={p.id} className="break-inside-avoid">
          <ProductCard product={p} slug={slug} cardStyle={cardStyle} brandToken={brandToken} />
        </div>
      ))}
    </div>
  )
}

// 3col-equal (default)
return (
  <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
    {products.map((p) => (
      <ProductCard key={p.id} product={p} slug={slug} cardStyle={cardStyle} brandToken={brandToken} />
    ))}
  </div>
)
```

- [ ] **Step 5: Update `storefront-ui/components/storefront/ProductCard.tsx` — add card variant support**

Add `cardStyle`, `featured`, and `brandToken` props. The card's visual treatment changes by `cardStyle`:

- `borderless`: no border, generous padding, muted separator line
- `outlined`: thin border using `colors.text_muted` at 20% opacity
- `elevated`: box-shadow, background is `colors.surface`
- `colored-bg`: card background uses `colors.primary` at 8% opacity, accent price

Update `ProductCard` function signature:

```tsx
interface ProductCardProps {
  product: PublicProduct
  slug: string
  cardStyle?: 'borderless' | 'outlined' | 'elevated' | 'colored-bg'
  featured?: boolean
  brandToken?: BrandToken | null
}
```

Add card style variants to the card container:

```tsx
const cardStyles: Record<string, React.CSSProperties> = {
  borderless: {
    padding: featured ? '2rem' : '1rem',
    borderBottom: brandToken ? `1px solid ${brandToken.colors.text}18` : undefined,
  },
  outlined: {
    border: brandToken ? `1px solid ${brandToken.colors.text_muted}33` : '1px solid #333',
    borderRadius: brandToken?.layout.border_radius ?? '8px',
    padding: '1rem',
  },
  elevated: {
    background: brandToken?.colors.surface ?? 'var(--color-surface-2)',
    borderRadius: brandToken?.layout.border_radius ?? '8px',
    padding: '1rem',
    boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
  },
  'colored-bg': {
    background: brandToken ? `${brandToken.colors.primary}14` : 'transparent',
    borderRadius: brandToken?.layout.border_radius ?? '8px',
    padding: '1rem',
  },
}

const containerStyle = cardStyles[cardStyle ?? 'elevated'] ?? cardStyles.elevated
```

Wrap the existing card content in:
```tsx
<div style={containerStyle} className="group cursor-pointer transition-all duration-200 hover:opacity-90">
  {/* existing card content */}
</div>
```

- [ ] **Step 6: Update `storefront-ui/components/storefront/Storefront.tsx` — use BrandToken + StoreShell**

Replace the current implementation with a version that:
1. Checks if `store.brand_token` is present
2. If yes, wraps content in `StoreShell` and uses `HeroSection`, `CategoryNav`, updated `ProductGrid`
3. If no, falls back to existing implementation unchanged

```tsx
// Add imports at top:
import { StoreShell } from '@/components/store/StoreShell'
import { HeroSection } from '@/components/store/HeroSection'
import { CategoryNav } from '@/components/store/CategoryNav'

// In the render, after `if (status === 'ok' && store)`:
if (store.brand_token) {
  const bt = store.brand_token
  return (
    <StoreShell brandToken={bt}>
      {store.promos.length > 0 && (
        <div className="w-full text-center py-2.5 text-sm font-medium"
          style={{ background: bt.colors.accent, color: bt.colors.background }}>
          {store.promos[0].label}
        </div>
      )}
      <button onClick={() => openCart(true)} /* existing cart button */ />
      <Cart />
      <HeroSection
        brandToken={bt}
        storeName={store.store_name}
        tagline={store.tagline}
        logoMark={store.icons.logo_mark}
      />
      <div className="max-w-5xl mx-auto px-5 pb-16"
        style={{ paddingLeft: bt.layout.spacing === 'generous' ? '2rem' : undefined }}>
        <input type="search" value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="Search products…" className="w-full rounded-lg px-4 py-2.5 text-sm outline-none mb-6"
          style={{ background: `${bt.colors.text}0A`, color: bt.colors.text,
            border: `1px solid ${bt.colors.text}22` }} />
        <CategoryNav
          categories={store.categories}
          active={activeCategory}
          onSelect={setActiveCategory}
          brandToken={bt}
        />
        <ProductGrid
          products={filtered}
          logoMark={store.icons.logo_mark}
          slug={slug}
          emptyLabel={store.products.length === 0 ? 'Preparing the shelves' : 'Nothing matches'}
          emptySub={store.products.length === 0 ? 'New pieces are on their way.' : 'Try a different search.'}
          gridVariant={bt.layout.product_grid}
          cardStyle={bt.layout.card_style}
          brandToken={bt}
        />
      </div>
    </StoreShell>
  )
}
// else: existing render (unchanged fallback for stores without brand_token)
```

- [ ] **Step 7: Add behavior/agent/dashboard API methods to `storefront-ui/lib/api.ts`**

Append these methods to the `api` object:

```typescript
// Behavior
postBehaviorEvent: (slug: string, event: {
  event_type: string
  product_id?: string
  session_id: string
  timestamp?: number
}) => req<{ ok: boolean }>(`/api/behavior/event/${enc(slug)}`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(event),
}),

simulateActivity: (slug: string) =>
  req<{ ok: boolean; scenario: string; events: number }>(
    `/api/behavior/simulate/${enc(slug)}`,
    { method: 'POST' }
  ),

// Agent actions
getPendingActions: (slug: string) =>
  req<{ actions: AgentAction[] }>(`/api/agent/actions/${enc(slug)}/pending`),

approveAction: (actionId: string) =>
  req<{ action: AgentAction }>(`/api/agent/actions/${enc(actionId)}/approve`, {
    method: 'POST',
  }),

dismissAction: (actionId: string) =>
  req<{ action: AgentAction }>(`/api/agent/actions/${enc(actionId)}/dismiss`, {
    method: 'POST',
  }),

// Dashboard
getDashboard: (slug: string) =>
  req<{
    store_name: string
    total_gmv: number
    elevate_attributed_gmv: number
    elevate_fee: number
    actions: Array<{
      promo_id: string
      action_type: string
      title: string
      trigger: string
      estimated_gmv: number
      executed_at: number | null
      attributed_orders: number
      attributed_gmv: number
      fee: number
    }>
  }>(`/api/dashboard/${enc(slug)}`),
```

Add `import type { AgentAction } from '@/types/schemas'` to the top of `lib/api.ts`.

- [ ] **Step 8: Visual verification**

```bash
docker compose restart api
```

Open `http://localhost:3000/s/haree` and `http://localhost:3000/s/crest`.

Check:
- [ ] Each store has a visually distinct hero based on its `brand_token.layout.hero_type`
- [ ] Product grid matches `brand_token.layout.product_grid`
- [ ] Product cards match `brand_token.layout.card_style`
- [ ] Category nav matches `brand_token.layout.category_style`
- [ ] Both stores look completely different from each other

If `brand_token` is null (brand not regenerated yet): the old fallback renders. That's expected — fix by running the simulate curl from Task 2.

- [ ] **Step 9: Commit**

```bash
git add storefront-ui/components/store/ storefront-ui/components/storefront/ProductGrid.tsx storefront-ui/components/storefront/ProductCard.tsx storefront-ui/components/storefront/Storefront.tsx storefront-ui/lib/api.ts
git commit -m "[sprint-2] layout variants: StoreShell + 4 layout styles + CategoryNav"
```

---

## Task 5: Frontend — Merchant Terminal

**Files:**
- Create: `storefront-ui/app/merchant/[slug]/page.tsx`
- Create: `storefront-ui/components/merchant/MerchantTerminal.tsx`
- Create: `storefront-ui/components/merchant/ActionCard.tsx`
- Create: `storefront-ui/components/merchant/BehaviorPulse.tsx`
- Create: `storefront-ui/components/merchant/AttributionDashboard.tsx`

**Interfaces:**
- Consumes: `GET /api/agent/actions/{slug}/pending` from Task 3
- Consumes: `POST /api/agent/actions/{id}/approve` and `/dismiss` from Task 3
- Consumes: `POST /api/behavior/simulate/{slug}` from Task 3
- Consumes: `GET /api/dashboard/{slug}` from Task 3
- Consumes: WS `/ws/terminal/{merchant_id}` for live `agent_action` events

- [ ] **Step 1: Create `storefront-ui/app/merchant/[slug]/page.tsx`**

```tsx
import { MerchantTerminal } from '@/components/merchant/MerchantTerminal'

export default async function MerchantPage({
  params,
}: {
  params: Promise<{ slug: string }>
}) {
  const { slug } = await params
  return <MerchantTerminal slug={slug} />
}
```

- [ ] **Step 2: Create `storefront-ui/components/merchant/ActionCard.tsx`**

```tsx
'use client'

import { motion, AnimatePresence } from 'framer-motion'
import type { AgentAction } from '@/types/schemas'

interface ActionCardProps {
  action: AgentAction
  onApprove: (id: string) => void
  onDismiss: (id: string) => void
  isLoading?: boolean
}

const ACTION_TYPE_LABELS: Record<string, string> = {
  flash_sale: 'Flash Sale',
  layout_morph: 'Layout Shift',
  scarcity_price: 'Scarcity Pricing',
  recovery_offer: 'Recovery Offer',
  copy_rewrite: 'Copy Rewrite',
}

export function ActionCard({ action, onApprove, onDismiss, isLoading }: ActionCardProps) {
  const confidencePct = Math.round(action.estimated_confidence * 100)

  return (
    <motion.div
      initial={{ opacity: 0, y: 30, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -20, scale: 0.96 }}
      transition={{ duration: 0.45, ease: [0.4, 0, 0.2, 1] }}
      className="rounded-xl border p-5"
      style={{
        background: 'var(--color-surface-2)',
        borderColor: 'var(--color-border)',
      }}
    >
      {/* Trigger label */}
      <p className="text-xs font-mono text-muted mb-2 uppercase tracking-wide">
        {ACTION_TYPE_LABELS[action.action_type] ?? action.action_type}
      </p>

      {/* Trigger reason */}
      <p className="text-xs mb-3" style={{ color: 'var(--color-warning)' }}>
        ⚡ {action.trigger}
      </p>

      {/* Action title */}
      <h3 className="text-base font-semibold mb-1 leading-snug">
        {action.title}
      </h3>

      {/* Description */}
      <p className="text-sm text-muted mb-4">{action.description}</p>

      {/* Estimated impact */}
      <div className="flex items-center gap-3 mb-3">
        <span className="text-sm font-semibold" style={{ color: 'var(--color-accent)' }}>
          → +${action.estimated_gmv.toLocaleString()} estimated revenue
        </span>
      </div>

      {/* Confidence bar */}
      <div className="mb-3">
        <div className="flex justify-between text-xs text-muted mb-1">
          <span>AI confidence</span>
          <span>{confidencePct}%</span>
        </div>
        <div className="h-1 rounded-full" style={{ background: 'var(--color-border)' }}>
          <div
            className="h-1 rounded-full transition-all"
            style={{
              width: `${confidencePct}%`,
              background: 'var(--color-accent)',
            }}
          />
        </div>
      </div>

      {/* Brand check */}
      {action.brand_check && (
        <p className="text-xs text-muted mb-4">
          ✓ {action.brand_check}
        </p>
      )}

      {/* Actions */}
      <div className="flex gap-3">
        <button
          onClick={() => onApprove(action.id)}
          disabled={isLoading}
          className="flex-1 py-2.5 rounded-lg text-sm font-semibold transition-opacity disabled:opacity-50"
          style={{ background: 'var(--color-accent)', color: 'var(--color-bg)' }}
        >
          {isLoading ? 'Applying…' : 'Approve'}
        </button>
        <button
          onClick={() => onDismiss(action.id)}
          disabled={isLoading}
          className="px-4 py-2.5 rounded-lg text-sm transition-opacity disabled:opacity-50"
          style={{ border: '1px solid var(--color-border)', color: 'var(--color-text)' }}
        >
          Dismiss
        </button>
      </div>
    </motion.div>
  )
}
```

- [ ] **Step 3: Create `storefront-ui/components/merchant/BehaviorPulse.tsx`**

```tsx
'use client'

import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

interface PulseEvent {
  id: string
  text: string
  ts: number
}

interface BehaviorPulseProps {
  slug: string
  onSimulate: () => void
  isSimulating: boolean
}

export function BehaviorPulse({ slug, onSimulate, isSimulating }: BehaviorPulseProps) {
  const [events, setEvents] = useState<PulseEvent[]>([])

  // Add a synthetic event to the visual feed (called from parent when user simulates)
  const addEvent = (text: string) => {
    setEvents((prev) => [
      { id: Math.random().toString(36).slice(2), text, ts: Date.now() },
      ...prev.slice(0, 6),
    ])
  }

  // Expose addEvent via a ref-like approach — parent triggers via simulate
  useEffect(() => {
    if (!isSimulating) return
    const labels = [
      'view — product-1',
      'view — product-1',
      'add_to_cart — product-1',
      'abandon — product-1',
      'abandon — product-1',
      'abandon — product-1',
      'abandon — product-1 (threshold!)',
    ]
    labels.forEach((label, i) => {
      setTimeout(() => addEvent(label), i * 300)
    })
  }, [isSimulating])

  return (
    <div className="rounded-xl border p-4" style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold font-mono uppercase tracking-wide text-muted">
          Behavior Pulse
        </h3>
        <button
          onClick={onSimulate}
          disabled={isSimulating}
          className="text-xs px-3 py-1.5 rounded-lg font-mono disabled:opacity-50 transition-opacity"
          style={{ background: 'var(--color-accent)', color: 'var(--color-bg)' }}
        >
          {isSimulating ? 'Simulating…' : 'Simulate Customer Activity'}
        </button>
      </div>

      <div className="space-y-1.5 min-h-[140px]">
        <AnimatePresence initial={false}>
          {events.length === 0 ? (
            <p className="text-xs text-muted font-mono">Waiting for customer events…</p>
          ) : (
            events.map((ev) => (
              <motion.div
                key={ev.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="text-xs font-mono text-muted flex items-center gap-2"
              >
                <span className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                  style={{ background: ev.text.includes('abandon') ? 'var(--color-danger)' : 'var(--color-accent)' }} />
                {ev.text}
              </motion.div>
            ))
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Create `storefront-ui/components/merchant/AttributionDashboard.tsx`**

```tsx
'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

interface DashboardData {
  store_name: string
  total_gmv: number
  elevate_attributed_gmv: number
  elevate_fee: number
  actions: Array<{
    promo_id: string
    action_type: string
    title: string
    attributed_orders: number
    attributed_gmv: number
    fee: number
    executed_at: number | null
  }>
}

export function AttributionDashboard({ slug }: { slug: string }) {
  const [data, setData] = useState<DashboardData | null>(null)

  useEffect(() => {
    api.getDashboard(slug).then(setData).catch(() => null)
  }, [slug])

  if (!data) {
    return <p className="text-xs text-muted font-mono">Loading dashboard…</p>
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Total GMV" value={`$${data.total_gmv.toLocaleString()}`} />
        <Stat label="AI-Attributed" value={`$${data.elevate_attributed_gmv.toLocaleString()}`} accent />
        <Stat label="Elevate Fee (10%)" value={`$${data.elevate_fee.toLocaleString()}`} />
      </div>

      {data.actions.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-mono uppercase tracking-wide text-muted">Executed Actions</p>
          {data.actions.map((a) => (
            <div key={a.promo_id}
              className="rounded-lg p-3 flex items-center justify-between"
              style={{ background: 'var(--color-surface-2)', border: '1px solid var(--color-border)' }}>
              <div>
                <p className="text-sm font-medium">{a.title}</p>
                <p className="text-xs text-muted">{a.promo_id} · {a.attributed_orders} orders</p>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold" style={{ color: 'var(--color-accent)' }}>
                  ${a.attributed_gmv.toLocaleString()}
                </p>
                <p className="text-xs text-muted">fee ${a.fee.toLocaleString()}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {data.actions.length === 0 && (
        <p className="text-xs text-muted font-mono">
          No executed actions yet — approve an AI action to see attribution.
        </p>
      )}
    </div>
  )
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-lg p-3 text-center"
      style={{ background: 'var(--color-surface-2)', border: '1px solid var(--color-border)' }}>
      <p className="text-xs text-muted font-mono mb-1">{label}</p>
      <p className="text-lg font-bold" style={{ color: accent ? 'var(--color-accent)' : undefined }}>
        {value}
      </p>
    </div>
  )
}
```

- [ ] **Step 5: Create `storefront-ui/components/merchant/MerchantTerminal.tsx`**

```tsx
'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { AnimatePresence } from 'framer-motion'
import { api } from '@/lib/api'
import type { AgentAction } from '@/types/schemas'
import { ActionCard } from './ActionCard'
import { BehaviorPulse } from './BehaviorPulse'
import { AttributionDashboard } from './AttributionDashboard'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:9000'
const WS_BASE = API_BASE.replace(/^http/, 'ws')

type Tab = 'actions' | 'dashboard'

export function MerchantTerminal({ slug }: { slug: string }) {
  const [actions, setActions] = useState<AgentAction[]>([])
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const [isSimulating, setIsSimulating] = useState(false)
  const [wsStatus, setWsStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting')
  const [activeTab, setActiveTab] = useState<Tab>('actions')
  const [merchantId, setMerchantId] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  // Load merchant id from the store endpoint
  useEffect(() => {
    fetch(`${API_BASE}/api/store/${slug}`)
      .then((r) => r.json())
      .then((store) => {
        // We need merchant_id for WS — use slug as identifier (slug = merchant slug)
        // The terminal WS path uses merchant_id, not slug
        // Fetch it from the pending actions endpoint which tells us the merchant_id
        api.getPendingActions(slug).then((data) => {
          if (data.actions.length > 0) {
            setMerchantId(data.actions[0].merchant_id)
          }
        }).catch(() => null)
      })
      .catch(() => null)
  }, [slug])

  // Load pending actions on mount
  useEffect(() => {
    api.getPendingActions(slug)
      .then((data) => setActions(data.actions))
      .catch(() => null)
  }, [slug])

  // WebSocket for live agent_action events
  useEffect(() => {
    if (!merchantId) return

    const ws = new WebSocket(`${WS_BASE}/ws/terminal/${merchantId}`)
    wsRef.current = ws

    ws.onopen = () => setWsStatus('connected')
    ws.onclose = () => setWsStatus('disconnected')

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.event === 'agent_action' && msg.payload?.action) {
          setActions((prev) => {
            const exists = prev.find((a) => a.id === msg.payload.action.id)
            if (exists) return prev
            return [msg.payload.action, ...prev]
          })
        }
      } catch {
        // ignore parse errors
      }
    }

    return () => {
      ws.close()
    }
  }, [merchantId])

  const handleApprove = useCallback(async (id: string) => {
    setLoadingId(id)
    try {
      const { action } = await api.approveAction(id)
      setActions((prev) => prev.filter((a) => a.id !== id))
    } catch {
      // show nothing — the card stays
    } finally {
      setLoadingId(null)
    }
  }, [])

  const handleDismiss = useCallback(async (id: string) => {
    setLoadingId(id)
    try {
      await api.dismissAction(id)
      setActions((prev) => prev.filter((a) => a.id !== id))
    } finally {
      setLoadingId(null)
    }
  }, [])

  const handleSimulate = useCallback(async () => {
    setIsSimulating(true)
    try {
      await api.simulateActivity(slug)
    } catch {
      // ignore
    }
    setTimeout(() => setIsSimulating(false), 4000)
  }, [slug])

  return (
    <main className="min-h-screen" style={{ background: 'var(--color-bg)', color: 'var(--color-text)' }}>
      {/* Header */}
      <header className="border-b px-6 py-4 flex items-center justify-between"
        style={{ borderColor: 'var(--color-border)' }}>
        <div>
          <h1 className="text-lg font-semibold font-mono">{slug}</h1>
          <p className="text-xs text-muted font-mono">Merchant Terminal</p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`w-2 h-2 rounded-full ${wsStatus === 'connected' ? 'bg-green-400' : wsStatus === 'connecting' ? 'bg-yellow-400' : 'bg-red-400'}`} />
          <span className="text-xs font-mono text-muted">{wsStatus}</span>
          <a href={`/s/${slug}`} target="_blank" rel="noopener"
            className="text-xs font-mono px-3 py-1.5 rounded-lg"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-accent)' }}>
            View Store ↗
          </a>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">
        {/* Behavior Pulse */}
        <BehaviorPulse slug={slug} onSimulate={handleSimulate} isSimulating={isSimulating} />

        {/* Tabs */}
        <div className="flex gap-1 p-1 rounded-lg" style={{ background: 'var(--color-surface)' }}>
          {(['actions', 'dashboard'] as Tab[]).map((tab) => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              className="flex-1 py-2 text-sm font-mono rounded-md transition-colors capitalize"
              style={activeTab === tab
                ? { background: 'var(--color-surface-2)', color: 'var(--color-text)' }
                : { color: 'var(--color-text-muted)' }
              }>
              {tab === 'actions' ? `Actions ${actions.length > 0 ? `(${actions.length})` : ''}` : 'Attribution'}
            </button>
          ))}
        </div>

        {/* Actions Tab */}
        {activeTab === 'actions' && (
          <div>
            {actions.length === 0 ? (
              <div className="text-center py-16">
                <p className="text-muted font-mono text-sm mb-2">No pending actions</p>
                <p className="text-xs text-muted">Hit "Simulate Customer Activity" to trigger the AI decision cycle</p>
              </div>
            ) : (
              <div className="space-y-4">
                <AnimatePresence>
                  {actions.map((action) => (
                    <ActionCard
                      key={action.id}
                      action={action}
                      onApprove={handleApprove}
                      onDismiss={handleDismiss}
                      isLoading={loadingId === action.id}
                    />
                  ))}
                </AnimatePresence>
              </div>
            )}
          </div>
        )}

        {/* Dashboard Tab */}
        {activeTab === 'dashboard' && (
          <AttributionDashboard slug={slug} />
        )}
      </div>
    </main>
  )
}
```

- [ ] **Step 6: Verify the merchant terminal visually**

Open `http://localhost:3000/merchant/haree` in a browser.

Check:
- [ ] Page loads with "Merchant Terminal" header showing `haree`
- [ ] "Simulate Customer Activity" button is present
- [ ] Click simulate — behavior pulse shows events appearing
- [ ] After ~5 seconds, an action card surfaces under "Actions" tab
- [ ] Approve button dismisses the card with a Framer Motion exit
- [ ] Dashboard tab shows attribution data (may be $0 attributed if no orders yet)
- [ ] Store link navigates to `/s/haree`

- [ ] **Step 7: Test full demo loop end-to-end**

1. Navigate to `http://localhost:3000/s/haree` — store loads with brand-themed layout
2. Open `http://localhost:3000/merchant/haree` in a second tab
3. Click "Simulate Customer Activity"
4. Watch behavior pulse light up with abandon events
5. Action card surfaces in the Actions tab
6. Click "Approve"
7. Switch back to the storefront — it hot-reloads (promo banner appears or layout shifts)
8. Go to Dashboard tab — action shows in executed actions list

- [ ] **Step 8: Commit**

```bash
git add storefront-ui/app/merchant/ storefront-ui/components/merchant/
git commit -m "[sprint-2] merchant terminal: action cards + behavior pulse + attribution dashboard"
```

---

## Self-Review Checklist

**Spec coverage against docs/read.md:**
- [x] Store birth → BrandToken generation (Task 2) — ✓
- [x] 4 layout styles (editorial/bold-grid/minimal-dark/warm-craft) — Task 4 ✓
- [x] HeroSection 4 variants — Task 4 ✓
- [x] ProductGrid 3 variants — Task 4 ✓
- [x] ProductCard 4 variants — Task 4 ✓
- [x] CategoryNav 3 variants — Task 4 ✓
- [x] `POST /api/behavior/event` — Task 3 ✓
- [x] Anomaly detection (abandon surge, velocity spike) — Task 3 ✓
- [x] Qwen-Max decision cycle → AgentAction — Task 3 ✓
- [x] WS broadcast `agent_action` to terminal — Task 3 ✓
- [x] `POST /api/agent/actions/{id}/approve` — Task 3 ✓
- [x] `POST /api/agent/actions/{id}/dismiss` — Task 3 ✓
- [x] Flash sale execution (creates promo in SystemState) — Task 3 ✓
- [x] Behavior simulation button — Tasks 3 + 5 ✓
- [x] Merchant terminal UI — Task 5 ✓
- [x] ActionCard with confidence bar + brand check — Task 5 ✓
- [x] Attribution dashboard — Tasks 3 + 5 ✓
- [x] Seed products on store creation — Task 2 ✓
- [x] `GET /api/dashboard/{slug}` — Task 3 ✓

**What's NOT covered (post-hackathon / out of scope per docs/read.md §16):**
- Real payment processing — fake checkout exists, that's fine
- SSE store birth progress sequence (30-second animated sequence) — left for post-hackathon polish
- Layout morph Framer Motion storefront animation — the grid updates but doesn't animate between layouts

**Type consistency:**
- `AgentAction.merchant_id` — defined in Task 1, consumed in Task 3 and Task 5 ✓
- `BrandToken.layout.product_grid` → `gridVariant` prop — Task 1 defines, Task 4 consumes ✓
- `BrandToken.layout.card_style` → `cardStyle` prop — matches across Tasks 1 and 4 ✓
- `api.simulateActivity(slug)` → `POST /api/behavior/simulate/{slug}` — Task 3 router, Task 4 api.ts ✓
- `api.getPendingActions(slug)` → `GET /api/agent/actions/{slug}/pending` — Task 3, Task 4 ✓
