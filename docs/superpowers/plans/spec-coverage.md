# Spec Coverage vs `docs/read.md`
> Branch: sprint-2 · Last updated: 2026-06-27

---

## Summary

| Area | Status |
|------|--------|
| Data models | ✅ Complete |
| Brand engine (Qwen-VL + Qwen-Max) | ✅ Complete |
| Decision engine (anomaly → action → approve) | ✅ Complete |
| Behavior simulation | ✅ Complete |
| Attribution dashboard (10% fee) | ✅ Complete |
| 4 layout variants (editorial / bold-grid / minimal-dark / warm-craft) | ✅ Complete |
| All storefront sub-components (Hero, Grid, Card, CategoryNav) | ✅ Complete |
| Merchant terminal (option cards, approve/dismiss) | ✅ Complete |
| WebSocket (agent_action, state_updated) | ✅ Complete |
| StoreBirth SSE progress sequence (§9) | ❌ Not built |
| BehaviorPulse live session feed | ❌ Not built |
| OSS `oss2.Auth` SDK call visible in backend | ⚠️ Partial |
| Alibaba FC deployment + CI/CD pipeline | ⚠️ Partial |
| Architecture diagram | ❌ Not built |
| Demo video | ❌ Not recorded |

---

## Section-by-Section

### §2 — Data Models

| Model | Spec wants | Status |
|-------|-----------|--------|
| Store | slug, name, logo_url, brand_tokens (JSONB), brand_rules, tier | ✅ Exists as `MerchantDB` + `BrandProfileDB` with `brand_tokens` column |
| BrandToken | colors, typography, layout (4 variants), mood, industryHint, brandVoice | ✅ Full schema in `schemas.py` + `schemas.ts` |
| Product | id, store_id, name, description, price, category, image_url, stock, is_featured | ✅ `ProductDB` — equivalent |
| AgentAction | id, store_id, promo_id, action_type, trigger, payload, estimated_gmv, status, timestamps | ✅ `AgentActionDB` — full match |
| Order | id, store_id, promo_id (attribution link), total, created_at | ✅ `OrderDB` with `promo_applied` |
| BehaviorEvent | Redis only — event_type, product_id, session_id, timestamp | ✅ Redis list via `Keys.events(merchant_id)` |

---

### §4 — Core Services

| Service | Spec wants | Status |
|---------|-----------|--------|
| `brand_engine.py` | Qwen-VL-Max logo → BrandToken + BrandGuardRules | ✅ `brand.py` — `analyze_logo()` + `generate_brand_token()` + guard rules |
| `decision_engine.py` | Qwen-Max → AgentAction JSON → persist → WS push | ✅ `decision_engine.py` — full cycle with gate (no double-firing) |
| `behavior_tracker.py` | Redis event push + anomaly threshold check | ✅ `behavior_tracker.py` — env-var thresholds |
| `oss_service.py` | `oss2.Auth` SDK call, `bucket.put_object()` | ⚠️ Sprint 1 uses **STS presigned PUT** (frontend uploads directly). `oss2` is not called in Python service. Spec requires at least one `oss2` SDK call visible. |
| `store_generator.py` | brand token → store config | ✅ Handled inside `brand.py` + `store.py` (no separate file — acceptable) |
| `websocket/manager.py` | WS connection manager | ✅ `ws_manager.py` — `push_to_terminal()`, `push_to_storefront()`, `push_to_all()` |

---

### §5 — API Endpoints

#### Store Birth Flow

| Endpoint | Spec | Status |
|----------|------|--------|
| `POST /api/stores/create` (multipart + SSE stream) | Upload logo → OSS → Qwen-VL → BrandToken → seed products → SSE progress events | ⚠️ We have `POST /onboarding/start` + WS `brand_ready` event — no SSE stream, no single multipart endpoint. Functionally equivalent but **demo UX differs significantly** (see §9) |
| `GET /api/stores/{slug}` | Full store + brand_tokens + products | ✅ Exists as `GET /api/store/{slug}` — returns `PublicStore` with `brand_token` |
| `GET /api/stores/{slug}/products` | Paginated products | ✅ Products included in `PublicStore` response |

#### Agent Loop

| Endpoint | Status |
|----------|--------|
| `POST /api/behavior/event` (store_id, event_type, product_id, session_id) | ✅ `POST /api/behavior/event/{slug}` |
| `GET /api/agent/actions/{store_id}/pending` | ✅ `GET /api/agent/actions/{slug}/pending` |
| `POST /api/agent/actions/{action_id}/approve` | ✅ Executes payload + broadcasts `STATE_UPDATED` |
| `POST /api/agent/actions/{action_id}/dismiss` | ✅ |

#### Attribution Dashboard

| Endpoint | Status |
|----------|--------|
| `GET /api/dashboard/{store_id}` → total_gmv, attributed_gmv, fee, actions[] | ✅ `GET /api/dashboard/{slug}` — 10% fee, promo attribution |
| 72-hour attribution window | ⚠️ Not implemented — we attribute by `promo_applied` field match only, no time window |

#### WebSocket

| Event | Status |
|-------|--------|
| `agent_action` — new pending action | ✅ |
| `store_update` / `state_updated` — post-approve | ✅ |
| `behavior_pulse` — live session count + event feed | ❌ Not implemented |

---

### §6–7 — Frontend Components

| Component | Spec | Status |
|-----------|------|--------|
| `StoreShell.tsx` | CSS var injection from brand_tokens | ✅ `components/store/StoreShell.tsx` — `resolveTheme()` |
| `HeroSection.tsx` | 4 variants: full-bleed / text-forward / split / texture-bg | ✅ Built in Task 4 |
| `ProductGrid.tsx` | 3 variants: 2col-featured / 3col-equal / masonry | ✅ Built in Task 4 |
| `ProductCard.tsx` | 4 variants: borderless / outlined / elevated / colored-bg | ✅ Built in Task 4 |
| `CategoryNav.tsx` | 3 variants: pill / underline-tab / minimal-text | ✅ Built in Task 4 |
| `MerchantTerminal.tsx` | Right panel with WS, action cards, dashboard | ✅ `app/terminal/page.tsx` + components |
| `ActionCard.tsx` (OptionCard) | Trigger label, title, GMV, confidence bar, brand check, Approve/Dismiss | ✅ `OptionCard.tsx` — full spec including water-like animation |
| `BehaviorPulse.tsx` | Live session count + event feed | ❌ Not built |
| `AttributionDashboard.tsx` | GMV metrics, fee, action log | ✅ Built in Task 5 |
| `LogoUpload.tsx` | Logo drag-and-drop → OSS | ✅ Sprint 1 |
| `StoreBirth.tsx` | 30-second SSE progress animation | ❌ Sprint 1 has incubation loading screen; the step-by-step SSE reveal is **not built** |

---

### §8 — Zustand Store

| Field | Status |
|-------|--------|
| store, brandTokens, products | ✅ |
| pendingActions, wsConnected | ✅ |
| activeLayout, morphLayout() | ⚠️ Layout is derived from brand_token in render — not stored in Zustand |
| behaviorMetrics, updateBehaviorMetrics() | ❌ Not in Zustand (behavior is backend-only) |
| resolveAction() | ✅ Handled via API calls in terminal |

---

### §9 — Store Birth UX (0→60s SSE sequence) — ❌ NOT BUILT

This is the **biggest gap** between the spec and what exists.

**Spec wants:**
- SSE stream from `POST /api/stores/create`
- Step-by-step progress events: color swatches appear one by one, font names appear, layout style named, seed products populate with skeletons, BrandGuardRules as bullet list
- `StoreBirth.tsx` component consuming the SSE stream with Framer Motion per step
- Full 30-second branded reveal

**What exists:**
- Sprint 1: incubation loading screen with ambient orb + cycling text ("Analyzing geometry...", "Extracting palette...", etc.)
- WS `brand_ready` event fires when done — frontend jumps from loading to complete brand reveal
- **No step-by-step progressive reveal** — it's binary (loading → done)

**Demo impact:** The demo script at `[0:20–1:10]` shows two stores being born with a 30-second reveal each. The current UX does not match this. It works — but it's not the cinematic moment the spec describes.

---

### §10 — Behavior Simulation — ✅ Done

- `POST /api/behavior/simulate/{slug}` fires 10-event script with 5 abandons
- Frontend "Simulate Activity" button in StoreSnapshot: idle → sending → done states
- Triggers anomaly → Qwen decision cycle → action card appears in ~10s

---

### §12 — Alibaba Cloud Deployment

| Item | Status |
|------|--------|
| Dockerfile | ✅ Exists (Sprint 1) |
| `s.yaml` (Serverless Devs config) | ✅ Scaffolded (Sprint 1) |
| OSS bucket + logo upload live | ✅ STS presigned upload working |
| FC deployed + running | ⚠️ Unknown — not verified this session |
| GitHub Actions CI/CD pipeline | ❌ Not built |
| `oss2` SDK call visible in Python | ❌ Not present — STS approach bypasses this |
| Proof-of-deployment screen recording | ❌ Not done |

---

## Remaining Work for Submission

Ordered by demo impact:

### P0 — Breaks the demo
*(None — the full demo loop works: logo → brand → simulate → action card → approve → dashboard)*

### P1 — Visible gap in demo video
1. **StoreBirth SSE sequence** — the 30-second branded reveal. Currently it's a binary loading → done. Judges will see the dramatic reveal in the demo script but our version is an ambient loader. This is the #1 visual gap.
2. **`oss2` SDK call** — hackathon requires visible Alibaba Cloud SDK usage. STS tokens are indirect. Adding a single `oss2.Auth` call anywhere in the Python codebase (even a presigned URL generation) satisfies this.

### P2 — Submission checklist gaps
3. **BehaviorPulse** — live session count in the terminal. Not required for the demo to work, but mentioned in the terminal spec.
4. **Architecture diagram** — required for submission (can be drawn in Excalidraw, 30 min).
5. **Proof-of-deployment screen recording** — required for judges.
6. **Demo video** — 3-minute recording of the full loop.
7. **Devpost submission** — text + links.

### P3 — Nice-to-have
8. 72-hour attribution window in dashboard query.
9. `morphLayout()` in Zustand (currently layout is render-time only).
10. GitHub Actions CI/CD.
