# How Elevate Uses Qwen — Architecture & Token Economics

_Last updated: 2026-06-15. This reflects the code as built in Sprint 1._

## TL;DR
- **Two models**, used for four jobs. Everything is cached so we never pay twice.
- We send Qwen **the logo (once)** and **product names/categories/prices** — never
  customer data, never the whole database, never telemetry in full.
- A fully-onboarded store with ~90 products costs roughly **a few cents** of tokens.
- One known bug (fixed alongside this doc): very large product batches (~95+)
  overflowed an output cap and fell back to plain descriptions.

---

## The two models

| Model | Used for | Why |
|-------|----------|-----|
| `qwen-vl-max` | Logo analysis (vision) | Reads the image → colors, mood, style |
| `qwen-max` | Brand, SVG icons, product descriptions | Best structured-JSON quality |

That's the whole roster. No dynamic router, no model zoo.

---

## The call map (what fires, when)

| When | Model | Calls | What we send | What we get | Cached? |
|------|-------|-------|--------------|-------------|---------|
| Logo drop | qwen-vl-max | 1 | the logo image (URL or base64) + a short prompt | colors, mood, style | brand pkg cached forever |
| Brand gen | qwen-max | 1 | the logo analysis JSON + store name/category | palette, fonts, voice, guard rules | yes (Redis + Postgres) |
| Icons | qwen-max | 1 | palette + style (no image) | 2 small SVG marks | yes |
| Add products | qwen-max | 1 per ~20 products | product **names/categories/prices only** | one description each | stored on the product |
| Decisions (Sprint 2) | qwen-max | 1 per anomaly | a telemetry **diff**, not full state | option cards | — |

Key properties already enforced in code:
- **Brand is generated once and cached forever** — revisiting onboarding or the
  storefront never re-calls Qwen. It only regenerates if a merchant re-onboards.
- **Descriptions are batched**, never one-call-per-product.
- **No customer/PII** is ever sent. Product calls contain only catalog fields
  (name, category, price). Telemetry (Sprint 2) will send snapshot *diffs*, not
  the full state.

---

## "Are we sending all 90 products to Qwen?"

Yes — but in **one batched call per chunk**, not 90 calls, and only three fields
per product (name, category, price). For a 90-product CSV that's a single prompt
of ~1.5K input tokens, not a data dump. We do **not** send descriptions you
already have, images, stock levels, costs, or anything about customers.

---

## Token estimates (rough, per call)

Estimates — actual varies with image size and model verbosity. Treat as
order-of-magnitude.

| Call | Input tokens | Output tokens | Notes |
|------|-------------:|--------------:|-------|
| Logo analysis | ~700–1,500 | ~300–500 | image dominates input |
| Brand generation | ~800–1,000 | ~1,200–1,500 | guard rules + voice |
| Icons | ~300–400 | ~400–600 | small SVGs |
| Descriptions (per 20 products) | ~500 | ~800–1,000 | ~40 tokens/product |

### Per store
- **Onboarding (logo + brand + icons):** ~3 calls, ~**5K total tokens**, one time.
- **90 products:** ~5 chunked calls, ~**7K total tokens**, one time.
- **A fully built store with 90 products:** ~**12K tokens total, ever** (then cached).

### Cost ballpark
Model Studio (international) qwen-max/qwen-vl-max list pricing is on the order of
single-digit dollars per **million** tokens. So:
- One onboarded store ≈ **a fraction of a cent** of tokens.
- That store + 90 products ≈ **a few cents**, one time.

> Verify current rates at
> https://www.alibabacloud.com/help/en/model-studio/models — pricing changes and
> there are free tiers. The takeaway: at our scale, tokens are not the cost driver.

---

## The 96-product bug (found 2026-06-15, fixed)

**Symptom:** a 96-row product import produced 96 plain `"{name}."` descriptions
instead of Qwen copy. A 91-row import worked.

**Cause:** all descriptions were generated in a **single** qwen-max call capped
at 3,500 output tokens. ~91 products fit; ~96 overflowed, the JSON truncated, and
the parser fell back to plain copy for **all** of them (all-or-nothing).

**Fix:** descriptions now generate in **chunks of ~20 products**, run in parallel.
Each chunk is well under the token budget, failures are isolated to a chunk
(not the whole import), and large catalogs work reliably.

To regenerate descriptions for an already-imported store (e.g. Haree), we can add
a one-shot "regenerate descriptions" action — flagged as a follow-up.

---

## What's deliberately NOT sent to Qwen
- Customer identities, sessions, or browsing data (Sprint 2 sends only anonymized
  snapshot diffs)
- Passwords, emails, or any auth material
- Product cost prices or margins (those never leave the backend)
- The full system state on every decision — only the diff since last snapshot
