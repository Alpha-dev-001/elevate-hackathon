# Elevate — autonomous autopilot for running a store

> An autonomous operator for an online store — the way AI agents changed how
> software gets written, brought to commerce. Qwen doesn't assist the merchant —
> it **runs the store**:
> reasoning over every signal the store produces, proposing and executing
> changes behind a safety layer it cannot override, and getting better at
> growing *that specific store* over time.
>
> The codebase is the body. **Qwen is the brain.**

[License: MIT](./LICENSE) · [Built with Qwen](https://qwencloud.com) · [Alibaba Cloud](https://alibabacloud.com)

**A swarm of 4 role-scoped Qwen specialists (extensible — not fixed at four) · 2 models (incl. multimodal) · 10 typed tools · a Layer-0 structural guard + 3-layer interceptor + tamper-evident decision ledger · reactive *and* proactive triggers · per-store learning · 540+ backend tests across 87 test files · live Qwen benchmark: 100% valid, 5.6s avg**

<!-- TODO(hero): 1280×640 — merchant terminal mid-decision, an option card visible + Decision Trace panel open. See docs/IMAGE_GALLERY.md #01 -->
![Elevate — autonomous autopilot for running a store](docs/images/01-hero.png)

**▶ [3-minute demo video](TODO_DEMO_VIDEO_URL)**  ·  **🌐 [Live backend](http://47.243.86.14/api/health)** (on Alibaba Cloud ECS)  ·  **🖼 [More screenshots](docs/images/)**

---

## The one result that explains the whole architecture

Same `qwen-max` model. Same seven scenarios — each with genuinely different
cost, price, margin floor, and discount ceiling. We ran it two ways: **bare**
(the raw model proposal, nothing between it and execution) and **through
Elevate's pipeline** (role-scoped tool call → structural guard → interceptor).

> **The bare model proposed the *identical* flat `10%` discount on all seven.**
> The exact same model, run through Elevate, reasoned each one to a different,
> provably-safe value: **2.89%, 40.0%, 11.11%, 10.0%, 10.0%, 15.0%**, and "no
> discount dimension" for a catalog-merge control.

An unguarded LLM doesn't reason about the cost in front of it — it reaches for
a safe-sounding round number and calls it a day. *The architecture is what
makes Qwen actually reason.* Real API calls, reproducible:
`python -m tests.bench_live` — full breakdown in [BENCHMARKS.md](./BENCHMARKS.md).

This is the thesis of the whole project: **the intelligence isn't the model,
it's the model wired into a system that forces it to be right.**

---

## How it actually works

Elevate is not "one model with a system prompt." It's a small operations team
of role-scoped Qwen specialists, each gated by an immutable safety stack, fed
by two equally-first-class trigger sources:

```
Customer event (WebSocket) ─┐                         reactive
                            ├─► signal ─► ROLE ROUTER ─► Qwen specialist (role-scoped tools only)
Scheduled tick (proactive) ─┘   │                              │
   pricing · scarcity · catalog │                              │ proposes ONE typed tool call
   health, checked on a cadence │                              ▼
                                │                    ┌─ LAYER 0 · Structural guard ─┐  illegal state?
                                │                    │  (discount∈[0,100], price>0,  │  → declined, never
                                │                    │   real target, closed enums)  │     becomes an action
                                │                    └───────────────┬───────────────┘
                                │                                    ▼
                                │                    ┌─ 3-LAYER INTERCEPTOR (immutable) ─┐
                                │                    │  1 Brand guard (Qwen-authored)     │
                                │                    │  2 Business constraints → clamp    │
                                │                    │  3 System safety → hard block      │
                                │                    └───────────────┬────────────────────┘
                                │                                    ▼
                                │                   TRUST GATE — earned + merchant opted in?
                                │                        ┌───────────┴───────────┐
                                │                 human-in-the-loop        auto-apply (bounded,
                                │                 option card, merchant     already-safe moves,
                                │                 approves / rejects        merchant's own toggle)
                                │                        └───────────┬───────────┘
                                ▼                                    ▼
                        DECISION LEDGER  ◄──── every status change ──► EXECUTE → storefront morphs
                    (hash-chained, HMAC, Postgres)                        │
                                ▲                                         ▼
                                └──────────── LEARN ◄──── outcome + merchant verdict
                                        per-role stance shifts the next proposal
```

Every arrow in that diagram is real, tested code — not a roadmap.

<!-- TODO(diagram): rendered version of the pipeline above (Mermaid export or designed graphic), 1600px wide. See docs/IMAGE_GALLERY.md #02 -->
![The Elevate decision pipeline — signal to ledger to learning](docs/images/02-pipeline.png)

---

## The swarm — four role-scoped specialists (not fixed at four)

Instead of one generalist prompt holding all nine tools, each trigger routes to
a **named role that owns a disjoint subset of tools and cannot call outside it.**
A hallucinated cross-domain action isn't caught after the fact — the tool
literally isn't on the model's menu for that role.

| Role | Owns | Tools (and *only* these) |
| --- | --- | --- |
| **Pricing Strategist** | live pricing, flash sales, scarcity | `flash_sale`, `scarcity_price`, `price_rebalance` |
| **Sales Rep** | cart recovery, dwell nudges, new-arrival spotlight | `recovery_offer`, `cart_dwell_nudge`, `feature_product` |
| **Store Curator** | layout + copy presentation | `layout_morph`, `copy_rewrite` |
| **Inventory Overseer** | catalog hygiene | `duplicate_merge` |

Two behaviors make this a *team*, not four isolated prompts:

- **Escalation.** A role can hand a decision to another specialist when the real
  fix is outside its own tools — the Store Curator, seeing a product with real
  interest but no conversions, can escalate to the Pricing Strategist via a typed
  `escalate_to_role` tool instead of forcing a layout change that won't help.
- **Priority arbitration tuned by learning.** Each role has a base priority;
  this store's own approval history nudges it up or down (a role the merchant
  keeps agreeing with gets a louder voice), so competing signals resolve the way
  *this* merchant has taught the system to resolve them.

Same one Qwen call per triggered event either way — the scoping adds structure,
not tokens.

---

## Why a broken (or hallucinating) model cannot break the store

Three independent layers stand between any proposal and the live store. **Qwen
authored parts of this layer, but it can never override it.**

1. **Layer 0 — Structural guard.** Every tool call is parsed through a
   constrained Pydantic model *before* it can become an action: discount ∈
   [0, 100], price > 0, duration > 0, targets that must resolve to a real
   product, closed enums for copy targets. An illegal value is *unrepresentable*
   — it declines the cycle instead of being caught downstream.
2. **The 3-layer interceptor (immutable).** Brand guard (fires Qwen's own
   brand-consistency warnings) → business constraints (auto-**clamps** an
   over-aggressive discount to the merchant's ceiling) → system safety
   (**hard-blocks** below-cost, negative-stock, expired-promo moves, no
   exceptions).
3. **Decision Ledger.** Every lifecycle transition — proposed, blocked,
   approved, executed, dismissed — is written to a hash-chained, HMAC-signed
   Postgres log that attests to the action row's *real current values*, so a
   later check detects tampering, reordering, or a quietly-edited history.
   Verify offline: `python scripts/verify_ledger.py <store>`.

Structural safety **and** runtime safety **and** an audit trail — belt,
suspenders, and a receipt.

---

## The store learns — something a stateless agent structurally cannot do

After an action resolves, the outcome and the merchant's verdict feed the next
decision. Beyond remembering *what happened*, Elevate quantifies *what to do
differently*: for each role it aggregates how this merchant has resolved that
role's past proposals — kept vs dismissed, and the discount level kept vs
rejected — into a directive injected into the role's next prompt:

> *"Learned for this store: the merchant kept 2 of 6 recent Pricing Strategist
> proposals. Kept offers averaged 9% off vs 35% for dismissed ones — lead with
> about 9%."*

Proposals measurably converge on what *this* store accepts. The stance is stored
on each decision's context snapshot and shown on the **Decision Trace** page, so
the learning is visible, not a claim. It rides the existing decision call — zero
extra tokens — and stays silent until there's enough history to be honest.

---

## Human-in-the-loop is the architecture, not a button

Track 4 asks for agents that *"automate real-world business workflows end-to-end
with human-in-the-loop checkpoints at critical decisions."* In Elevate the option
card **is** that checkpoint — it's the only path a gated decision can take to
reach the live storefront. The merchant approves or rejects, and **both outcomes
are written to the ledger and the learning loop.** Trust is *earned per
(store, product)*, but earning it only unlocks the option — small,
already-interceptor-safe pricing moves can auto-apply once trust is earned
*and* the merchant has explicitly opted that product into it, one toggle at
a time, reversible any time. Trust only ever removes the gate — it never
widens the safe range — and a single dismissal resets the streak. Full
autonomy everywhere would score *worse* on this track, and the design
reflects that on purpose: the merchant decides when Qwen gets to skip the
checkpoint, not just how good Qwen's track record has been.

| Judging criterion | Weight | Where Elevate proves it |
| --- | --- | --- |
| Technical Depth & Engineering | 30% | 4 role-scoped agents with disjoint tools + escalation + learned arbitration · Layer-0 guard + 3-layer interceptor + hash-chained ledger · 2 models, 7 distinct Qwen call types, native tool-calling · concurrency-safe checkout + self-healing state · Redis + Postgres · 500+ tests |
| Innovation & AI Creativity | 30% | A self-governing *swarm* of role-scoped Qwen agents: roles that can't exceed their tools, escalate to each other, and adapt priority + proposals from per-store learning — extensible beyond the four shown — plus an MCP server exposing the store to external agents |
| Problem Value & Impact | 25% | A real store runs and improves itself without the merchant hiring a CRO agency — reactive to live behavior, proactive on pricing/scarcity/catalog health |
| Presentation & Documentation | 15% | [Architecture](./docs/ARCHITECTURE.md) · [Technical deep dive](./docs/TECHNICAL-DEEP-DIVE.md) · [Benchmarks](./BENCHMARKS.md) · [Testing](./docs/TESTING.md) |

---

## Reactive *and* proactive — both first-class

A signal is a signal regardless of source. Elevate acts on what's happening
*right now* and initiates on its own without waiting for an event:

- **Reactive** — a velocity spike, a cart abandoning, a cart dwelling untouched,
  a catalog anomaly. Customer DOM events (`view`, `hover`, `cart_add`,
  `purchase`, `abandon`) stream over WebSocket → Redis velocity tracking →
  threshold crossing → the right role's decision cycle.
- **Proactive** — pricing reasoned on a cadence against each product's baseline,
  a scarcity check on low-stock high-demand items, catalog health / duplicate
  scans — caught before a merchant would ever notice, folded into a per-store
  tick.

---

## The spice on top: Qwen builds the store it then runs

The autopilot is the product. But the same brain also *builds* the storefront
it operates — which is what makes every decision above land somewhere real and
visibly distinct, not on a Shopify theme:

```
Logo → qwen-vl-max reads geometry, palette, mood
     → qwen-max generates the brand: palette, voice, SVG icons, and the guard
       rules it will later be held to (the AI literally cannot violate the brand
       it authored — those rules are enforced by deterministic Python)
     → a LayoutDSL composes a genuinely distinct store (not a template swap) —
       no two brands get the same store
     → merchant drops a folder of raw phone photos → qwen-vl-max reads each into a
       structured product: a sellable name from what it can see, a description in
       the store's brand voice, category, the colorways/variants in the shot, and a
       price anchored to the merchant's baseline (never a scraped MSRP) — and it
       flags low-confidence reads for review instead of guessing wrong
     → a client-side perceptual hash (aHash, ~2ms/image) dedups near-identical
       shots into one product before a single token is spent
     → store goes live → the autopilot above takes over
```

That product-vision call is itself a sophisticated use of Qwen: one photo in,
a full catalog entry out — *naming, describing, categorizing, and variant-detecting*
from pixels, while knowing what **not** to guess (it won't invent a resale price it
can't see). The adversarial vision suite proves it stays graceful on the messy real
world too — a selfie, a blank image, a garbage price all degrade to "needs review,"
never a silent wrong product going live.

Seven distinct Qwen jobs power this (logo analysis · brand generation · LayoutDSL
composition · scoped CSS · product vision · batched descriptions · decision
cycles) — two models, never seven calls to the same prompt. If a Qwen call fails
entirely, variant coercion → structural normalization → a brand-seeded
deterministic fallback still yield a renderable, on-brand store. The customer
never sees a blank page.

---

## What Elevate is NOT (to prevent common misreads)

- **No video.** "Vision" = `qwen-vl-max` on still uploaded images. Customer
  behavior = discrete WebSocket DOM events, not camera feeds or video frames.
- **No template store.** Every store's layout is composed per brand, not themed —
  no two stores are the same.
- **It *is* multi-merchant — and multi-account.** Per-merchant auth (JWT in an
  httpOnly cookie + bcrypt), every table scoped to `merchant_id`, Redis keys
  namespaced per merchant. Storefronts also have real **per-brand shopper accounts**
  (the same email at two stores = two separate accounts) alongside the guest cart.
- **Honest hackathon scope** — no payment processing, no order fulfillment, and
  product variants are *detected* (a red vs. blue listing won't be wrongly merged)
  but not yet selectable on the storefront. It proves the autopilot end-to-end:
  a real merchant uploads a real logo and gets a real store that runs itself.

---

## Stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 15, TypeScript, Tailwind, Framer Motion, Zustand |
| Backend | FastAPI, Python 3.11, Pydantic v2, SQLAlchemy (async) |
| AI | **qwen-vl-max** (vision) + **qwen-max** (text / decisions), OpenAI-compatible tool-calling |
| Real-time | WebSocket (full-duplex, event-driven, zero polling) |
| Database | PostgreSQL (Alibaba Cloud RDS) — persistent source of truth |
| Cache | Redis (Alibaba Cloud Tair) — telemetry, sessions, velocity, pending actions |
| Storage | Alibaba Cloud OSS — logos & product images (presigned PUT, never through the backend) |
| Deploy | Alibaba Cloud (backend live on ECS) + Docker Compose (local) |
| Agents | MCP server (FastMCP) exposing the store to external agents |

**Proof of deployment** — the backend runs on Alibaba Cloud ECS (Hong Kong), and the health endpoint answers live:

![Elevate backend running on Alibaba Cloud ECS, health check returning ok](docs/images/15-alibaba-deploy.png)

```
elevate/
├── storefront-ui/          # Next.js 15 frontend
│   ├── app/                # onboarding · terminal (decisions, attribution) · builder · s/[slug] storefront
│   ├── components/         # 80+ React components
│   └── lib/                # ws.ts · store.ts (Zustand) · fingerprint.ts (perceptual dedup)
└── analytics-brain/        # FastAPI backend
    └── app/
        ├── models/         # Pydantic schemas (source of truth) + DB models
        ├── routers/        # products · onboarding · agent · behavior · …
        └── services/       # decision_engine · qwen_roles · action_guard · interceptor ·
                            #  learning · autopilot_trust · receipts (ledger) · pricing · mcp_server · …
```

---

## Deep dives

The README keeps the pitch tight. Everything goes deeper in dedicated docs.

| Topic | Where |
| --- | --- |
| **How it works** — interceptor, guard, roles, learning, MCP, telemetry, token efficiency | [docs/TECHNICAL-DEEP-DIVE.md](./docs/TECHNICAL-DEEP-DIVE.md) |
| **Live Qwen benchmarks** — real API, latency + validity, guarded-vs-bare ablation | [BENCHMARKS.md](./BENCHMARKS.md) |
| **Architecture diagrams** — Mermaid flowcharts, data flow | [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) |
| **Testing** — 115 test files (87 backend, 28 frontend), adversarial suites, benchmarks | [docs/TESTING.md](./docs/TESTING.md) |
| **Qwen model usage** — which models, which jobs, token costs | [QWEN_USAGE.md](./QWEN_USAGE.md) |

---

## Getting started

```bash
git clone https://github.com/Alpha-dev-001/elevate-hackathon
cd elevate

# Backend
cd analytics-brain
cp .env.example .env      # Qwen API key, OSS credentials, DB URL
pip install -r requirements.txt
uvicorn app.main:app --port 9000

# Frontend (separate terminal)
cd ../storefront-ui
cp .env.example .env.local
npm install && npm run dev
```

Open `http://localhost:3000/setup` to start onboarding.

```bash
# Qwen Cloud
QWEN_API_KEY=sk-...
QWEN_VL_MODEL=qwen-vl-max
QWEN_TEXT_MODEL=qwen-max
# Alibaba Cloud OSS
OSS_REGION=cn-hongkong
OSS_ACCESS_KEY_ID=...
OSS_ACCESS_KEY_SECRET=...
OSS_BUCKET=elevate-assets
# Data
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/elevate
REDIS_URL=redis://localhost:6379
```

---

## Hackathon

Built for the **Global AI Hackathon Series with Qwen Cloud** — **Track 4:
Autopilot Agent**. Blog:
[Elevate: Making Qwen the Brain of a Store That Runs Itself](https://dev.to/alpha-dev-001/elevate-making-qwen-the-brain-of-a-store-that-runs-itself-582p)

## License

MIT — see [LICENSE](./LICENSE)
