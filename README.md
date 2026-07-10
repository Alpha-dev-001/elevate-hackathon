# Elevate — Your store, alive.

> AI-native commerce where Qwen is not a feature — it is the runtime.
> Upload a logo. Qwen builds the brand, runs the store, and learns from every decision.

[License: MIT](./LICENSE)
[Built with Qwen](https://qwencloud.com)
[Alibaba Cloud](https://alibabacloud.com)

---

## TL;DR — Three things judges should know

1. **Qwen authors its own constraints.** At brand generation time, Qwen writes the
   guard rules that govern its future behavior — color conflicts, layout coherence,
   voice consistency. These rules are enforced by deterministic Python (Pydantic +
   Zod + 3-layer interceptor), not by prompting. The AI literally cannot violate
   the brand it created. This is not prompt engineering — it is schema-enforced
   self-governance.

2. **The store runs itself in real-time.** Customer browser events (click, hover,
   cart_add) flow through WebSocket → Redis velocity tracking → anomaly detection
   → qwen-max decision cycle → option card in the merchant terminal → approve →
   storefront morphs. The whole cycle is under 2 seconds perceived latency.
   Qwen learns from every approval AND every rejection — the next decision cycle
   reads outcome memory first.

3. **A broken AI response cannot produce a broken store.** Three defense layers
   guarantee a renderable, on-brand storefront regardless of what Qwen returns:
   variant coercion, structural normalization, and deterministic fallback. If the
   Qwen call fails entirely, a brand-seeded hash generates a distinct layout.
   The customer never sees a blank page.

---

## Contents

- [What makes Elevate different](#what-makes-elevate-different)
- [What Elevate is NOT](#what-elevate-is-not)
- [The Two-Model Architecture](#the-two-model-architecture)
- [What happens under the hood](#what-happens-under-the-hood)
  - [Onboarding](#onboarding-5-steps--30-seconds-to-live-store)
  - [The Three-Layer Interceptor](#the-three-layer-interceptor)
  - [Validation Architecture](#validation-architecture--defense-in-depth)
  - [Fault-Tolerant Storefront](#fault-tolerant-storefront--three-defense-layers)
  - [CSS Sanitization](#css-sanitization-guardrail)
  - [Real-Time Telemetry Pipeline](#real-time-telemetry-pipeline)
  - [Product Vision Pipeline](#product-vision-pipeline)
  - [Qwen Memory](#qwen-memory--the-autopilot-learns)
  - [Duplicate Detection + Catalog Audit](#duplicate-detection--catalog-audit)
  - [Creative Extension](#qwen-creative-extension)
  - [Qwen Reasoning](#qwen-reasoning--transparent-decisions)
  - [Per-Product Targeting + Signal Freshness](#per-product-targeting--signal-freshness)
- [Token Efficiency](#token-efficiency)
- [Testing (44 files)](#testing)
- [Stack](#stack)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Blog Post](#blog-post)

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

## What Elevate is NOT

To prevent common misreads — especially relevant for hackathon evaluators:

- **No video processing.** Customer behavior = discrete WebSocket DOM events
(`view`, `hover`, `cart_add`, `purchase`, `abandon`) — not video frames,
not camera feeds, not sensor data.
- **No physical stores.** Elevate is a pure online commerce platform.
Everything happens in the browser — merchant terminal and customer storefront.
- **No cameras or hardware integration.** Entirely browser-based, both for
the merchant (terminal) and the customer (storefront).
- **"Vision" = static image analysis.** The Product Vision pipeline uses
`qwen-vl-max` to analyze uploaded product photos — still images, not live
video streams. One image in, structured product data out.

---

## The Two-Model Architecture

Two Qwen models. Each chosen for what it does best. No routing complexity.


| Task                                      | Model           | Why                                                        |
| ----------------------------------------- | --------------- | ---------------------------------------------------------- |
| Logo analysis + product identification    | **qwen-vl-max** | Multimodal — reads images, identifies products from photos |
| Brand generation, descriptions, decisions | **qwen-max**    | Best quality text, structured JSON output                  |


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

**Technical implementation:** Both models are called via OpenAI-compatible chat
completions with `response_format: {type: "json_object"}` for structured output.
Responses are parsed server-side by `_extract_json()` (handles Qwen wrapping
JSON in markdown code fences) then validated through Pydantic models — malformed
output triggers one retry before falling back to deterministic defaults. Vision
Fingerprinting uses the `image-hash` library (aHash, 8×8 = 64-bit) computed in
the browser via `fingerprint.ts` — O(1) per image, O(n) per batch comparison.
Hamming distance ≤ 5 = near-duplicate. Hash computation is ~2ms per image.

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

**Technical implementation:** The STS upload flow (`POST /api/upload/token`)
generates temporary OSS credentials (15-min expiry) — the frontend uploads
binary directly to OSS, never through the backend (serverless functions must
not handle file bytes). Brand generation chains `_run_vl()` (qwen-vl-max,
image → `LogoAnalysis`) then `generate_brand()` (qwen-max → `GeneratedBrand` +
`BrandGuardRules`) in sequence, both server-side. Results are cached in Redis
keyed by `logo_url` — subsequent loads are O(1) cache hits. StoreBirth streams
each step as SSE events (`analyzing_geometry`, `extracting_palette`,
`generating_brand`, `composing_layout`) so the frontend shows a fluid loading
state. Target: < 5 seconds total. `generate_layout_dsl()` runs through the
3-layer defense pipeline (coerce → normalize → fallback) before the DSL is
persisted to `brand_tokens.layout_dsl` (JSONB in Postgres).

### The Three-Layer Interceptor

Every Qwen-proposed action passes through three validation layers before
reaching the merchant. This is the brand's immune system:


| Layer                    | Source                           | Behavior                                                                                  |
| ------------------------ | -------------------------------- | ----------------------------------------------------------------------------------------- |
| **Brand Guard**          | Qwen-authored at brand gen time  | Fires Qwen's own warning about color conflicts, voice mismatches. Does not block — flags. |
| **Business Constraints** | Merchant's margin/discount rules | Auto-clamps values with warning shown to merchant. Price below margin floor → clamped.    |
| **System Safety**        | Hardcoded                        | Price below cost, stock below zero, expired promo → **hard block**. No exceptions.        |


**Technical implementation:** The interceptor is pure deterministic Python —
zero LLM involvement. `validate_action()` in `interceptor.py` runs all three
layers in sequence. `enforce_price()` computes
`min_price = cost_price * (1 + margin_floor)` and clamps the proposed price
if it falls below. `enforce_discount()` checks the proposed discount against
`max_discount_pct` and `promo.expires_at`. Layer 1 matches the action's target
field against `BrandGuardRules.rules` — if a rule fires, the warning message
is Qwen's own pre-authored text (generated at brand creation, stored in
Postgres, surfaced instantly with zero latency). `validate_action()` returns
`ValidationResult(passed=bool, clamped: dict | None, blocked: list[Violation])`.
No retry logic — a blocked action is returned to the client as HTTP 409.

The interceptor is immutable. Qwen cannot override it. This is what makes
the autopilot trustworthy — the merchant's rules are enforced regardless of
what Qwen proposes.

### Validation Architecture — Defense in Depth

Every Qwen output is validated server-side AND client-side before rendering.
No LLM output reaches the DOM unvalidated.

```
Qwen output → Pydantic model validation (server) → Redis cache → API response
                                                        ↓
API response → Zod schema safeParse (client) → render or FallbackStorefront
                                                        ↓
Every action → coerce_variant() → normalize_dsl() → interceptor (3 layers)
                                                        ↓
CSS output → sanitize_css() → property allowlist + forbidden regex + scope lock
```

**Server-side**: every Qwen response is parsed through Pydantic models
(`GeneratedBrand`, `LayoutDSL`, `ProductVision`, `AgentAction`). If Qwen
hallucinated a field or returned malformed JSON, the Pydantic model catches it
before the data is stored or returned. `_extract_json()` in `brand.py` handles
the common case of Qwen wrapping JSON in markdown code fences.

**Client-side**: Zod schemas in `types/schemas.ts` mirror every Pydantic model
exactly. `LayoutDSLSchema.safeParse()` is called in `DSLRenderer` before
rendering — if validation fails, `FallbackStorefront` renders instead. The
WebSocket client uses `BrandReadyPayloadSchema.safeParse()` on every incoming
event payload.

**The interceptor's Layers 2 and 3 are deterministic Python.** No LLM
involvement. No prompt engineering. `enforce_price()` checks
`price >= cost_price * (1 + margin_floor)` — hard math, not vibes.
`validate_action()` returns `ValidationResult(passed=True|False)` with
specific violations. Layer 3 blocks (`stock < 0`, `price < cost`,
`expired promo`) return 409 to the client with no override path.

**CSS sanitization** (`sanitize_css()`): property allowlist (8 safe properties),
forbidden pattern rejection (`url()`, `@import`, `@keyframes`, `position: fixed`,
`z-index`), scope enforcement (`[data-store="{slug}"]` only). The sanitizer
runs server-side before storage — by the time CSS reaches the browser, it has
already been validated. `CustomCSSInjector` on the frontend injects pre-validated
CSS as a scoped `<style>` tag and cleans up on unmount.

### Fault-Tolerant Storefront — Three Defense Layers

Qwen composes every store's layout (section order, variant choices, nav style,
card design). But Qwen can hallucinate, return malformed JSON, or time out.
A broken Qwen response must never produce a broken store.

Three defense layers guarantee a renderable, on-brand storefront regardless of
what Qwen returns:


| Layer | Name                      | Behavior                                                                                                                                                                                                                                                 |
| ----- | ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A** | `coerce_variant`          | Every section variant is validated against its type's allowed set. A hallucinated or cross-type variant (e.g. a grid variant on a hero) is coerced to the type's default. Near-miss strings are normalized and matched (`"masonry"` → `"masonry-4col"`). |
| **B** | `normalize_dsl`           | Structural rules enforced on every save and regeneration: exactly one leading hero, at least one product grid, 2–5 sections total, no adjacent banners. Violations are repaired, not rejected.                                                           |
| **C** | `fallback_dsl_from_token` | When the Qwen call fails entirely (network, timeout, garbage), a deterministic DSL is generated from `hash(store_name + mood + industry)`. Stores stay distinct even with Qwen offline — no two brands fall back to the same template.                   |


**Graceful degradation on the frontend**: if the Zod schema validation fails on
the DSL received from the backend, `DSLRenderer` renders `FallbackStorefront` —
a fully functional, brand-themed storefront (search, categories, product grid,
cart) that uses the brand's palette and typography without relying on the DSL.
The store never shows a blank page or an error. The customer never sees a
broken state.

**Technical implementation:** `coerce_variant()` (defense A) uses a lookup
table `VALID_VARIANTS` keyed by `SectionType` enum — near-miss strings are
normalized via `_norm()` (lowercase + strip non-alphanumeric) and matched
against the allowed set; cross-type values are never honored. `normalize_dsl()`
(defense B) is a pure function: ensures exactly one leading hero
(`sections[0].type == "hero"`), at least one product grid, 2–5 sections total
(truncates excess, pads shortage), and no adjacent banners. All violations are
repaired in-place, not rejected — the DSL is always valid after normalization.
`fallback_dsl_from_token()` (defense C) uses `_seed() = hash(store_name + mood

- industry)`to deterministically pick from variant pools — same brand always produces the same fallback layout, even with Qwen completely offline. On the frontend,`DSLRenderer`calls`LayoutDSLSchema.safeParse(candidate)`— on failure, it renders`FallbackStorefront` which uses the brand's palette and
typography to render a fully functional store (search, categories, product grid,
cart) without depending on the DSL structure at all.

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

**Technical implementation:** `sanitize_css(css, slug)` in `css_gen.py` runs
three regex-based passes: (1) property allowlist — strips any declaration not
using one of 8 safe properties (`transform`, `transition`, `letter-spacing`,
`line-height`, `text-decoration`, `opacity`, `border-radius`, `box-shadow`),
(2) forbidden pattern rejection — removes rules containing `url()`, `@import`,
`@keyframes`, `position: fixed`, `z-index` entirely, (3) scope enforcement —
keeps only rules scoped to `[data-store="{slug}"]`, drops unscoped selectors.
The function is O(n) on CSS length. `generate_custom_css()` calls qwen-max with
a constrained prompt that lists the allowed properties upfront, reducing the
chance of forbidden output. Even when Qwen obeys, the sanitizer runs as a
defense-in-depth pass — prompt compliance is never trusted.

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

**Technical implementation:** Events are discrete browser interactions
(`view`, `hover`, `cart_add`, `purchase`, `abandon`) sent as JSON frames over
WebSocket — not video, not streams. `push_event()` in `behavior_tracker.py`
writes to a Redis sorted set (`ZADD velocity:{merchant_id}:{product_id} timestamp event_id`) — O(log n) per insertion. `count_views_in_window()` uses
`ZRANGEBYSCORE` to count events in the configured time window. When the
threshold is exceeded, `run_decision_cycle()` in `decision_engine.py` uses
**Qwen's native tool-calling API** — 5 tools defined in `tools.py` (one per
action type: `propose_flash_sale`, `propose_scarcity_price`, `propose_layout_morph`,
`propose_recovery_offer`, `propose_copy_rewrite`). Qwen selects which tool to
call and fills typed parameters — no JSON output parsing needed. Tool arguments
become the execution payload directly. Reasoning comes from Qwen's message
content alongside the tool call. Memory context and business constraints are
injected into the prompt.

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

**Human correction workflow** — when Qwen misreads a product (wrong name, bad
price, wrong category), the merchant fixes it inline without leaving the page:

1. **Pending products** land in the CatalogReview section with image, name,
   price, category, and description — all editable inline.
2. **`confident=False` products** get a visible "needs verification" badge so
   the merchant's eye goes straight to uncertain guesses.
3. **Inline editors** — every field (name, price, category, description) is
   editable in-place. The merchant corrects the value and taps Approve.
4. **Every correction is recorded** — the PATCH writes a `MemoryEntry` with
   the old → new diff. Future vision calls read this memory, so Qwen stops
   making the same mistake for this merchant.
5. **Discard** — if the product is unsalvageable, one tap hard-deletes it
   from the database. No orphaned pending records.

The workflow is: drop photos → scan pending list → fix what Qwen got wrong
inline → approve what's right → Qwen learns from every correction. No separate
admin panel, no context switch, no batch re-upload.

**Technical implementation:** `analyze_product_image()` in `vision.py` calls
`qwen-vl-max` with a structured prompt that requests JSON output: product name,
brand (only if visible), description in the store's voice, category, colorways,
price, and confidence flag. `asyncio.Semaphore(5)` caps parallel calls to
prevent rate-limiting. Each response is validated through Pydantic's
`ProductVision` model — malformed JSON triggers one retry. Perceptual
hashing uses aHash (8×8 = 64-bit) computed client-side in `fingerprint.ts` —
hamming distance ≤ 5 = near-duplicate, computed in ~2ms per image. Prices are
anchored to the merchant's baseline via `margin_floor_price()` — never web MSRP.
Memory context (`build_memory_context()`) is injected into the vision prompt at
zero extra token cost when entries exist, so Qwen names and describes products
the way the merchant has demonstrated they prefer.

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

**Technical implementation:** `write_memory()` in `memory.py` inserts into
`merchants.qwen_memory` (JSONB column via SQLAlchemy) and mirrors to Redis key
`merchant_memory:{id}` — both in one transaction. `build_memory_context()`
formats the last 5 entries as plain-text prompt injection: "The merchant
preferred X over Y" / "A flash-sale at 15% drove 3 orders."
`OutcomeObserver` (`observe_outcome()`) is scheduled via
`schedule_observation()` — a background task that fires when the promo expires,
counts orders joined by `promo_id`, and writes an outcome `MemoryEntry` with
`summarize_outcome()` (e.g., "flash_sale at 15% → 3 orders, $127 revenue").i Memory is capped at 20 entries per merchant (FIFO eviction). If Redis is down, `get_memory()` falls back to Postgres — O(n) query with `LIMIT 20`. Memory
failures are caught in a try/except and logged — they never block the calling
operation.

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

**Technical implementation:** Automatic dedup (`POST /products/deduplicate`) is
zero-LLM — it groups products by primary image URL and checks the `created_by`
field: Qwen-generated duplicates are auto-merged (hard-delete extras, keep
first), merchant-written duplicates are flagged for human review. Runs on every
products page load — O(n) on product count. Catalog audit (`review_catalog()`
in `catalog.py`) sends all products (up to 100) to `qwen-max` in one batched
call, requesting `CatalogAuditReport` with `catalog_score`, `findings[]`
(severity: critical/warning/info), and specific fixes. Results are cached in
Redis (`_cache()`) keyed by merchant ID — subsequent audit reads hit cache until
the catalog changes. `confident=False` products from the vision pipeline are
automatically included in audit scope.

### Qwen Creative Extension

The store builder has a free-text creative input: "Tell Qwen what you want."
The merchant types their vision (e.g. "I want a bold hero with a full-bleed
image, then a story about craftsmanship") and `qwen-max` composes a new DSL
layout guided by that direction.

The output passes through the same 3-layer defense pipeline (coerce →
normalize → fallback). This is brand-guarded creative direction within the
existing DSL schema — never unconstrained codegen. The merchant's vision,
Qwen's execution, brand constraints enforced.

**Technical implementation:** The creative input is passed to `qwen-max` as a
natural-language directive appended to the existing `generate_layout_dsl()`
prompt — no separate prompt template needed. The response is a `LayoutDSL`
JSON object that goes through the identical `coerce_variant()` → `normalize_dsl()`
→ `fallback_dsl_from_token()` pipeline as the initial brand generation. The DSL
schema (`VALID_VARIANTS`, section types, global config) constrains what Qwen
can output — even unconstrained creative direction stays within the renderable
section/card/nav registries. The result is persisted to `brand_tokens.layout_dsl`
(JSONB) and pushed to the storefront via WebSocket `state_updated` event.

### Qwen Reasoning — Transparent Decisions

Every proposed action includes Qwen's step-by-step reasoning chain, visible
in a collapsible section on each option card:

> "12 views on slides in 30s → velocity spike → flash-sale at 15% because
> margin floor allows it → expected ~3 conversions from current session"

The reasoning is stored alongside the action and surfaced on demand — subtle
by default, deep when the merchant wants to understand why Qwen proposed
what it did. This makes the intelligence visible without overwhelming the
decision UI.

**Technical implementation:** When Qwen calls a tool via the decision cycle's
tool-calling API, the response includes both `message.content` (free-text
reasoning) and `message.tool_calls` (structured parameters). The reasoning is
extracted from `message.content` — Qwen's natural-language explanation of why
it chose this tool and these parameters (e.g., "12 views on slides in 30s →
velocity spike → flash-sale at 15% because margin floor allows it"). The
reasoning chain is stored in `agent_actions.reasoning` (JSONB in Postgres) and
rendered in the option card's collapsible `<details>` element. No additional
Qwen call is needed — reasoning is part of the same tool-calling response.
The reasoning is also used by the `OutcomeObserver` to correlate
predicted outcomes with actual results for memory learning.

### Per-Product Targeting + Signal Freshness

When a velocity spike fires, Qwen targets the **specific product** that
spiked — not the whole store. The anomaly detection pipeline identifies which
product has disproportionate views, enriches the description with the product
name, and passes the product ID through the tool-calling chain so the flash
sale applies to exactly that product.

```
24 views on "Linen Blazer" in 30s
  → per-product counter identifies the spiking product
  → enriched anomaly: "Velocity spike: 24 views on Linen Blazer (abc-123)"
  → Qwen calls propose_flash_sale(product_id="abc-123", discount=15%)
  → promo applies to Linen Blazer specifically
  → option card shows "⎯ Target: abc-123" + age timer
```

Decision cards also have a **signal freshness TTL** (5 minutes, configurable).
If the merchant doesn't act within the window, the anomaly is considered
stale — the card shows an "Expired" state and the backend auto-dismisses it
to unblock future decisions. This prevents the system from getting stuck with
one ignored card blocking the entire autopilot pipeline.

**Behavior tracking from real traffic:** The storefront emits `view`,
`add_to_cart`, and `abandon` events from real customer browsing via a
dedicated tracking module (`lib/behavior.ts`). Product views use
IntersectionObserver (50% visibility threshold, 30s dedup per product).
Add-to-cart fires on every cart action. Abandon detection fires on page
visibility change when the customer has interacted but leaves without
purchasing. These events flow through the same WebSocket → behavior_tracker →
anomaly detection pipeline as the demo simulation — the autopilot works
identically with real and simulated traffic.

**Technical implementation:** `count_per_product_views_in_window()` in
`behavior_tracker.py` parses the Redis events list and returns a
`dict[product_id, view_count]`. `anomaly_description()` returns a
`(description, product_id)` tuple — the caller enriches the product_id with
the human-readable name from Postgres before passing to the decision cycle.
`_register_promo()` in `agent.py` reads `payload.get("product_id")` from
Qwen's tool call to target the correct product, falling back to the first
product only if the specified one was deactivated between decision and
approval. Stale card TTL is enforced in `run_decision_cycle()` — pending
actions older than `pending_action_ttl_seconds` are auto-dismissed and an
`ACTION_EXPIRED` WebSocket event pushes the removal to all connected
terminals.

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

**Technical implementation:** All Qwen calls go through a single `_qwen_chat()`
wrapper in `qwen.py` that checks Redis cache (keyed by prompt hash) before
making the API call, and writes the response to cache before returning. Cache
TTL: brand generation = permanent, descriptions = 24h, decisions = no cache
(state-dependent). `generate_descriptions()` batches all product names into one
prompt with numbered output slots — one API call regardless of catalog size.
`run_decision_cycle()` sends only the state diff (computed by `capture_snapshot()`
delta against the last snapshot), not the full `SystemState` — typically 60-80%
fewer tokens per call.

---

## Testing

**44 test files** (23 backend, 21 frontend) covering every Qwen output path
and validation layer.

**Backend** (`analytics-brain/tests/`, pytest — 23 files, ~970 lines):


| File                           | What it covers                                               |
| ------------------------------ | ------------------------------------------------------------ |
| `test_generate_layout_dsl.py`  | DSL generation, 3 defense layers, fallback path              |
| `test_css_gen.py`              | CSS generation + sanitization (forbidden patterns stripped)  |
| `test_brand_dsl_live.py`       | DSL save → normalize → regenerate integration                |
| `test_memory.py`               | Qwen memory loop (merchant behavior → future decisions)      |
| `test_layout_dsl_coerce.py`    | `coerce_variant()` — defense layer A (variant coercion)      |
| `test_layout_dsl_normalize.py` | `normalize_dsl()` — defense layer B (structural rules)       |
| `test_layout_dsl_fallback.py`  | `fallback_dsl_from_token()` — defense layer C (Qwen offline) |
| `test_layout_dsl.py`           | End-to-end DSL pipeline                                      |
| `test_outcome_observer.py`     | Outcome observation (attributed orders → memory)             |
| `test_decision_memory.py`      | Decision cycle + memory integration                          |
| `test_capability_tracker.py`   | Unmet intent tracking → capability proposals                 |
| `test_rbac.py`                 | Role-based access control (merchant vs customer)             |
| `test_auth.py`                 | JWT auth, bcrypt, httpOnly cookies                           |
| `test_behavior.py`             | Telemetry event tracking, anomaly detection                  |
| `test_storebirth.py`           | Store birth SSE streaming                                    |
| `test_store_dsl_backfill.py`   | DSL backfill for stores without layouts                      |
| `test_onboarding_live.py`      | Full onboarding integration flow                             |
| `test_products_live.py`        | Product CRUD + vision pipeline integration                   |
| `test_storefront_live.py`      | Storefront rendering integration                             |
| `test_store_dsl_live.py`       | Live DSL persistence and retrieval                           |
| `test_db_models_sprint3.py`    | SQLAlchemy model validation                                  |
| `test_memory_live.py`          | Memory persistence (Postgres + Redis mirror)                 |
| `test_storebirth_live.py`      | Store birth with real Qwen calls                             |


**Frontend** (`storefront-ui/`, Vitest — 21 files):


| File                                                            | What it covers                                    |
| --------------------------------------------------------------- | ------------------------------------------------- |
| `types/__tests__/layoutDsl.test.ts`                             | `LayoutDSLSchema.parse()` — Zod schema validation |
| `lib/__tests__/dslRenderer.test.tsx`                            | DSLRenderer safeParse + FallbackStorefront        |
| `lib/__tests__/distinctness.test.tsx`                           | 40-store distinctness guarantee                   |
| `lib/__tests__/builderStore.test.ts`                            | Builder state management                          |
| `lib/__tests__/harness.test.ts`                                 | Test harness infrastructure                       |
| `lib/__tests__/customerAuth.test.ts`                            | Customer auth flow                                |
| `components/storefront/__tests__/cssInjector.test.tsx`          | `CustomCSSInjector` — scoped CSS injection        |
| `components/storefront/__tests__/storeBirth.test.tsx`           | StoreBirth SSE streaming UI                       |
| `components/storefront/__tests__/productDrawer.test.tsx`        | Product add drawer                                |
| `components/storefront/cards/__tests__/cards.test.tsx`          | Product card variants                             |
| `components/storefront/nav/__tests__/nav.test.tsx`              | Navigation variants                               |
| `components/storefront/sections/__tests__/hero.test.tsx`        | Hero section rendering                            |
| `components/storefront/sections/__tests__/productGrid.test.tsx` | Product grid section                              |
| `components/storefront/sections/__tests__/bannerStory.test.tsx` | Banner story section                              |
| `components/storefront/sections/__tests__/addToCart.test.tsx`   | Cart integration                                  |
| `components/storefront/__tests__/detailCartVariants.test.tsx`   | Detail page + cart variants                       |
| `components/builder/__tests__/builderPreview.test.tsx`          | Builder preview rendering                         |
| `components/builder/__tests__/sectionList.test.tsx`             | Section reordering                                |
| `components/builder/__tests__/advisory.test.tsx`                | Brand guard advisory UI                           |
| `components/builder/__tests__/editPopover.test.tsx`             | Point-and-edit popover                            |
| `app/__tests__/brandReview.test.tsx`                            | Brand review onboarding step                      |


**Testing principle**: every Qwen output has a test that feeds it garbage and
asserts the system doesn't break. `coerce_variant()` receives a hallucinated
variant string → falls back to the type default. `normalize_dsl()` receives a
broken structure → repairs it in-place. `LayoutDSLSchema.safeParse()` receives
malformed DSL → `FallbackStorefront` renders. `sanitize_css()` receives CSS
with `@import` and `url()` → strips them silently.

---

## Stack


| Layer     | Technology                                                                       |
| --------- | -------------------------------------------------------------------------------- |
| Frontend  | Next.js 15, TypeScript, Tailwind, Framer Motion, Zustand                         |
| Backend   | FastAPI, Python 3.11, Pydantic v2, SQLAlchemy (async)                            |
| AI        | **qwen-vl-max** (vision) + **qwen-max** (text/decisions)                         |
| Real-time | WebSocket (full-duplex, event-driven, zero polling)                              |
| Database  | PostgreSQL (Alibaba Cloud RDS) — persistent source of truth                      |
| Cache     | Redis (Alibaba Cloud Tair) — telemetry, sessions, state                          |
| Storage   | Alibaba Cloud OSS — logos, product images (presigned PUT, never through backend) |
| Deploy    | Alibaba Cloud Function Compute (serverless) + Docker Compose (local)             |


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
fingerprinting, three-layer interceptor, **native tool-calling API for decision
cycles** (5 structured tools, typed parameters, no JSON parsing), token-efficient
batching, memory system that learns from merchant edits AND outcome observation,
LayoutDSL composition with three defense layers, creative extension for
merchant-directed design, transparent reasoning chains on every proposed action.
- **Innovation (30%)**: Qwen IS the runtime (not a feature), brand guard rules
authored by Qwen at creation time, Vision Fingerprinting for dedup, realtime
telemetry → decision → approve → morph cycle, option cards not chat,
fault-tolerant storefront, automatic catalog dedup, Qwen-powered catalog
audit, merchant-directed creative generation within brand constraints.

---

## Blog Post

[Elevate: Making Qwen the Brain of a Store That Runs Itself](https://dev.to/alpha-dev-001/elevate-making-qwen-the-brain-of-a-store-that-runs-itself-582p)

The full engineering story: architectural decisions, the memory learning loop,
the 3-layer interceptor design, and why Qwen IS the runtime — not a feature.

---

## License

MIT — see [LICENSE](./LICENSE)