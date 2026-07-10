# Elevate — Your store, alive.

> AI-native commerce where Qwen is not a feature — it is the runtime.
> Upload a logo. Qwen builds the brand, runs the store, and learns from every decision.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
[![Built with Qwen](https://img.shields.io/badge/Built%20with-Qwen%20VL-Max%20%2B%20Qwen-Max-blue)](https://qwencloud.com)
[![Alibaba Cloud](https://img.shields.io/badge/Deployed%20on-Alibaba%20Cloud-orange)](https://alibabacloud.com)

---

## What makes Elevate different

Most AI commerce tools bolt a chatbot onto a Shopify clone. You ask questions,
get answers, then go do the work yourself.

Elevate is the opposite. Qwen builds the store from a single logo upload,
defines the brand rules, catalogs products from photos, watches customer
behavior in real-time, and surfaces decisions as option cards — not chat.
The merchant stays in control. Qwen does the work.

```
Logo → qwen-vl-max reads it
     → qwen-max generates brand (palette, voice, guard rules, layout)
     → Store shell appears live
     → Merchant drops product photos
     → qwen-vl-max identifies each product (Vision Fingerprinting deduplicates)
     → Store goes live
     → Customer session begins
     → Telemetry streams in real-time
     → Qwen detects patterns, proposes actions
     → Merchant taps Approve
     → Storefront morphs instantly
     → Qwen remembers every decision for next time
```

---

## The Two-Model Architecture

Two Qwen models. Each chosen for what it does best. No routing complexity.

| Task | Model | Why |
|------|-------|-----|
| Logo analysis + product identification | **qwen-vl-max** | Multimodal — reads images, identifies products from photos |
| Brand generation, descriptions, decisions | **qwen-max** | Best quality text, structured JSON output |

**Vision Fingerprinting** — before any image reaches Qwen, a perceptual hash
(aHash, 64-bit) runs client-side. Near-duplicate photos (same product, different
angle) collapse into one product with multiple images. This prevents wasting
tokens on identical products and keeps the catalog clean.

```
Drop 3 photos of the same slides
  → Fingerprint: all 3 match (hamming distance ≤ 5)
  → 1 uploaded to OSS, 2 duplicate URLs stored
  → Only 1 qwen-vl-max call (not 3)
  → 1 product created with 3 image URLs
  → "Created 1 product from 3 photos (2 duplicates merged)"
```

---

## What happens under the hood

### Onboarding (5 steps, < 30 seconds to live store)

1. **The Drop** — Merchant uploads a logo. Direct to OSS via presigned PUT
   (backend never touches file bytes — serverless-safe).

2. **The Incubation** — `qwen-vl-max` reads the logo, extracts geometry, palette,
   and mood. `qwen-max` generates the full brand package: color palette,
   typography, voice profile, layout variant, and **guard rules** — the brand's
   immune system, written in Qwen's own words.

3. **The Reveal** — Store shell renders with the generated brand. Colors,
   typography, SVG icons, all on-brand. If zero products: a beautiful "Preparing
   the shelves..." state that looks intentional, not broken.

4. **Product Vision** — Merchant drops product photos. Each is fingerprinted
   for dedup, uploaded to OSS, then `qwen-vl-max` identifies it: name, brand
   (only if visible in the photo), description in the store's voice, category,
   colorways, and a price anchored to the merchant's baseline (never web MSRP).
   Products land as **pending** — the merchant approves each one.

5. **The Launch** — Merchant publishes. SystemState initializes in Redis.
   Store goes live at `/s/{slug}`. After launch, approved products sync to
   the storefront instantly via WebSocket — no republish needed.

### The Three-Layer Interceptor

Every Qwen-proposed action passes through three validation layers before
reaching the merchant. This is the brand's immune system:

| Layer | Source | Behavior |
|-------|--------|----------|
| **Brand Guard** | Qwen-authored at brand gen time | Fires Qwen's own warning about color conflicts, voice mismatches. Does not block — flags. |
| **Business Constraints** | Merchant's margin/discount rules | Auto-clamps values with warning shown to merchant. Price below margin floor → clamped. |
| **System Safety** | Hardcoded | Price below cost, stock below zero, expired promo → **hard block**. No exceptions. |

The interceptor is immutable. Qwen cannot override it. This is what makes
the autopilot trustworthy — the merchant's rules are enforced regardless of
what Qwen proposes.

### Fault-Tolerant Storefront — Three Defense Layers

Qwen composes every store's layout (section order, variant choices, nav style,
card design). But Qwen can hallucinate, return malformed JSON, or time out.
A broken Qwen response must never produce a broken store.

Three defense layers guarantee a renderable, on-brand storefront regardless of
what Qwen returns:

| Layer | Name | Behavior |
|-------|------|----------|
| **A** | `coerce_variant` | Every section variant is validated against its type's allowed set. A hallucinated or cross-type variant (e.g. a grid variant on a hero) is coerced to the type's default. Near-miss strings are normalized and matched (`"masonry"` → `"masonry-4col"`). |
| **B** | `normalize_dsl` | Structural rules enforced on every save and regeneration: exactly one leading hero, at least one product grid, 2–5 sections total, no adjacent banners. Violations are repaired, not rejected. |
| **C** | `fallback_dsl_from_token` | When the Qwen call fails entirely (network, timeout, garbage), a deterministic DSL is generated from `hash(store_name + mood + industry)`. Stores stay distinct even with Qwen offline — no two brands fall back to the same template. |

**Graceful degradation on the frontend**: if the Zod schema validation fails on
the DSL received from the backend, `DSLRenderer` renders `FallbackStorefront` —
a fully functional, brand-themed storefront (search, categories, product grid,
cart) that uses the brand's palette and typography without relying on the DSL.
The store never shows a blank page or an error. The customer never sees a
broken state.

### CSS Sanitization Guardrail

Qwen generates scoped CSS for micro-interaction personality (hover transforms,
letter-spacing, transitions). This CSS is injected into the live storefront.
Unsanitized AI-generated CSS is a security and brand-integrity risk.

The sanitization pipeline:

1. **Property allowlist** — only 8 properties permitted: `transform`, `transition`,
   `letter-spacing`, `line-height`, `text-decoration`, `opacity`, `border-radius`,
   `box-shadow`. Everything else is stripped.
2. **Forbidden patterns** — `url()`, `@import`, `@keyframes`, `position: fixed`,
   `z-index` are rejected entirely. No external resource loading, no animation
   keyframes, no stacking context manipulation.
3. **Scope enforcement** — only rules scoped to `[data-store="{slug}"]` are kept.
   Unscoped selectors are dropped. One store's CSS can never affect another.

The result is injected client-side via `CustomCSSInjector` and cleaned up on
unmount. The sanitizer runs server-side before storage — by the time CSS reaches
the browser, it has already been validated.

### Real-Time Telemetry Pipeline

```
Customer browses → WebSocket event → FastAPI → Redis (velocity tracking)
                                                    ↓
                                          Anomaly detection
                                          (configurable threshold)
                                                    ↓
                                          qwen-max decision cycle
                                          (snapshot diff, not full state)
                                                    ↓
                                          Interceptor validates
                                                    ↓
                                          Option cards surface in terminal
                                                    ↓
                                          Merchant taps Approve
                                                    ↓
                                          Delta executed → WebSocket push
                                                    ↓
                                          Storefront morphs. Terminal updates.
                                          All connected clients sync instantly.
```

Anomaly detection is deterministic and configurable (`ANOMALY_THRESHOLD`,
`ANOMALY_WINDOW_SECONDS`) — if a product gets 5+ views in 30 seconds, Qwen
fires a decision cycle. Judges care about the autopilot reaction, not the
detection algorithm.

### Product Vision Pipeline

```
Merchant drops photos
  → Client-side: perceptual hash (aHash) groups near-duplicates
  → Upload all to OSS (duplicates get URLs too, just skip vision)
  → POST /products/vision-batch (only representatives)
  → asyncio.Semaphore(5): 5 parallel qwen-vl-max calls
  → Each returns: name, brand, description, category, colors, price, confidence
  → Products created as pending (is_active=False)
  → "Product Vision" section: per-product Approve / Discard / Approve All
  → Approved products flip is_active=True → sync to live storefront instantly
  → confident=False products flagged for CatalogReview
```

The `confident=False` flag is honesty by design. When Qwen can't clearly
identify a product, it says so — the merchant reviews it rather than a
silent wrong guess going live.

### Qwen Memory — The Autopilot Learns

Every merchant action Qwen observes is appended to `qwen_memory` on the
Merchant record. Two memory sources feed the learning loop:

1. **Merchant edits**: When a merchant changes a product's price, name, or
   category, a `MemoryEntry` records the old → new diff. Future vision calls
   and description generation include this memory — Qwen names, prices, and
   describes products the way the merchant has demonstrated they prefer.

2. **Outcome observation**: The `OutcomeObserver` runs after each agent action
   expires, counting attributed orders (joined by `promo_id`) and writing
   `MemoryEntry` records. The next decision cycle reads this memory first —
   Qwen proposes differently based on what actually worked.

Memory is stored in Postgres (durable) with Redis as a fast mirror. Capped
at 20 entries per merchant. Memory failures are caught and logged — they
never block a product edit, vision call, or decision cycle.

The merchant never talks to Qwen. Qwen just learns.

### Duplicate Detection + Catalog Audit

Two-layer catalog hygiene — automatic and Qwen-powered:

**Automatic deduplication** (`POST /products/deduplicate`):
- Groups products by primary image URL
- Qwen-generated duplicates → auto-merged (keep first, hard-delete extras)
- Merchant-written duplicates → flagged for human review
- Runs automatically on every products page load

**Qwen catalog audit** (`POST /products/catalog-audit`):
- One `qwen-max` call reviews up to 100 products
- Checks: pricing anomalies, missing categories, naming issues, description
  quality, duplicates
- Returns `catalog_score` (0-100), individual findings with severity, and
  specific actionable fixes

### Qwen Creative Extension

The store builder has a free-text creative input: "Tell Qwen what you want."
The merchant types their vision (e.g. "I want a bold hero with a full-bleed
image, then a story about craftsmanship") and `qwen-max` composes a new DSL
layout guided by that direction.

The output passes through the same 3-layer defense pipeline (coerce →
normalize → fallback). This is brand-guarded creative direction within the
existing DSL schema — never unconstrained codegen. The merchant's vision,
Qwen's execution, brand constraints enforced.

### Qwen Reasoning — Transparent Decisions

Every proposed action includes Qwen's step-by-step reasoning chain, visible
in a collapsible section on each option card:

> "12 views on slides in 30s → velocity spike → flash-sale at 15% because
> margin floor allows it → expected ~3 conversions from current session"

The reasoning is stored alongside the action and surfaced on demand — subtle
by default, deep when the merchant wants to understand why Qwen proposed
what it did. This makes the intelligence visible without overwhelming the
decision UI.

---

## Token Efficiency

Every Qwen call does maximum work. No throwaway calls.

- **Brand generation**: One `qwen-vl-max` + one `qwen-max` call. Cached forever.
- **Product descriptions**: All names batched into ONE `qwen-max` call. Never looped per product.
- **Product Vision**: One `qwen-vl-max` per unique product (fingerprinting eliminates duplicates). Memory-informed prompts at zero extra cost.
- **Decision cycles**: Send snapshot **diff** only, not full state. Includes reasoning chain.
- **Catalog audit**: ONE `qwen-max` call reviews up to 100 products.
- **Creative DSL**: ONE `qwen-max` call reusing existing prompt infrastructure.
- **Duplicate detection**: Zero Qwen calls — deterministic image URL comparison.
- **Memory injection**: Zero additional tokens when memory is empty.
- **Every output cached in Redis** before returning. Cache hit = zero tokens.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, TypeScript, Tailwind, Framer Motion, Zustand |
| Backend | FastAPI, Python 3.11, Pydantic v2, SQLAlchemy (async) |
| AI | **qwen-vl-max** (vision) + **qwen-max** (text/decisions) |
| Real-time | WebSocket (full-duplex, event-driven, zero polling) |
| Database | PostgreSQL (Alibaba Cloud RDS) — persistent source of truth |
| Cache | Redis (Alibaba Cloud Tair) — telemetry, sessions, state |
| Storage | Alibaba Cloud OSS — logos, product images (presigned PUT, never through backend) |
| Deploy | Alibaba Cloud Function Compute (serverless) + Docker Compose (local) |

---

## Architecture

See **[docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)** for the full system design
with diagrams.

```
elevate/
├── storefront-ui/          # Next.js 15 frontend
│   ├── app/
│   │   ├── (onboarding)/  # Setup, brand review, products (5-step flow)
│   │   ├── terminal/      # Merchant command center (decisions, attribution)
│   │   ├── storefront/    # Customer-facing store (DSL-rendered)
│   │   ├── scan/          # QR code campaign landing pages
│   │   └── builder/       # Point-and-click store builder
│   ├── components/
│   │   ├── onboarding/   # LogoUpload, ImageDropZone, CatalogReview
│   │   ├── terminal/     # OptionCard, DecisionFeed, StoreSnapshot
│   │   └── storefront/   # DSLRenderer, FallbackStorefront, CustomCSSInjector
│   │                      # ProductGrid, Cart, LayoutRouter
│   ├── lib/
│   │   ├── api.ts        # REST client (credentials: include)
│   │   ├── ws.ts         # WebSocket client
│   │   ├── store.ts      # Zustand global state
│   │   └── fingerprint.ts # Vision Fingerprinting (perceptual dedup)
│   └── types/schemas.ts  # Zod schemas (mirror Pydantic exactly)
│
└── analytics-brain/        # FastAPI backend
    ├── app/
    │   ├── core/          # Config, Redis, WebSocket manager, security
    │   ├── models/        # Pydantic schemas (source of truth) + DB models
    │   ├── routers/       # Products, onboarding, agent, merchant, behavior
    │   └── services/      # Qwen, brand, vision, interceptor, telemetry, delta
    │                      # layout_dsl.py (3 defense layers), css_gen.py (sanitizer)
    │                      # memory.py + outcome_observer.py (learning loop)
    └── scripts/           # Demo store builder, data migrations
```

---

## Getting Started

```bash
git clone https://github.com/Alpha-dev-001/elevate
cd elevate

# Backend
cd analytics-brain
cp .env.example .env      # Fill in Qwen API key, OSS credentials, DB URL
pip install -r requirements.txt
uvicorn app.main:app --reload --port 9000

# Frontend (separate terminal)
cd ../storefront-ui
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000/setup` to start onboarding.

### Environment Variables

```bash
# Qwen Cloud
QWEN_API_KEY=sk-...
QWEN_VL_MODEL=qwen-vl-max
QWEN_TEXT_MODEL=qwen-max

# Alibaba Cloud OSS (for logo + product image uploads)
OSS_REGION=cn-hongkong
OSS_ACCESS_KEY_ID=...
OSS_ACCESS_KEY_SECRET=...
OSS_BUCKET=elevate-assets

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/elevate

# Redis
REDIS_URL=redis://localhost:6379
```

---

## Hackathon

Built for the **Global AI Hackathon Series with Qwen Cloud** — **Track 4: Autopilot Agent**.

**Judging criteria alignment:**
- **Qwen Sophistication (30%)**: Two-model architecture, vision pipeline with
  fingerprinting, three-layer interceptor, token-efficient batching, memory
  system that learns from merchant edits AND outcome observation, LayoutDSL
  composition with three defense layers, creative extension for merchant-directed
  design, transparent reasoning chains on every proposed action.
- **Innovation (30%)**: Qwen IS the runtime (not a feature), brand guard rules
  authored by Qwen at creation time, Vision Fingerprinting for dedup, realtime
  telemetry → decision → approve → morph cycle, option cards not chat,
  fault-tolerant storefront, automatic catalog dedup, Qwen-powered catalog
  audit, merchant-directed creative generation within brand constraints.

---

## License

MIT — see [LICENSE](./LICENSE)
