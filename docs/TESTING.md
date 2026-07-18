# Elevate — Testing

**105 test files** (78 backend, 27 frontend) · **500+ backend tests** covering
every Qwen output path, validation layer, role/guard/learning path, and
adversarial input.

---

## Backend Tests (pytest — 78 files, 500+ tests)

_The table highlights the key suites; it is not the exhaustive file list._

| File                                | What it covers                                               |
| ----------------------------------- | ------------------------------------------------------------ |
| `test_generate_layout_dsl.py`       | DSL generation, 3 defense layers, fallback path              |
| `test_css_gen.py`                   | CSS generation + sanitization (forbidden patterns stripped)  |
| `test_brand_dsl_live.py`            | DSL save → normalize → regenerate integration                |
| `test_memory.py`                    | Qwen memory loop (merchant behavior → future decisions)      |
| `test_layout_dsl_coerce.py`         | `coerce_variant()` — defense layer A (variant coercion)      |
| `test_layout_dsl_normalize.py`      | `normalize_dsl()` — defense layer B (structural rules)       |
| `test_layout_dsl_fallback.py`       | `fallback_dsl_from_token()` — defense layer C (Qwen offline) |
| `test_layout_dsl.py`                | End-to-end DSL pipeline                                      |
| `test_outcome_observer.py`          | Outcome observation (attributed orders → memory)             |
| `test_decision_memory.py`           | Decision cycle + memory integration                          |
| `test_capability_tracker.py`        | Unmet intent tracking → capability proposals                 |
| `test_rbac.py`                      | Role-based access control (merchant vs customer)             |
| `test_auth.py`                      | JWT auth, bcrypt, httpOnly cookies                           |
| `test_behavior.py`                  | Telemetry event tracking, anomaly detection                  |
| `test_behavior_tracker.py`          | Redis sorted-set event tracking, windowed counts            |
| `test_storebirth.py`                | Store birth SSE streaming                                    |
| `test_store_dsl_backfill.py`        | DSL backfill for stores without layouts                      |
| `test_tools.py`                     | Qwen tool-calling interface                                  |
| `test_onboarding_live.py`           | Full onboarding integration flow (Qwen + DB)                 |
| `test_products_live.py`             | Product CRUD + vision pipeline integration                   |
| `test_storefront_live.py`           | Storefront rendering integration                             |
| `test_store_dsl_live.py`            | Live DSL persistence and retrieval                           |
| `test_db_models_sprint3.py`         | SQLAlchemy model validation                                  |
| `test_memory_live.py`               | Memory persistence (Postgres + Redis mirror)                 |
| `test_storebirth_live.py`           | Store birth with real Qwen calls                             |
| `test_adversarial_interceptor.py`   | Interceptor edge cases: negative prices, NaN, Inf, multi-patch attacks |
| `test_adversarial_css.py`           | CSS injection: `url()` exfiltration, `position:fixed` phishing, `@import` |
| `test_adversarial_vision.py`        | Vision edge cases: selfie, landscape, blank image, garbage price |
| `test_benchmarks.py`                | Benchmark framework: 5 scenarios, latency/quality/validity   |

---

## Frontend Tests (Vitest — 21 files)

| File                                                             | What it covers                                    |
| ---------------------------------------------------------------- | ------------------------------------------------- |
| `types/__tests__/layoutDsl.test.ts`                              | `LayoutDSLSchema.parse()` — Zod schema validation |
| `lib/__tests__/dslRenderer.test.tsx`                             | DSLRenderer safeParse + FallbackStorefront        |
| `lib/__tests__/distinctness.test.tsx`                            | 40-store distinctness guarantee                   |
| `lib/__tests__/builderStore.test.ts`                             | Builder state management                          |
| `lib/__tests__/harness.test.ts`                                  | Test harness infrastructure                       |
| `lib/__tests__/customerAuth.test.ts`                             | Customer auth flow                                |
| `components/storefront/__tests__/cssInjector.test.tsx`           | `CustomCSSInjector` — scoped CSS injection        |
| `components/storefront/__tests__/storeBirth.test.tsx`            | StoreBirth SSE streaming UI                       |
| `components/storefront/__tests__/productDrawer.test.tsx`         | Product add drawer                                |
| `components/storefront/cards/__tests__/cards.test.tsx`           | Product card variants                             |
| `components/storefront/nav/__tests__/nav.test.tsx`               | Navigation variants                               |
| `components/storefront/sections/__tests__/hero.test.tsx`         | Hero section rendering                            |
| `components/storefront/sections/__tests__/productGrid.test.tsx` | Product grid section                              |
| `components/storefront/sections/__tests__/bannerStory.test.tsx`  | Banner story section                              |
| `components/storefront/sections/__tests__/addToCart.test.tsx`    | Cart integration                                  |
| `components/storefront/__tests__/detailCartVariants.test.tsx`    | Detail page + cart variants                       |
| `components/builder/__tests__/builderPreview.test.tsx`           | Builder preview rendering                         |
| `components/builder/__tests__/sectionList.test.tsx`              | Section reordering                                |
| `components/builder/__tests__/advisory.test.tsx`                 | Brand guard advisory UI                           |
| `components/builder/__tests__/editPopover.test.tsx`              | Point-and-edit popover                            |
| `app/__tests__/brandReview.test.tsx`                             | Brand review onboarding step                      |

---

## Testing Principles

Every Qwen output has a test that feeds it garbage and asserts the
system doesn't break:

- `coerce_variant()` receives a hallucinated variant string → falls back
  to the type default
- `normalize_dsl()` receives a broken structure → repairs it in-place
- `LayoutDSLSchema.safeParse()` receives malformed DSL →
  `FallbackStorefront` renders
- `sanitize_css()` receives CSS with `@import` and `url()` → strips them
  silently

---

## Adversarial Testing

Three adversarial test suites cover attack vectors:

**Interceptor** (`test_adversarial_interceptor.py`):
- Negative prices, NaN, Infinity, zero-cost products
- Multi-patch attacks (one malicious patch hidden between two valid ones)
- Margin floor bypass attempts
- Discount ceiling violations

**CSS Sanitization** (`test_adversarial_css.py`):
- `url()` data-exfiltration attempts
- `position: fixed` phishing overlays
- `@keyframes` injection
- `z-index` stacking attacks
- `expression()` XSS payloads

**Product Vision** (`test_adversarial_vision.py`):
- Selfies, landscapes, blank images
- Garbage price values ($0, $999999, negative)
- `confident=False` fires correctly on ambiguous images
- Price clamping holds against outlier inputs

---

## Benchmarks

Five benchmark scenarios measure Qwen call performance and output
quality. The framework runs offline with mock data (verifying
infrastructure) and live with real Qwen API calls when `QWEN_API_KEY`
is set.

| Scenario           | Model       | Max Tokens | Measures                                       |
| ------------------ | ----------- | ---------- | ---------------------------------------------- |
| Logo Analysis      | qwen-vl-max | 512        | Vision latency, palette/mood validity          |
| Brand Generation   | qwen-max    | 2500       | Text latency, guard rule count, schema validity|
| Decision Cycle     | qwen-max    | 1000       | Tool-calling latency, action validity          |
| Product Vision     | qwen-vl-max | 400        | VL latency, confidence accuracy, price sanity  |
| Batch Descriptions | qwen-max    | 2000       | Batch latency, per-product quality             |

**Run benchmarks:**

```bash
# Offline (verifies framework, no API calls):
cd analytics-brain
pytest tests/test_benchmarks.py -v

# Live (real Qwen calls — requires QWEN_API_KEY):
pytest tests/test_benchmarks.py -v -k "live"
```

**Expected performance** (measured on DashScope International endpoint):

| Call               | Latency    | Notes                                |
| ------------------ | ---------- | ------------------------------------ |
| Logo analysis      | ~10-20s    | Multimodal image processing          |
| Brand generation   | ~35-45s    | 2500 tokens, heavy generation        |
| Decision cycle     | ~5-15s     | 1000 tokens with tool-calling        |
| Product vision     | ~10-20s    | Per image, multimodal                |
| Batch descriptions | ~20-30s    | Per chunk of 20 products             |
