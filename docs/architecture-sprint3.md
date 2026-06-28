# Elevate — Sprint 3 Architecture (Qwen Call Chain)

> The codebase is the body. Qwen is the brain. Sprint 3 takes the Qwen chain
> from 2 calls to 5+ and closes the cognitive loop: action → outcome → memory →
> smarter next decision.

## The Qwen Call Chain (5+ distinct calls)

```
 Logo (OSS URL)
     │
     ▼
┌──────────────────────────┐
│ ① qwen-vl-max            │  analyze_logo()           cache: brand:{id}
│   image → LogoAnalysis   │  (geometry, palette, mood)
└──────────────────────────┘
     │
     ▼
┌──────────────────────────┐
│ ② qwen-max               │  generate_brand_token()   cache: brand_tokens JSONB
│   → BrandToken           │  (colors, type, layout DNA, mood, industry)
└──────────────────────────┘
     │
     ▼
┌──────────────────────────┐
│ ③ qwen-max               │  generate_layout_dsl()    cache: layout_dsl:{id} (forever)
│   → LayoutDSL            │  sections[] + global_config + product_card
│   Defense A/B/C:          │  coerce_variant → normalize_dsl → fallback_dsl_from_token
│   never a broken store    │  (brand-seeded fallback guarantees distinctness if Qwen is down)
└──────────────────────────┘
     │
     ▼
┌──────────────────────────┐
│ ④ qwen-max               │  generate_custom_css()    stored in layout_dsl.custom_css
│   → scoped CSS block     │  sanitize_css (allowlist, [data-store="slug"] only)
└──────────────────────────┘
     │
     ▼  StoreBirth SSE  (GET /api/brand/birth/{slug}) streams ①–④ as visible steps
     │
     ▼
 Store Builder (human-in-the-loop)
   drag-to-reorder · variant swap · color change → local brand-guard advisory
   PUT /api/brand/dsl/{slug}  (re-runs normalize_dsl)   →  Publish → /s/{slug}
     │
     ▼
 Customer browsing → behavior events → Redis → deterministic anomaly threshold
     │
     ▼
┌──────────────────────────────────────────────┐
│ ⑤ qwen-max  run_decision_cycle()             │  reads MEMORY first:
│   reads build_memory_context(get_memory())   │  "What I know about this store: …"
│   → AgentAction (option card)                 │  WS payload: estimated_tokens, memory_count
└──────────────────────────────────────────────┘
     │ merchant approves / dismisses (human-in-the-loop checkpoint)
     ▼
 Delta executed → storefront morphs (fluid)
     │
     ▼
┌──────────────────────────────────────────────┐
│ Outcome Observer (background)                 │  schedule_observation() on promo expiry
│   observe_outcome(): count attributed orders  │  write_memory() → merchants.qwen_memory
│   → MemoryEntry                               │  + Redis merchant_memory:{id}
└──────────────────────────────────────────────┘
     │
     └──────────────►  feeds back into ⑤ next cycle  (the loop closes — Qwen learns)

  [post-hackathon, designed not built]
  action_outcomes(embedding vector(1536)) — cross-store RAG: "what worked for
  similar brands" injected at decision time. pgvector + ivfflat cosine index.
```

## Data layers
- **Postgres (source of truth):** `brand_profiles.brand_tokens` JSONB now carries
  `layout_dsl` (incl. `custom_css`); `merchants.qwen_memory` JSONB; `agent_actions`
  gains `merchant_behavior` + `trigger_description`.
- **Redis (fast layer):** `layout_dsl:{id}` (forever), `merchant_memory:{id}`,
  brand/profile/onboarding-phase caches. Always best-effort — never the only copy.

## Distinctness guarantee (40 stores → 40 distinct)
Three layers make a broken/templated store impossible:
- **A — `coerce_variant`**: type-aware; cross-type or hallucinated variants fall to the type default.
- **B — `normalize_dsl`**: structural rules (≤1 hero leads; ≥1 grid; announcement-bar floats top; 2–5 sections; no adjacent banners). The renderer trusts only this.
- **C — `fallback_dsl_from_token`**: deterministic, **brand-seeded** (`hash(store_name+mood+industry)`) — distinct stores even with Qwen offline.

## Frontend rendering
`DSLRenderer` reads `store.brand_token.layout_dsl`, injects scoped CSS, and composes
from registries (`SECTION_REGISTRY` 4+4+3+3, `CARD_REGISTRY` 6, `NAV_REGISTRY` 5).
No `layout_dsl` → `FallbackStorefront` (pre-Sprint-3 appearance).
