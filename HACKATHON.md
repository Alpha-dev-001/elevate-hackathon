# Elevate — Hackathon Build Guide

> **Deadline:** July 9, 2026 @ 2:00pm PDT
> **Track:** Track 4 — Autopilot Agent (primary) / Track 1 — MemoryAgent (crossover)
> **Prize:** $7,000 cash + $3,000 cloud credits per track winner

---

## The One-Line Pitch

Elevate is the AI that runs your store while you sleep — not by chatting with you, but by acting.

---

## What We Are Actually Building

A monorepo with two completely separated applications:

- `storefront-ui/` — Next.js 15 frontend: merchant terminal, live storefront, onboarding flow
- `analytics-brain/` — FastAPI backend: Qwen orchestration, WebSocket pipeline,
  telemetry, delta execution, brand generation

Qwen is not a chatbot here. It builds the store from a logo, authors its own
brand defense rules, and runs the store autonomously via real-time telemetry.
The code is the body. Qwen is the brain.

---

## The Core Demo Loop (3 Minutes — Build Everything to Serve This)

```
0:00 — Merchant signs up, uploads a logo
0:30 — Qwen analyzes it, generates full brand — store shell appears live
1:00 — Merchant tries to change accent color →
        brand warning fires in Qwen's own words about this specific logo
1:20 — Merchant adds 3 products — Qwen writes descriptions instantly
1:40 — Store goes live — customer session begins on split screen
2:00 — Products viewed rapidly — velocity spike detected
2:15 — Qwen fires decision cycle — option cards surface in terminal
2:30 — Merchant taps Approve — storefront morphs with fluid transition
2:45 — QR code generated — scan triggers promo on product page
3:00 — Done
```

If this loop works end-to-end and looks clean, we win.

---

## The Six Systems (Milestone Checklist)

### 0. Onboarding — The Store Comes Alive
- [ ] Merchant auth (simple JWT)
- [ ] Logo upload → Alibaba Cloud OSS
- [ ] Qwen-VL multimodal logo analysis → LogoAnalysis model
- [ ] Qwen-Max brand generation → GeneratedBrand + BrandGuardRules
- [ ] Brand preview renders live store shell from brand data
- [ ] BrandWarning fires in real time as merchant tweaks brand settings
- [ ] Product management (add, edit, bulk CSV upload)
- [ ] Qwen product description generation (batched — one call for all products)
- [ ] Store publish → SystemState initialized → goes live

### 1. Telemetry Snapshot Layer
- [ ] `recordEvent()` ingests customer events from storefront via WebSocket
- [ ] `captureSnapshot()` aggregates velocity, session count, abandon rate
- [ ] Anomaly detection flags velocity spikes and dead products
- [ ] Snapshot cached in Redis with 5-minute TTL
- [ ] No polling — pure event pipeline

### 2. Merchant Terminal (Option-Driven Interface)
- [ ] Option cards rendered per proposed Qwen action
- [ ] Each card shows: label, description, estimated impact, risk level
- [ ] Approve / Reject / Stage Preview per card
- [ ] Staging sandbox shows live diff before committing
- [ ] No long-form chat anywhere in the UI
- [ ] Fluid Framer Motion transitions on all Qwen-driven elements

### 3. Subconscious Interceptor (Three Layers)
- [ ] Layer 1: BrandGuardRules — Qwen's own authored defense, fires Qwen's warnings
- [ ] Layer 2: BusinessProfile constraints — margin floor, discount ceiling, auto-clamp
- [ ] Layer 3: System safety — hard block on price below cost, stock below zero
- [ ] All violations surfaced visually on option cards with specific messaging

### 4. Delta Execution Engine
- [ ] `execute_delta()` applies JSON patches via jsonpatch (Python backend)
- [ ] State versioned and persisted to Redis
- [ ] `stage_preview()` runs patches in memory without persisting
- [ ] `rollback_last()` restores previous state in one call
- [ ] Audit log of all deltas (last 100) in Redis
- [ ] WebSocket pushes new state to ALL connected surfaces immediately

### 5. Physical Bridge (QR Campaigns)
- [ ] `POST /api/qr/generate` creates campaign-aware QR codes
- [ ] Deep link encodes merchantId, productId, promoId
- [ ] `GET /api/qr/scan` records scan count, returns active promo
- [ ] QR updates dynamically when promo changes
- [ ] Scan data flows back into telemetry

---

## Stack Reference

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, TypeScript, Tailwind, Framer Motion, Zustand, Zod |
| Backend | FastAPI, Python 3.10, Pydantic v2, async Redis, httpx |
| AI — Logo + Brand | qwen3.5-plus (multimodal, one call handles both) |
| AI — Decision cycles | qwen3-max (agent pipeline, structured JSON) |
| AI — Product descriptions | qwen-plus (batched, cost efficient) |
| AI — Sprint 4 visualization | qwen3-max-thinking (generates visual output) |
| Infrastructure | Alibaba Cloud Function Compute (FC3) |
| State / Telemetry | Alibaba Cloud Redis (Tair) |
| Asset Storage | Alibaba Cloud OSS |
| Delta Engine | jsonpatch (Python) |
| QR Generation | qrcode (Python) |
| Deploy | Serverless Devs (s.yaml) |

---

## Build Order (Sprint by Sprint)

### Sprint 1 — The Store Comes Alive
- [ ] Repo pushed to GitHub (public, MIT license)
- [ ] Qwen Cloud credits activated
- [ ] Alibaba Cloud free trial active
- [ ] Deploy hello world to Function Compute (get proof screenshot EARLY)
- [ ] Redis + PostgreSQL running on Alibaba Cloud
- [ ] Provisioned concurrency set on FC (keep warm — no cold start in demo)
- [ ] All env vars filled
- [ ] qwen-vl-max tested — multimodal logo call confirmed working
- [ ] Full onboarding flow: logo → brand → products → live
- [ ] BrandGuardRules includes pre-built allowed_color_palette + brand_voice_profile
- [ ] Storefront mobile responsive
Note: BrandWarning reflex is Sprint 2, not Sprint 1

### Sprint 2 — The Store Has a Life
- [ ] Full product CRUD + image uploads
- [ ] Cart (session-based, Redis)
- [ ] Basic order flow
- [ ] Promo engine foundations
- [ ] Storefront pages complete (listing, detail, search)
- [ ] Design Sprint 2 properly before building — see SPRINTS.md

### Sprint 3 — Qwen Takes the Wheel
- [ ] Telemetry WebSocket pipeline live
- [ ] Qwen decision cycles firing from anomalies
- [ ] Option card terminal UI complete
- [ ] Delta execution + storefront hot-reload (fluid transitions)
- [ ] QR campaign bridge
- [ ] QwenMerchantModel self-modification layer begins
- [ ] Design Sprint 3 properly before building — see SPRINTS.md

### Sprint 4 — Polish + Submission
- [ ] Architecture diagram
- [ ] 3-minute demo video (YouTube/Vimeo, public)
- [ ] README finalized
- [ ] Blog post written (DEVLOG.md is the source — $500 prize)
- [ ] Alibaba Cloud deployment proof recording
- [ ] Devpost finalized before July 9 @ 2:00pm PDT
- [ ] Design Sprint 4 properly before building — see SPRINTS.md

---

## Submission Checklist (July 9 @ 2:00pm PDT)

- [ ] Public GitHub repo with MIT LICENSE
- [ ] Screen recording proving backend on Alibaba Cloud
- [ ] Architecture diagram in repo
- [ ] 3-minute demo video on YouTube or Vimeo (public)
- [ ] Text description on Devpost (use HACKATHON_STORY.md)
- [ ] Track 4: Autopilot Agent selected
- [ ] Blog post URL (DEVLOG.md → blog post = $500 prize)

---

## Judging Criteria

| Criteria | Weight | Our Angle |
|----------|--------|-----------|
| Technical Depth & Engineering | 30% | Qwen as runtime engine, multimodal brand generation, three-layer interceptor, WebSocket pipeline |
| Innovation & AI Creativity | 30% | BrandGuardRules (Qwen defends what it built), option-driven interface, self-modification layer |
| Problem Value & Impact | 25% | Real merchant pain, production-ready architecture, clear startup path |
| Presentation & Documentation | 15% | Clean demo loop, architecture diagram, DEVLOG blog post |

---

## What "Production-Ready" Means Here

- Real error handling (not just happy path)
- Actual Alibaba Cloud deployment (not localhost screenshots)
- Business constraints enforced (interceptor must actually work)
- Rollback capability (merchants need an undo)
- Auth in place (JWT — Sprint 1)
- The demo does not crash

It does not mean billing, advanced multi-tenancy, or a full product suite.
That is in PRODUCT.md.
