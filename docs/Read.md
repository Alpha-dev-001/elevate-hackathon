# ELEVATE — Full Build Specification
## Qwen Cloud Global Hackathon · Track 4: Autopilot Agent
> This document is the single source of truth for Claude Code. Build exactly this.

---

## 0. What We Are Building

Elevate is an AI-native commerce platform where the store runs itself.

A merchant uploads a logo. Qwen reads it, builds a fully branded storefront — not just colors, but layout personality, typography, card style, hero type, spacing mood. Then Qwen watches customer behavior in real time, fires autonomous decisions (flash sale, layout morph, scarcity pricing), presents them as action cards to the merchant, and executes on approval. The store gets smarter the longer it runs.

**The demo loop judges need to see:**
1. Logo upload → store born in <60 seconds, visually distinct per brand
2. Simulated customer behavior spike → Qwen fires a decision → action card appears
3. Merchant approves → storefront hot-reloads live
4. Attribution dashboard shows: *"This action drove $X. Your fee: $Y."*

---

## 1. Tech Stack

```
Frontend:   Next.js 15 (App Router) · Zustand · Framer Motion · Tailwind CSS
Backend:    FastAPI · PostgreSQL · Redis · Alembic
AI:         Qwen-VL-Max (vision/logo analysis) · Qwen-Max (reasoning/decisions)
Infra:      Alibaba Cloud Function Compute · OSS (object storage) · Tair (Redis-compatible)
Realtime:   WebSocket (FastAPI native)
```

**Alibaba Cloud requirements (non-negotiable for submission):**
- Logo images stored in **Alibaba OSS** (not local disk)
- FastAPI deployed to **Alibaba Function Compute** via Docker
- At least one `oss2` SDK call visible in codebase
- Screen recording of Alibaba Cloud console showing running service

---

## 2. Data Models

### `Store`
```python
class Store(Base):
    __tablename__ = "stores"
    id            = Column(UUID, primary_key=True, default=uuid4)
    slug          = Column(String, unique=True, index=True)       # e.g. "haree"
    name          = Column(String)
    logo_url      = Column(String)                                 # OSS URL
    brand_tokens  = Column(JSONB)                                  # Full BrandToken object
    brand_rules   = Column(JSONB)                                  # BrandGuardRules
    created_at    = Column(DateTime, default=datetime.utcnow)
    tier          = Column(String, default="autopilot_basic")      # basic/pro/elite
```

### `BrandToken` (JSONB shape)
```json
{
  "colors": {
    "primary": "#6B1B2E",
    "accent": "#C9A84C",
    "background": "#F5F0E8",
    "surface": "#EDE6DC",
    "text": "#1A0A0E",
    "textMuted": "#8B6F6F"
  },
  "typography": {
    "displayFont": "Playfair Display",
    "bodyFont": "Cormorant Garamond",
    "scale": "editorial",
    "letterSpacing": "wide",
    "weight": "light"
  },
  "layout": {
    "style": "editorial",
    "heroType": "full-bleed",
    "productGrid": "2col-featured",
    "cardStyle": "borderless",
    "borderRadius": "2px",
    "spacing": "generous",
    "categoryStyle": "underline-tab"
  },
  "mood": "luxury-heritage",
  "industryHint": "fashion",
  "brandVoice": "refined, unhurried, quietly confident"
}
```

### Layout Styles (4 variants — these are the options Qwen picks from)
| Style | Triggers From | Hero | Grid | Cards | Feel |
|---|---|---|---|---|---|
| `editorial` | serif font, muted luxury palette | full-bleed image | 2-col featured first | borderless, generous padding | Vogue, Net-a-Porter |
| `bold-grid` | bright accent, sans-serif, playful logo | text-forward banner | tight 3-col equal | rounded, colored bg | Glossier, Fenty |
| `minimal-dark` | dark/monochrome logo, tech/premium | dark hero, sparse text | 3-col clean | sharp edges, white on dark | SSENSE, Rick Owens |
| `warm-craft` | earthy tones, organic logo elements | texture-bg hero | masonry-ish 3-col | soft radius, warm borders | Aesop, Graza |

### `Product`
```python
class Product(Base):
    __tablename__ = "products"
    id          = Column(UUID, primary_key=True, default=uuid4)
    store_id    = Column(UUID, ForeignKey("stores.id"))
    name        = Column(String)
    description = Column(Text)
    price       = Column(Numeric(10, 2))
    category    = Column(String)
    image_url   = Column(String)
    stock       = Column(Integer, default=100)
    is_featured = Column(Boolean, default=False)
```

### `AgentAction`
```python
class AgentAction(Base):
    __tablename__ = "agent_actions"
    id            = Column(UUID, primary_key=True, default=uuid4)
    store_id      = Column(UUID, ForeignKey("stores.id"))
    promo_id      = Column(String, unique=True)                    # e.g. "FLASH_20250627_A3F2"
    action_type   = Column(String)                                 # flash_sale | layout_morph | scarcity_price | recovery
    trigger       = Column(String)                                 # what caused this
    payload       = Column(JSONB)                                  # action details
    estimated_gmv = Column(Numeric(10, 2))
    status        = Column(String, default="pending")              # pending | approved | dismissed | executed
    created_at    = Column(DateTime, default=datetime.utcnow)
    approved_at   = Column(DateTime, nullable=True)
    executed_at   = Column(DateTime, nullable=True)
```

### `Order`
```python
class Order(Base):
    __tablename__ = "orders"
    id          = Column(UUID, primary_key=True, default=uuid4)
    store_id    = Column(UUID, ForeignKey("stores.id"))
    promo_id    = Column(String, nullable=True)                    # attribution link
    total       = Column(Numeric(10, 2))
    created_at  = Column(DateTime, default=datetime.utcnow)
```

### `BehaviorEvent` (Redis only — not persisted)
```json
{
  "store_id": "uuid",
  "event_type": "view|add_to_cart|abandon|purchase|search",
  "product_id": "uuid",
  "session_id": "string",
  "timestamp": "iso8601"
}
```

---

## 3. Backend — FastAPI Structure

```
backend/
├── main.py
├── core/
│   ├── config.py          # env vars, Alibaba OSS config
│   ├── database.py        # async SQLAlchemy engine
│   └── redis.py           # Redis/Tair connection
├── models/
│   ├── store.py
│   ├── product.py
│   ├── agent_action.py
│   └── order.py
├── routers/
│   ├── stores.py          # store CRUD + logo upload
│   ├── products.py        # product CRUD
│   ├── agent.py           # decision cycle + approve/dismiss
│   ├── behavior.py        # event ingestion
│   ├── orders.py          # order creation + attribution
│   └── dashboard.py       # attribution analytics
├── services/
│   ├── brand_engine.py    # Qwen-VL logo analysis → BrandToken
│   ├── decision_engine.py # Qwen-Max → AgentAction
│   ├── behavior_tracker.py# Redis event aggregation
│   ├── oss_service.py     # Alibaba OSS upload/fetch
│   └── store_generator.py # brand token → store config
└── websocket/
    └── manager.py         # WS connection manager
```

---

## 4. Core Services — Exact Implementation

### 4.1 Brand Engine (`services/brand_engine.py`)

```python
import httpx
import base64
from pathlib import Path

QWEN_VL_ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

BRAND_EXTRACTION_PROMPT = """
You are a world-class brand strategist and creative director.
Analyze this logo image and return ONLY a valid JSON object with this exact shape:

{
  "colors": {
    "primary": "<dominant brand color hex>",
    "accent": "<secondary/highlight color hex>",
    "background": "<ideal store background hex>",
    "surface": "<card/panel background hex>",
    "text": "<primary text color hex>",
    "textMuted": "<muted/secondary text hex>"
  },
  "typography": {
    "displayFont": "<Google Font name — choose a font that matches this brand's personality>",
    "bodyFont": "<Google Font name — for body copy>",
    "scale": "<compact|balanced|editorial>",
    "letterSpacing": "<tight|normal|wide>",
    "weight": "<light|regular|medium|bold>"
  },
  "layout": {
    "style": "<editorial|bold-grid|minimal-dark|warm-craft>",
    "heroType": "<full-bleed|text-forward|split|texture-bg>",
    "productGrid": "<2col-featured|3col-equal|masonry>",
    "cardStyle": "<borderless|outlined|elevated|colored-bg>",
    "borderRadius": "<2px|8px|16px|24px>",
    "spacing": "<compact|balanced|generous>",
    "categoryStyle": "<pill|underline-tab|minimal-text>"
  },
  "mood": "<one of: luxury-heritage|bold-playful|minimal-premium|organic-craft|tech-forward>",
  "industryHint": "<fashion|beauty|food|tech|home|sport|other>",
  "brandVoice": "<3-6 word description of tone: e.g. refined, unhurried, quietly confident>"
}

Be opinionated. Make choices that would make this store unmistakable. 
The layout.style must reflect the visual DNA of this logo, not a default choice.
Return ONLY the JSON. No explanation. No markdown.
"""

async def extract_brand_tokens(image_bytes: bytes, api_key: str) -> dict:
    b64 = base64.b64encode(image_bytes).decode()
    
    payload = {
        "model": "qwen-vl-max",
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"image": f"data:image/png;base64,{b64}"},
                        {"text": BRAND_EXTRACTION_PROMPT}
                    ]
                }
            ]
        }
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            QWEN_VL_ENDPOINT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json=payload
        )
        resp.raise_for_status()
        
    data = resp.json()
    raw = data["output"]["choices"][0]["message"]["content"][0]["text"]
    
    # Strip markdown fences if present
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    
    import json
    return json.loads(raw)


async def generate_brand_rules(brand_tokens: dict, store_name: str, api_key: str) -> dict:
    """Qwen-Max generates the store's own guardrails based on its brand identity."""
    
    prompt = f"""
You are the brand guardian for "{store_name}".
Based on this brand identity: {brand_tokens}

Generate BrandGuardRules as JSON:
{{
  "neverDiscount": <true if luxury brand, false otherwise>,
  "maxDiscountPercent": <0-50>,
  "toneRules": ["<rule 1>", "<rule 2>", "<rule 3>"],
  "colorRules": ["never use X color", ...],
  "competitorResponse": "<how to respond to competitor price drops: discount|bundle|value-reframe|ignore>",
  "scarcityAllowed": <true|false>,
  "flashSaleStyle": "<aggressive|subtle|none>"
}}

Return ONLY JSON.
"""
    
    resp = await call_qwen_max(prompt, api_key)
    return resp
```

### 4.2 Decision Engine (`services/decision_engine.py`)

```python
DECISION_PROMPT_TEMPLATE = """
You are the autonomous commerce brain for "{store_name}".
Brand mood: {mood} | Voice: {brand_voice}
BrandGuardRules: {brand_rules}

Current store state:
- Products: {products_summary}
- Last 10 minutes behavior: {behavior_summary}
- Current active promotions: {active_promos}

Anomaly detected: {anomaly_description}

Decide ONE action to take. Return ONLY this JSON:
{{
  "action_type": "<flash_sale|layout_morph|scarcity_price|recovery_offer|copy_rewrite>",
  "trigger": "<1-sentence: what caused this decision>",
  "title": "<merchant-facing action card title, max 8 words>",
  "description": "<merchant-facing description, max 20 words>",
  "estimated_gmv": <estimated revenue impact as number>,
  "estimated_confidence": <0.0-1.0>,
  "payload": {{
    // action_type specific:
    // flash_sale: {{ "product_ids": [...], "discount_percent": 15, "duration_minutes": 30 }}
    // layout_morph: {{ "new_grid": "2col-featured", "featured_product_ids": [...], "reason": "..." }}
    // scarcity_price: {{ "product_id": "...", "new_price": 0.00, "scarcity_message": "..." }}
    // recovery_offer: {{ "trigger": "cart_abandon", "offer": "free_shipping|5pct_off", "message": "..." }}
    // copy_rewrite: {{ "product_id": "...", "new_description": "..." }}
  }},
  "brand_check": "<confirm this action respects brand rules or flag a conflict>"
}}

The merchant must approve before this executes. Make it worth approving.
Return ONLY JSON.
"""

ANOMALY_DETECTORS = {
    "velocity_spike": lambda events: sum(1 for e in events if e["event_type"] == "view") > 20,
    "cart_abandon_surge": lambda events: sum(1 for e in events if e["event_type"] == "abandon") > 5,
    "low_stock_high_demand": lambda events, products: any(
        p["stock"] < 10 and 
        sum(1 for e in events if e.get("product_id") == p["id"]) > 3
        for p in products
    ),
}

async def run_decision_cycle(store_id: str, db, redis_client, api_key: str):
    """Called when an anomaly is detected. Returns AgentAction or None."""
    
    store = await db.get(Store, store_id)
    events = await get_recent_events(redis_client, store_id, minutes=10)
    products = await get_products(db, store_id)
    
    # Detect anomaly
    anomaly = detect_anomaly(events, products)
    if not anomaly:
        return None
    
    # Check no pending actions already
    pending = await get_pending_actions(db, store_id)
    if pending:
        return None
    
    # Build context
    prompt = DECISION_PROMPT_TEMPLATE.format(
        store_name=store.name,
        mood=store.brand_tokens["mood"],
        brand_voice=store.brand_tokens["brandVoice"],
        brand_rules=store.brand_rules,
        products_summary=summarize_products(products),
        behavior_summary=summarize_events(events),
        active_promos=[],
        anomaly_description=anomaly
    )
    
    result = await call_qwen_max(prompt, api_key)
    
    # Generate promo_id
    import secrets
    promo_id = f"ELEV_{store_id[:4].upper()}_{secrets.token_hex(3).upper()}"
    
    action = AgentAction(
        store_id=store_id,
        promo_id=promo_id,
        action_type=result["action_type"],
        trigger=result["trigger"],
        payload=result,
        estimated_gmv=result["estimated_gmv"],
        status="pending"
    )
    
    db.add(action)
    await db.commit()
    
    # Push to merchant terminal via WebSocket
    await ws_manager.broadcast_to_store(store_id, {
        "type": "agent_action",
        "action": action.to_dict()
    })
    
    return action
```

### 4.3 OSS Service (`services/oss_service.py`)
```python
import oss2
from core.config import settings

def get_oss_bucket():
    auth = oss2.Auth(settings.ALIBABA_ACCESS_KEY_ID, settings.ALIBABA_ACCESS_KEY_SECRET)
    return oss2.Bucket(auth, settings.OSS_ENDPOINT, settings.OSS_BUCKET_NAME)

async def upload_logo(file_bytes: bytes, filename: str) -> str:
    """Upload logo to Alibaba OSS, return public URL."""
    bucket = get_oss_bucket()
    key = f"logos/{filename}"
    bucket.put_object(key, file_bytes)
    return f"https://{settings.OSS_BUCKET_NAME}.{settings.OSS_ENDPOINT}/{key}"
```

---

## 5. API Endpoints

### Store Birth Flow
```
POST /api/stores/create
  Body: multipart/form-data { logo: File, name: string, slug: string }
  1. Upload logo → Alibaba OSS
  2. Call brand_engine.extract_brand_tokens(logo_bytes)
  3. Call brand_engine.generate_brand_rules(tokens, name)
  4. Generate 6 seed products via Qwen-Max (industry-appropriate)
  5. Persist store + products
  6. Return: { store, brand_tokens, products }

GET /api/stores/{slug}
  Returns: full store object with brand_tokens + products

GET /api/stores/{slug}/products
  Query: category?, featured?
  Returns: paginated products
```

### Agent Loop
```
POST /api/behavior/event
  Body: { store_id, event_type, product_id?, session_id }
  1. Push to Redis list: events:{store_id}
  2. Trim to last 500 events
  3. Check anomaly thresholds → trigger decision cycle if hit

GET /api/agent/actions/{store_id}/pending
  Returns: pending AgentAction[]

POST /api/agent/actions/{action_id}/approve
  1. Set status = "approved"
  2. Execute payload (apply discount, morph layout, etc.)
  3. Set status = "executed"
  4. Broadcast store update via WebSocket
  5. Return: { action, store_update }

POST /api/agent/actions/{action_id}/dismiss
  Sets status = "dismissed"
```

### Attribution Dashboard
```
GET /api/dashboard/{store_id}
  Returns:
  {
    "total_gmv": 4820.00,
    "elevate_attributed_gmv": 1240.00,
    "elevate_fee": 124.00,
    "actions": [
      {
        "promo_id": "ELEV_HARE_A3F2",
        "title": "Summer Flash on Linen Wrap Blouse",
        "executed_at": "...",
        "attributed_orders": 12,
        "attributed_gmv": 540.00,
        "fee": 54.00
      }
    ]
  }
```

### WebSocket
```
WS /ws/{store_id}
  Server → Client events:
    { type: "agent_action", action: AgentAction }       # new decision pending
    { type: "store_update", store_update: object }      # post-approval update
    { type: "behavior_pulse", metrics: object }         # live activity feed
```

---

## 6. Frontend — Next.js Structure

```
frontend/
├── app/
│   ├── layout.tsx
│   ├── page.tsx                    # Landing / logo upload
│   ├── merchant/
│   │   └── [slug]/
│   │       └── page.tsx            # Merchant terminal
│   └── s/
│       └── [slug]/
│           └── page.tsx            # Customer-facing storefront
├── components/
│   ├── store/
│   │   ├── StoreShell.tsx          # Themed wrapper — reads brand_tokens
│   │   ├── HeroSection.tsx         # 4 variants: full-bleed|text-forward|split|texture-bg
│   │   ├── ProductGrid.tsx         # 3 variants: 2col-featured|3col-equal|masonry
│   │   ├── ProductCard.tsx         # 4 variants: borderless|outlined|elevated|colored-bg
│   │   └── CategoryNav.tsx         # 3 variants: pill|underline-tab|minimal-text
│   ├── merchant/
│   │   ├── MerchantTerminal.tsx    # Right panel: live action cards + dashboard
│   │   ├── ActionCard.tsx          # The approve/dismiss card
│   │   ├── BehaviorPulse.tsx       # Live session count + event feed
│   │   └── AttributionDashboard.tsx
│   └── onboarding/
│       ├── LogoUpload.tsx
│       └── StoreBirth.tsx          # Progress animation (0→60s)
├── store/
│   └── elevate.ts                  # Zustand store
└── lib/
    ├── api.ts
    └── websocket.ts
```

---

## 7. Frontend — Component Contracts

### `StoreShell.tsx`
```tsx
// Reads brand_tokens and injects CSS variables into :root
// ALL child components pull from these variables — no hardcoded colors

interface StoreShellProps {
  brandTokens: BrandToken
  children: React.ReactNode
}

// Injects:
// --color-primary, --color-accent, --color-bg, --color-surface
// --color-text, --color-text-muted
// --font-display, --font-body
// --radius, --spacing-unit
// --letter-spacing

export function StoreShell({ brandTokens, children }: StoreShellProps) {
  const cssVars = buildCssVars(brandTokens) // maps token → CSS var
  return (
    <div style={cssVars} data-layout={brandTokens.layout.style}>
      {children}
    </div>
  )
}
```

### `HeroSection.tsx`
```tsx
// heroType drives which variant renders
type HeroType = "full-bleed" | "text-forward" | "split" | "texture-bg"

// full-bleed:    Large featured image, brand name overlay, tagline below
// text-forward:  Centered text hero, no image, strong typography moment  
// split:         Left text, right product image, 50/50
// texture-bg:    Subtle brand-colored texture bg, product silhouette
```

### `ProductGrid.tsx`
```tsx
// productGrid value from brand_tokens drives layout
// 2col-featured:  First product is large (spans 2 cols), rest are normal
// 3col-equal:     Uniform 3-column grid
// masonry:        Variable height cards, Pinterest-style

// Also accepts morphTarget prop — when layout_morph action executes,
// Framer Motion animates from current layout to new layout
```

### `ActionCard.tsx`
```tsx
// The most important component in the whole product
// Appears in merchant terminal when Qwen fires a decision

interface ActionCardProps {
  action: AgentAction
  onApprove: (id: string) => void
  onDismiss: (id: string) => void
}

// Visual hierarchy:
// 1. Trigger label (small, muted): "Cart abandon surge detected"
// 2. Action title (bold): "Run 15% flash sale on Linen Wrap Blouse"
// 3. Estimated impact (green): "→ +$420 estimated revenue"
// 4. Confidence bar: visual indicator 0-100%
// 5. Brand check (small): "✓ Respects brand guardrails"
// 6. Approve button (primary) | Dismiss (ghost)

// On approve: optimistic update + Framer Motion exit animation
// Then storefront hot-reloads via WebSocket update
```

---

## 8. Zustand Store (`store/elevate.ts`)

```typescript
interface ElevateStore {
  // Store data
  store: Store | null
  brandTokens: BrandToken | null
  products: Product[]
  
  // Live state
  pendingActions: AgentAction[]
  behaviorMetrics: BehaviorMetrics
  wsConnected: boolean
  
  // Layout state (can be morphed by agent)
  activeLayout: LayoutConfig
  
  // Actions
  setStore: (store: Store) => void
  setBrandTokens: (tokens: BrandToken) => void
  addPendingAction: (action: AgentAction) => void
  resolveAction: (id: string, resolution: "approved" | "dismissed") => void
  morphLayout: (newLayout: Partial<LayoutConfig>) => void
  updateBehaviorMetrics: (metrics: BehaviorMetrics) => void
}
```

---

## 9. Store Birth UX (0 → 60 seconds)

This is the **hero demo moment**. Do not rush it. Make it feel like something is being born.

```
[0s]   Merchant uploads logo
[1s]   "Reading your brand..." — logo pulses gently
[3s]   Color palette extracted → swatches appear one by one
[6s]   "Choosing your typography..." — font names appear
[9s]   "Building your store identity..." — layout style named
[12s]  Store shell fades in — themed, empty
[15s]  "Generating your products..." — cards appear with skeleton loading
[20s]  Products populate with AI-written descriptions
[25s]  BrandGuardRules generated → shown as bullet list
[30s]  "Your store is alive." — full storefront revealed

Progress bar runs throughout. Each step is a real API call completing.
```

**Implementation:** SSE (Server-Sent Events) stream from `POST /api/stores/create`
Each step emits: `{ step: string, progress: number, data?: any }`
Frontend renders each step as it arrives.

---

## 10. Behavior Simulation (For Demo)

Since we can't wait for real customers during a 3-minute demo video, build a simulation mode:

```typescript
// In merchant terminal: "Simulate Customer Activity" button
// Fires a sequence of events with realistic delays

const DEMO_SCENARIO = [
  { delay: 0,    event: "view",        product: "product_1" },
  { delay: 800,  event: "view",        product: "product_1" },
  { delay: 1200, event: "add_to_cart", product: "product_1" },
  { delay: 2000, event: "view",        product: "product_2" },
  { delay: 2400, event: "abandon",     product: "product_1" },
  { delay: 2800, event: "view",        product: "product_1" },
  { delay: 3200, event: "abandon",     product: "product_1" },
  // 5 abandons = anomaly threshold → Qwen fires decision
]

// This triggers the decision cycle naturally
// Qwen sees the abandons → fires a recovery offer or flash sale
// Action card appears in merchant terminal
// Merchant approves → storefront updates live
```

---

## 11. Attribution Logic

```python
# Order is attributed to a promo_id if:
# 1. Order contains promo_id field (set at checkout when active promo exists)
# 2. Order created within 72 hours of promo execution

# Dashboard query:
SELECT 
    aa.promo_id,
    aa.payload->>'title' as action_title,
    COUNT(o.id) as attributed_orders,
    SUM(o.total) as attributed_gmv,
    SUM(o.total) * 0.10 as elevate_fee
FROM agent_actions aa
LEFT JOIN orders o ON o.promo_id = aa.promo_id
WHERE aa.store_id = :store_id
  AND aa.status = 'executed'
GROUP BY aa.promo_id, aa.payload
```

---

## 12. Alibaba Cloud Deployment

### Function Compute setup
```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
```

```yaml
# .github/workflows/deploy-alibaba.yml
- name: Build and push to ACR
  uses: docker/build-push-action@v4
  with:
    push: true
    tags: registry.cn-hangzhou.aliyuncs.com/axrie/elevate-api:latest

- name: Deploy to Function Compute
  run: |
    s deploy --use-local
```

### Required env vars
```
ALIBABA_ACCESS_KEY_ID=
ALIBABA_ACCESS_KEY_SECRET=
OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
OSS_BUCKET_NAME=elevate-assets
QWEN_API_KEY=
DATABASE_URL=
REDIS_URL=
```

### Proof of deployment (for submission)
Record a 90-second screen capture showing:
1. Alibaba Cloud console → Function Compute → elevate-api → Running
2. OSS console → elevate-assets bucket → a logo file present
3. One curl request to the live Function Compute URL returning 200

---

## 13. Demo Video Script (3 minutes)

```
[0:00 - 0:20] The Problem
"Every e-commerce store looks the same. Every store runs the same way.
The merchant does all the work. Qwen changes that."

[0:20 - 1:10] Store Birth
- Upload Haree Fashion logo live
- Watch the 30-second store birth sequence
- Reveal: a luxury editorial store, unmistakably Haree
- Upload Ashfaak Sugar logo
- Reveal: a warm-craft artisanal store — completely different

[1:10 - 2:00] The Brain Working
- Switch to merchant terminal
- Hit "Simulate customer activity"
- Watch the behavior pulse light up
- Action card appears: "Run flash sale → +$420 estimated"
- Hit Approve
- Camera cuts to storefront: live update, Framer Motion transition

[2:00 - 2:40] Attribution
- Open dashboard
- "That flash sale drove $1,080 in orders. Elevate's fee: $108."
- Show the promo_id trail

[2:40 - 3:00] The Vision
"This is Elevate. The store that runs itself.
Built on Qwen Cloud. Deployed on Alibaba Function Compute.
Track 4: Autopilot Agent."
```

---

## 14. Day-by-Day Build Plan

### Days 1–2: Foundation
- [ ] FastAPI project scaffold + all models + Alembic migrations
- [ ] Alibaba OSS integration working (`oss_service.py`)
- [ ] `POST /api/stores/create` → logo upload → OSS URL returned
- [ ] Qwen-VL-Max brand extraction working, returning valid BrandToken JSON
- [ ] Database seeded with 2 test stores (Haree Fashion + Ashfaak Sugar)

### Days 3–4: Store Rendering
- [ ] Next.js `StoreShell` with CSS variable injection
- [ ] All 4 `HeroSection` variants built
- [ ] All 3 `ProductGrid` variants built
- [ ] All 4 `ProductCard` variants built
- [ ] Store at `/s/haree` looks unmistakably different from `/s/crest`

### Days 5–6: The Brain
- [ ] Redis behavior event ingestion working
- [ ] Anomaly detection logic (velocity spike + cart abandon)
- [ ] `decision_engine.py` calling Qwen-Max → valid AgentAction JSON
- [ ] WebSocket manager wired up
- [ ] Pending action persisted + broadcast via WS

### Days 7–8: Merchant Terminal
- [ ] `MerchantTerminal` component with WS connection
- [ ] `ActionCard` renders pending action
- [ ] Approve flow: FastAPI executes payload → broadcasts store update
- [ ] Dismiss flow
- [ ] `BehaviorPulse` shows live session count

### Days 9–10: Demo Loop Polish
- [ ] Behavior simulation button working end-to-end
- [ ] Full demo loop: logo → store → simulate → action card → approve → update
- [ ] `StoreBirth` SSE progress sequence animated
- [ ] Framer Motion layout morph transition
- [ ] Attribution dashboard with realistic seeded numbers

### Days 11–12: Alibaba + Submission
- [ ] FastAPI deployed to Alibaba Function Compute
- [ ] OSS bucket live with real logo uploads
- [ ] Architecture diagram drawn (use Excalidraw or Figma)
- [ ] Record proof-of-deployment video
- [ ] Record 3-minute demo video

### Days 13–14: Buffer
- [ ] Fix everything that broke
- [ ] Polish the store birth animation
- [ ] Write Devpost submission text
- [ ] Submit

---

## 15. What Judges Will See and Score

| Criterion | Weight | What Wins It |
|---|---|---|
| Technical Depth | 30% | Qwen-VL + Qwen-Max both used meaningfully, OSS integration, WebSocket, decision cycle logic |
| Innovation & AI Creativity | 30% | Brand-driven layout variance (not just CSS vars), the autonomous decision→approve loop |
| Problem Value & Impact | 25% | Real merchant pain, rev share model, productization story |
| Presentation | 15% | Architecture diagram, clean demo video, Devpost write-up |

**Your strongest card:** No other Track 4 submission will have a storefront that visually transforms based on brand DNA. That's the moment that wins.

---

## 16. What NOT to Build (Scope Cuts)

- ❌ Real payment processing (fake checkout is fine)
- ❌ Transit Tree / logistics (mention in pitch as roadmap)
- ❌ Multi-merchant auth (hardcode 2-3 demo stores)
- ❌ Mobile app
- ❌ Email sequences
- ❌ Real inventory management
- ❌ Competitor price monitoring

---

*Elevate. The store that runs itself.*  
*Axrie Holdings Inc. — Qwen Cloud Global Hackathon 2026 — Track 4: Autopilot Agent*