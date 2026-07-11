# Elevate — Technical Deep Dive

> Everything under the hood. Read this after the README if you want to
> understand *how*, not just *what*.

---

## Contents

- [Onboarding (5 steps, < 30 seconds to live store)](#onboarding-5-steps--30-seconds-to-live-store)
- [The Three-Layer Interceptor](#the-three-layer-interceptor)
- [Validation Architecture — Defense in Depth](#validation-architecture--defense-in-depth)
- [Fault-Tolerant Storefront — Three Defense Layers](#fault-tolerant-storefront--three-defense-layers)
- [CSS Sanitization Guardrail](#css-sanitization-guardrail)
- [Real-Time Telemetry Pipeline](#real-time-telemetry-pipeline)
- [Product Vision Pipeline](#product-vision-pipeline)
- [Decision Memory — Not Fine-Tuning, By Design](#decision-memory--not-fine-tuning-by-design)
- [Duplicate Detection + Catalog Audit](#duplicate-detection--catalog-audit)
- [Qwen Creative Extension](#qwen-creative-extension)
- [Qwen Reasoning — Transparent Decisions](#qwen-reasoning--transparent-decisions)
- [Per-Product Targeting + Signal Freshness](#per-product-targeting--signal-freshness)
- [MCP Server — External Agent Integration](#mcp-server--external-agent-integration)
- [Token Efficiency + Cost Metering](#token-efficiency--cost-metering)

---

## Onboarding (5 steps, < 30 seconds to live store)

1. **The Drop** — Merchant uploads a logo. Direct to OSS via presigned PUT
   (backend never touches file bytes — serverless-safe).
2. **The Incubation** — `qwen-vl-max` reads the logo, extracts geometry,
   palette, and mood. `qwen-max` generates the full brand package: color
   palette, typography, voice profile, layout variant, and **guard rules**
   — the brand's immune system, written in Qwen's own words.
3. **The Reveal** — Store shell renders with the generated brand. Colors,
   typography, SVG icons, all on-brand. If zero products: a beautiful
   "Preparing the shelves..." state that looks intentional, not broken.
4. **Product Vision** — Merchant drops product photos. Each is
   fingerprinted for dedup, uploaded to OSS, then `qwen-vl-max` identifies
   it: name, brand (only if visible in the photo), description in the
   store's voice, category, colorways, and a price anchored to the
   merchant's baseline (never web MSRP). Products land as **pending** —
   the merchant approves each one.
5. **The Launch** — Merchant publishes. SystemState initializes in Redis.
   Store goes live at `/s/{slug}`. Approved products sync to the
   storefront instantly via WebSocket — no republish needed.

**Technical implementation:** The STS upload flow (`POST /api/upload/token`)
generates temporary OSS credentials (15-min expiry) — the frontend uploads
binary directly to OSS, never through the backend (serverless functions
must not handle file bytes). Brand generation chains `_run_vl()`
(qwen-vl-max, image → `LogoAnalysis`) then `generate_brand()`
(qwen-max → `GeneratedBrand` + `BrandGuardRules`) in sequence, both
server-side. Results are cached in Redis keyed by `logo_url` — subsequent
loads are O(1) cache hits. StoreBirth streams each step as SSE events
(`analyzing_geometry`, `extracting_palette`, `generating_brand`,
`composing_layout`) so the frontend shows a fluid loading state.
Target: < 5 seconds total. `generate_layout_dsl()` runs through the
3-layer defense pipeline (coerce → normalize → fallback) before the DSL
is persisted to `brand_tokens.layout_dsl` (JSONB in Postgres).

---

## The Three-Layer Interceptor

Every Qwen-proposed action passes through three validation layers before
reaching the merchant. This is the brand's immune system:

| Layer                    | Source                           | Behavior                                                                                  |
| ------------------------ | -------------------------------- | ----------------------------------------------------------------------------------------- |
| **Brand Guard**          | Qwen-authored at brand gen time  | Fires Qwen's own warning about color conflicts, voice mismatches. Does not block — flags. |
| **Business Constraints** | Merchant's margin/discount rules | Auto-clamps values with warning shown to merchant. Price below margin floor → clamped.    |
| **System Safety**        | Hardcoded                        | Price below cost, stock below zero, expired promo → **hard block**. No exceptions.        |

**Technical implementation:** The interceptor is pure deterministic Python —
zero LLM involvement. `validate_action()` in `interceptor.py` runs all
three layers in sequence. `enforce_price()` computes
`min_price = cost_price * (1 + margin_floor)` and clamps the proposed
price if it falls below. `enforce_discount()` checks the proposed discount
against `max_discount_pct` and `promo.expires_at`. Layer 1 matches the
action's target field against `BrandGuardRules.rules` — if a rule fires,
the warning message is Qwen's own pre-authored text (generated at brand
creation, stored in Postgres, surfaced instantly with zero latency).
`validate_action()` returns `ValidationResult(passed=bool,
clamped: dict | None, blocked: list[Violation])`. No retry logic — a
blocked action is returned to the client as HTTP 409.

The interceptor is immutable. Qwen cannot override it. This is what makes
the autopilot trustworthy — the merchant's rules are enforced regardless
of what Qwen proposes.

---

## Validation Architecture — Defense in Depth

Every Qwen output is validated server-side AND client-side before
rendering. No LLM output reaches the DOM unvalidated.

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
hallucinated a field or returned malformed JSON, the Pydantic model
catches it before the data is stored or returned. `_extract_json()` in
`brand.py` handles the common case of Qwen wrapping JSON in markdown
code fences.

**Client-side**: Zod schemas in `types/schemas.ts` mirror every Pydantic
model exactly. `LayoutDSLSchema.safeParse()` is called in `DSLRenderer`
before rendering — if validation fails, `FallbackStorefront` renders
instead. The WebSocket client uses `BrandReadyPayloadSchema.safeParse()`
on every incoming event payload.

**The interceptor's Layers 2 and 3 are deterministic Python.** No LLM
involvement. `enforce_price()` checks
`price >= cost_price * (1 + margin_floor)` — hard math, not vibes.
Layer 3 blocks (`stock < 0`, `price < cost`, `expired promo`) return
409 to the client with no override path.

---

## Fault-Tolerant Storefront — Three Defense Layers

Qwen composes every store's layout (section order, variant choices, nav
style, card design). But Qwen can hallucinate, return malformed JSON, or
time out. A broken Qwen response must never produce a broken store.

Three defense layers guarantee a renderable, on-brand storefront
regardless of what Qwen returns:

| Layer | Name                      | Behavior                                                                                                                                                                                                                                                 |
| ----- | ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A** | `coerce_variant`          | Every section variant is validated against its type's allowed set. A hallucinated or cross-type variant (e.g. a grid variant on a hero) is coerced to the type's default. Near-miss strings are normalized and matched (`"masonry"` → `"masonry-4col"`). |
| **B** | `normalize_dsl`           | Structural rules enforced on every save and regeneration: exactly one leading hero, at least one product grid, 2–5 sections total, no adjacent banners. Violations are repaired, not rejected.                                                           |
| **C** | `fallback_dsl_from_token` | When the Qwen call fails entirely (network, timeout, garbage), a deterministic DSL is generated from `hash(store_name + mood + industry)`. Stores stay distinct even with Qwen offline — no two brands fall back to the same template.                   |

**Graceful degradation on the frontend**: if the Zod schema validation
fails on the DSL received from the backend, `DSLRenderer` renders
`FallbackStorefront` — a fully functional, brand-themed storefront
(search, categories, product grid, cart) that uses the brand's palette
and typography without relying on the DSL. The store never shows a blank
page or an error.

**Technical implementation:** `coerce_variant()` (defense A) uses a
lookup table `VALID_VARIANTS` keyed by `SectionType` enum — near-miss
strings are normalized via `_norm()` (lowercase + strip non-alphanumeric)
and matched against the allowed set; cross-type values are never honored.
`normalize_dsl()` (defense B) is a pure function: ensures exactly one
leading hero (`sections[0].type == "hero"`), at least one product grid,
2–5 sections total (truncates excess, pads shortage), and no adjacent
banners. All violations are repaired in-place, not rejected.
`fallback_dsl_from_token()` (defense C) uses
`_seed() = hash(store_name + mood + industry)` to deterministically pick
from variant pools — same brand always produces the same fallback layout,
even with Qwen completely offline.

---

## CSS Sanitization Guardrail

Qwen generates scoped CSS for micro-interaction personality (hover
transforms, letter-spacing, transitions). This CSS is injected into the
live storefront. Unsanitized AI-generated CSS is a security and
brand-integrity risk.

The sanitization pipeline:

1. **Property allowlist** — only 8 properties permitted: `transform`,
   `transition`, `letter-spacing`, `line-height`, `text-decoration`,
   `opacity`, `border-radius`, `box-shadow`. Everything else is stripped.
2. **Forbidden patterns** — `url()`, `@import`, `@keyframes`,
   `position: fixed`, `z-index` are rejected entirely.
3. **Scope enforcement** — only rules scoped to `[data-store="{slug}"]`
   are kept. One store's CSS can never affect another.

**Technical implementation:** `sanitize_css(css, slug)` in `css_gen.py`
runs three regex-based passes. The sanitizer runs server-side before
storage — by the time CSS reaches the browser, it has already been
validated. `generate_custom_css()` calls qwen-max with a constrained
prompt that lists the allowed properties upfront, reducing the chance of
forbidden output. Even when Qwen obeys, the sanitizer runs as a
defense-in-depth pass — prompt compliance is never trusted.

---

## Real-Time Telemetry Pipeline

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

The trigger is deterministic and configurable (`ANOMALY_THRESHOLD`,
`ANOMALY_WINDOW_SECONDS`) — if a product gets 5+ views in 30 seconds,
Qwen fires a decision cycle. The autonomy is in the response chain:
Qwen reasons about what action to take, which product to target, what
discount to offer — informed by memory of what worked before.

**Technical implementation:** Events are discrete browser interactions
(`view`, `hover`, `cart_add`, `purchase`, `abandon`) sent as JSON frames
over WebSocket — not video, not streams. `push_event()` in
`behavior_tracker.py` writes to a Redis sorted set
(`ZADD velocity:{merchant_id}:{product_id} timestamp event_id`) — O(log n)
per insertion. `count_views_in_window()` uses `ZRANGEBYSCORE` to count
events in the configured time window. When the threshold is exceeded,
`run_decision_cycle()` in `decision_engine.py` uses **Qwen's native
tool-calling API** — 5 tools defined in `tools.py` (one per action type:
`propose_flash_sale`, `propose_scarcity_price`, `propose_layout_morph`,
`propose_recovery_offer`, `propose_copy_rewrite`). Qwen selects which
tool to call and fills typed parameters — no JSON output parsing needed.
Tool arguments become the execution payload directly. Reasoning comes
from Qwen's message content alongside the tool call. Memory context and
business constraints are injected into the prompt.

---

## Product Vision Pipeline

```
Merchant drops photos
  → Client-side: perceptual hash (aHash) groups near-duplicates
  → Upload all to OSS (duplicates get URLs too, just skip vision)
  → POST /products/vision-batch (only representatives)
  → asyncio.Semaphore(5): 5 parallel qwen-vl-max calls
  → Each returns: name, brand, description, category, colors, price, confidence
  → Products created as pending (is_active=False)
  → CatalogReview: per-product Approve / Discard / Approve All
  → Approved products flip is_active=True → sync to live storefront instantly
  → confident=False products flagged for CatalogReview
```

The `confident=False` flag is honesty by design. When Qwen can't clearly
identify a product, it says so — the merchant reviews it rather than a
silent wrong guess going live.

**Human correction workflow** — when Qwen misreads a product (wrong name,
bad price, wrong category), the merchant fixes it inline:

1. **Pending products** land in the CatalogReview section with image,
   name, price, category, and description — all editable inline.
2. **`confident=False` products** get a visible "needs verification"
   badge.
3. **Inline editors** — every field is editable in-place. The merchant
   corrects the value and taps Approve.
4. **Every correction is recorded** — the PATCH writes a `MemoryEntry`
   with the old → new diff. Future vision calls read this memory, so
   Qwen stops making the same mistake for this merchant.
5. **Discard** — if the product is unsalvageable, one tap hard-deletes
   it from the database.

**Technical implementation:** `analyze_product_image()` in `vision.py`
calls `qwen-vl-max` with a structured prompt. `asyncio.Semaphore(5)`
caps parallel calls. Each response is validated through Pydantic's
`ProductVision` model — malformed JSON triggers one retry. Perceptual
hashing uses aHash (8×8 = 64-bit) computed client-side in
`fingerprint.ts` — hamming distance ≤ 5 = near-duplicate, ~2ms per
image. Prices are anchored to the merchant's baseline via
`margin_floor_price()` — never web MSRP. Memory context
(`build_memory_context()`) is injected into the vision prompt at zero
extra token cost when entries exist.

---

## Decision Memory — Not Fine-Tuning, By Design

Every merchant action Qwen observes is appended to `qwen_memory` on the
Merchant record. Two memory sources feed the learning loop:

1. **Merchant edits**: When a merchant changes a product's price, name,
   or category, a `MemoryEntry` records the old → new diff. Future
   vision calls and description generation include this memory — Qwen
   names, prices, and describes products the way the merchant has
   demonstrated they prefer.
2. **Outcome observation**: The `OutcomeObserver` runs after each agent
   action expires, counting attributed orders (joined by `promo_id`) and
   writing `MemoryEntry` records. The next decision cycle reads this
   memory first — Qwen proposes differently based on what actually worked.

**Why context injection, not fine-tuning:** Memory is implemented as
structured context injection — not fine-tuning or embedding-based
retrieval. Each memory entry records what the merchant changed and what
happened when Qwen's proposal was executed. The last 5 entries are
injected into the next decision cycle's prompt as plain text. This is
intentional: for a real-time commerce system, prompt-level memory is
auditable (you can read every entry), reversible (delete an entry and
it's gone from the next call), and has zero cold-start cost (no model
retraining, no embedding index warmup). Fine-tuning qwen-max would
require thousands of examples and days of training for marginal
improvement over well-structured context injection.

**Technical implementation:** `write_memory()` in `memory.py` inserts
into `merchants.qwen_memory` (JSONB column via SQLAlchemy) and mirrors to
Redis key `merchant_memory:{id}` — both in one transaction.
`build_memory_context()` formats the last 5 entries as plain-text prompt
injection: "The merchant preferred X over Y" / "A flash-sale at 15%
drove 3 orders." `OutcomeObserver` (`observe_outcome()`) is scheduled
via `schedule_observation()` — a background task that fires when the
promo expires, counts orders joined by `promo_id`, and writes an outcome
`MemoryEntry` with `summarize_outcome()` (e.g., "flash_sale at 15% → 3
orders, $127 revenue"). Memory is capped at 20 entries per merchant
(FIFO eviction). If Redis is down, `get_memory()` falls back to
Postgres — O(n) query with `LIMIT 20`. Memory failures are caught in a
try/except and logged — they never block the calling operation.

The merchant never talks to Qwen. Qwen just learns.

---

## Duplicate Detection + Catalog Audit

Two-layer catalog hygiene — automatic and Qwen-powered:

**Automatic deduplication** (`POST /products/deduplicate`):
- Groups products by primary image URL
- Qwen-generated duplicates → auto-merged (keep first, hard-delete extras)
- Merchant-written duplicates → flagged for human review
- Runs automatically on every products page load
- Zero LLM calls — deterministic image URL comparison

**Qwen catalog audit** (`POST /products/catalog-audit`):
- One `qwen-max` call reviews up to 100 products
- Checks: pricing anomalies, missing categories, naming issues,
  description quality, duplicates
- Returns `catalog_score` (0-100), individual findings with severity,
  and specific actionable fixes
- Results cached in Redis keyed by merchant ID — subsequent audit reads
  hit cache until the catalog changes

**Technical implementation:** `review_catalog()` in `catalog.py` sends
all products (up to 100) to `qwen-max` in one batched call, requesting
`CatalogAuditReport` with `catalog_score`, `findings[]` (severity:
critical/warning/info), and specific fixes. `confident=False` products
from the vision pipeline are automatically included in audit scope.

---

## Qwen Creative Extension

The store builder has a free-text creative input: "Tell Qwen what you
want." The merchant types their vision (e.g. "I want a bold hero with a
full-bleed image, then a story about craftsmanship") and `qwen-max`
composes a new DSL layout guided by that direction.

The output passes through the same 3-layer defense pipeline (coerce →
normalize → fallback). This is brand-guarded creative direction within
the existing DSL schema — never unconstrained codegen.

**Technical implementation:** The creative input is appended to the
existing `generate_layout_dsl()` prompt — no separate prompt template
needed. The response is a `LayoutDSL` JSON object that goes through the
identical `coerce_variant()` → `normalize_dsl()` →
`fallback_dsl_from_token()` pipeline. The DSL schema constrains what
Qwen can output — even unconstrained creative direction stays within the
renderable section/card/nav registries.

---

## Qwen Reasoning — Transparent Decisions

Every proposed action includes Qwen's step-by-step reasoning chain,
visible in a collapsible section on each option card:

> "12 views on slides in 30s → velocity spike → flash-sale at 15%
> because margin floor allows it → expected ~3 conversions"

The reasoning is stored alongside the action and surfaced on demand —
subtle by default, deep when the merchant wants to understand why.

**Technical implementation:** When Qwen calls a tool via the decision
cycle's tool-calling API, the response includes both `message.content`
(free-text reasoning) and `message.tool_calls` (structured parameters).
The reasoning is extracted from `message.content` and stored in
`agent_actions.reasoning` (JSONB in Postgres). Rendered in the option
card's collapsible `<details>` element. No additional Qwen call needed
— reasoning is part of the same tool-calling response.

---

## Per-Product Targeting + Signal Freshness

When a velocity spike fires, Qwen targets the **specific product** that
spiked — not the whole store. The anomaly detection pipeline identifies
which product has disproportionate views, enriches the description with
the product name, and passes the product ID through the tool-calling
chain so the flash sale applies to exactly that product.

```
24 views on "Linen Blazer" in 30s
  → per-product counter identifies the spiking product
  → enriched anomaly: "Velocity spike: 24 views on Linen Blazer (abc-123)"
  → Qwen calls propose_flash_sale(product_id="abc-123", discount=15%)
  → promo applies to Linen Blazer specifically
  → option card shows "Target: abc-123" + age timer
```

Decision cards also have a **signal freshness TTL** (5 minutes,
configurable). If the merchant doesn't act within the window, the anomaly
is considered stale — the card shows "Expired" and the backend
auto-dismisses it. This prevents the system from getting stuck with one
ignored card blocking the entire autopilot pipeline.

**Behavior tracking from real traffic:** The storefront emits `view`,
`add_to_cart`, and `abandon` events from real customer browsing via
`lib/behavior.ts`. Product views use IntersectionObserver (50%
visibility threshold, 30s dedup per product). Add-to-cart fires on every
cart action. Abandon detection fires on page visibility change when the
customer has interacted but leaves without purchasing.

**Technical implementation:** `count_per_product_views_in_window()` in
`behavior_tracker.py` returns a `dict[product_id, view_count]`.
`anomaly_description()` returns a `(description, product_id)` tuple.
`_register_promo()` in `agent.py` reads `payload.get("product_id")`
from Qwen's tool call to target the correct product. Stale card TTL is
enforced in `run_decision_cycle()` — pending actions older than
`pending_action_ttl_seconds` are auto-dismissed and an `ACTION_EXPIRED`
WebSocket event pushes the removal to all connected terminals.

---

## MCP Server — External Agent Integration

Elevate exposes its autonomous agent via the **Model Context Protocol
(MCP)**, allowing any MCP-compatible client (Claude Desktop, Cursor, or
another AI agent) to drive the store's autopilot programmatically.

**5 tools:**

| Tool | What it does |
|------|-------------|
| `elevate_get_store_state` | Read the live SystemState (products, promos, layout, recovery) |
| `elevate_run_decision_cycle` | Trigger Qwen's decision engine with a custom anomaly description |
| `elevate_approve_action` | Approve a pending agent action — executes the payload |
| `elevate_dismiss_action` | Dismiss a pending action — Qwen learns from the rejection |
| `elevate_get_terminal_feed` | Read recent agent actions and their statuses |

**Run the MCP server:**

```bash
cd analytics-brain
pip install -r requirements.txt
python -m app.mcp_server
# Or via FastMCP CLI:
fastmcp run app/mcp_server.py:mcp
```

The MCP server shares the same Redis and Postgres as the FastAPI backend
— actions approved via MCP execute on the live store state.

---

## Token Efficiency + Cost Metering

Every Qwen call does maximum work. No throwaway calls.

- **Brand generation**: One `qwen-vl-max` + one `qwen-max` call. Cached
  forever.
- **Product descriptions**: All names batched into ONE `qwen-max` call.
  Never looped per product.
- **Product Vision**: One `qwen-vl-max` per unique product
  (fingerprinting eliminates duplicates). Memory-informed prompts at
  zero extra cost.
- **Decision cycles**: Send snapshot **diff** only, not full state.
  Includes reasoning chain.
- **Catalog audit**: ONE `qwen-max` call reviews up to 100 products.
- **Creative DSL**: ONE `qwen-max` call reusing existing prompt
  infrastructure.
- **Duplicate detection**: Zero Qwen calls — deterministic image URL
  comparison.
- **Memory injection**: Zero additional tokens when memory is empty.
- **Every output cached in Redis** before returning. Cache hit = zero
  tokens.

**Runtime cost metering:** Every `_qwen_chat()` call extracts
`usage.prompt_tokens` and `usage.completion_tokens` from the response
and records them in Redis (`elevate:{merchant_id}:qwen_usage`, capped at
200 entries, 7-day TTL). Each record includes: model, step name,
input/output tokens, and estimated USD cost based on DashScope pricing
(qwen-max: $0.004/1k input + $0.012/1k output). The terminal WS feed
includes a cumulative usage summary on every decision push. The
dashboard API exposes `/api/dashboard/{slug}/usage` for aggregate cost
data.

**Technical implementation:** All Qwen calls go through a single
`_qwen_chat()` wrapper in `brand.py` with connection pooling (shared
`httpx.AsyncClient` with keepalive connections — saves ~200ms TCP+TLS
per call), bounded exponential backoff, and per-call timeout. Cache
strategy: brand generation = permanent, descriptions = 24h, decisions =
no cache (state-dependent), catalog audit = 1 day.
`run_decision_cycle()` sends only the state diff (computed by
`capture_snapshot()` delta against the last snapshot), not the full
`SystemState` — typically 60-80% fewer tokens per call.
