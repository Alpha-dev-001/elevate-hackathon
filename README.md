# Elevate — Your store, alive.

> AI-native commerce where Qwen is not a feature — it is the runtime.
> Upload a logo. Qwen builds the brand, runs the store, and learns
> from every decision.

[License: MIT](./LICENSE)
·
[Built with Qwen](https://qwencloud.com)
·
[Alibaba Cloud](https://alibabacloud.com)

**157 tests passing · 62 adversarial edge cases · 7 distinct Qwen call types (vision, tool-calling, brand gen, DSL composition, CSS, descriptions, decisions) · MCP server exposing the store to external agents**

**Live Qwen benchmark (real API, not mocked): 100% valid rate across all 5 call types, avg 5.6s latency, 5/5 scenarios rated "good".** Reproduce it yourself: `docker compose exec api python -m tests.bench_live` — full breakdown in [BENCHMARKS.md](./BENCHMARKS.md).

---

## At a glance

**1. Qwen authors its own constraints.**
At brand generation time, Qwen writes the guard rules that govern its
future behavior — color conflicts, layout coherence, voice consistency.
These rules are enforced by deterministic Python (Pydantic + Zod +
3-layer interceptor), not by prompting. The AI literally cannot violate
the brand it created.

**2. The store runs itself in real-time.**
Customer browser events (click, hover, cart_add) flow through WebSocket
→ Redis velocity tracking → anomaly detection → qwen-max decision cycle
→ option card in the merchant terminal → approve → storefront morphs.
The trigger is deterministic by design — a configurable velocity
threshold. The autonomy is in the response: Qwen reasons about which
product, what action, what discount, in what words — informed by every
prior approval and rejection.

**3. A broken AI response cannot produce a broken store.**
Three defense layers guarantee a renderable, on-brand storefront
regardless of what Qwen returns: variant coercion, structural
normalization, and deterministic fallback. If the Qwen call fails
entirely, a brand-seeded hash generates a distinct layout.
The customer never sees a blank page.

### What Qwen actually does here vs. a typical AI integration

| What most "AI-powered" apps do | What Elevate does |
| --- | --- |
| Qwen answers questions in a chat box | Qwen builds the entire store from a logo |
| One model, one job (text in → text out) | Two models, **7+ distinct call types** (vision, tool-calling, brand gen, DSL composition, CSS, descriptions, decisions) |
| AI suggests, human implements manually | AI proposes → human approves → **store morphs live** |
| Generic safety rules written by developers | **Qwen authors its own guard rules** at brand creation — enforced by deterministic Python |
| No memory between sessions | Every merchant correction + outcome feeds the **next decision cycle** |
| JSON output parsed with regex | **Native tool-calling API** — Qwen selects which tool, fills typed parameters |

---

## Why this hits Track 4's mandate

Track 4 asks for agents that "**automate real-world business workflows
end-to-end with human-in-the-loop checkpoints at critical decisions.**"
Here's the feature-to-criterion map, not just a claim:

| Judging criterion | Weight | Where Elevate proves it |
| --- | --- | --- |
| Technical Depth & Engineering | 30% | 2 models, **7 distinct Qwen call types**, native tool-calling (6 typed tools), 3-layer interceptor, Redis + Postgres two-layer state, 157 tests |
| Innovation & AI Creativity | 30% | Qwen authors its own brand guard rules at creation time — not developer-written safety rules. LayoutDSL gives every store a genuinely distinct layout, not a template swap |
| Problem Value & Impact | 25% | Every independent brand deserves a store that looks like *them*, not a Shopify theme — and the store improves itself without a merchant hiring a CRO agency |
| Presentation & Documentation | 15% | Architecture diagram ([docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)), full test suite ([docs/TESTING.md](./docs/TESTING.md)), technical deep dive ([docs/TECHNICAL-DEEP-DIVE.md](./docs/TECHNICAL-DEEP-DIVE.md)) |

The human-in-the-loop checkpoint isn't a button that exists for show — it's
the only path a decision can take to reach the live storefront. Qwen
proposes, the interceptor validates, the merchant approves or rejects, and
**both outcomes are written back into memory** and read by the next
decision cycle. See [Qwen Memory](./docs/TECHNICAL-DEEP-DIVE.md#decision-memory--not-fine-tuning-by-design).

---

## A real decision cycle, not a mockup

This is the actual output of `narrative_from_tool()` — the function that
turns a Qwen tool call into what the merchant sees on an option card.
Verified by `test_tools.py::test_flash_sale_narrative`, not written for
this README:

```
Input (from a real velocity-spike anomaly):
  tool:          propose_flash_sale
  args:          { discount_percent: 15, duration_minutes: 1440 }
  product:       "Leather Slides"
  anomaly:       "Velocity spike: 12 views in 30s"
  brand_voice:   "warm and confident"

Output (rendered on the option card):
  title:         "Flash Sale: 15% off Leather Slides"
  description:   "24.0-hour flash sale to capture velocity spike"
  trigger:       "Velocity spike: 12 views in 30s"
  brand_check:   "Aligned with warm and confident voice"
```

Qwen chose the tool, the discount, and the duration from the anomaly and
the store's live state (`reasoning` is stored verbatim alongside this and
shown on demand in the terminal) — `narrative_from_tool()` is the
deterministic formatting layer downstream of that decision, so the option
card text is always well-formed even if Qwen's free-text reasoning is not.

---

## Demo

> **[Demo video]** — *[link coming — recording in progress]*
>
> **[Live instance]** — *[link coming — deploying to Alibaba Cloud FC]*

### What happens in the 3-minute demo

```
0:00  Merchant uploads a logo
0:15  Qwen analyzes it, generates full brand — store shell appears live
0:40  Merchant drops product photos — Qwen reads every one
1:20  Store goes live — customer session begins
2:00  Velocity spike detected — Qwen fires decision cycle
2:20  Merchant taps Approve — storefront morphs instantly
2:40  Outcome measured — Qwen learns from the result
3:00  Done
```

---

## What makes Elevate different

Most AI commerce tools bolt a chatbot onto a Shopify clone. You ask
questions, get answers, then go do the work yourself.

Elevate is the opposite. Qwen builds the store from a single logo
upload, defines the brand rules, catalogs products from photos,
watches customer behavior in real-time, and surfaces decisions as
option cards — not chat. The merchant stays in control. Qwen does
the work.

```
Logo → qwen-vl-max reads it
     → qwen-max generates brand (palette, voice, guard rules, layout)
     → Store shell appears live
     → Merchant drops product photos
     → qwen-vl-max identifies each (Vision Fingerprinting deduplicates)
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

To prevent common misreads:

- **No video processing.** Customer behavior = discrete WebSocket DOM
  events (`view`, `hover`, `cart_add`, `purchase`, `abandon`) — not
  video frames, not camera feeds.
- **No physical stores.** Pure online commerce. Browser only.
- **"Vision" = static image analysis.** `qwen-vl-max` analyzes uploaded
  product photos — still images, not live video.

**What this doesn't do yet** (honest scope — it's a hackathon, not a product):
no payment processing, no multi-tenant isolation, no production-grade RBAC,
no order fulfillment. It proves the autopilot concept end-to-end — a real
merchant uploading a real logo gets a real store that runs itself. That's
the thesis, and it works.

---

## Two-Model Architecture

Two Qwen models. Each chosen for what it does best. No routing complexity.

| Task                                      | Model           | Why                                                        |
| ----------------------------------------- | --------------- | ---------------------------------------------------------- |
| Logo analysis + product identification    | **qwen-vl-max** | Multimodal — reads images, identifies products from photos |
| Brand generation, descriptions, decisions | **qwen-max**    | Best quality text, structured JSON output                  |

**Every Qwen call in the system — 7 distinct jobs, not 7 calls to the same prompt:**

1. **Logo analysis** (VL) — geometry, palette, mood from one image
2. **Brand generation** — palette, typography, voice, guard rules, SVG icons
3. **Layout DSL composition** — section order, variants, nav style
4. **Custom CSS** — scoped micro-interactions (sanitized before storage)
5. **Product vision** (VL) — identify + describe from photo, price anchored
6. **Batched descriptions** — 20 products per call, parallelized chunks
7. **Decision cycles** — native tool-calling (6 typed tools), memory-informed

**Vision Fingerprinting** — before any image reaches Qwen, a perceptual
hash (aHash, 64-bit) runs client-side in `fingerprint.ts`. Near-duplicate
photos collapse into one product with multiple images. Hamming distance
≤ 5 = near-duplicate. ~2ms per image. Zero wasted tokens.

Both models are called via OpenAI-compatible chat completions with
`response_format: {type: "json_object"}` for structured output.
Responses are validated through Pydantic — malformed output triggers one
retry before falling back to deterministic defaults.

---

## Stack

| Layer     | Technology                                                               |
| --------- | ------------------------------------------------------------------------ |
| Frontend  | Next.js 15, TypeScript, Tailwind, Framer Motion, Zustand                 |
| Backend   | FastAPI, Python 3.11, Pydantic v2, SQLAlchemy (async)                    |
| AI        | **qwen-vl-max** (vision) + **qwen-max** (text/decisions)                 |
| Real-time | WebSocket (full-duplex, event-driven, zero polling)                      |
| Database  | PostgreSQL (Alibaba Cloud RDS) — persistent source of truth              |
| Cache     | Redis (Alibaba Cloud Tair) — telemetry, sessions, state                  |
| Storage   | Alibaba Cloud OSS — logos, product images (presigned PUT, never through backend) |
| Deploy    | Alibaba Cloud Function Compute (serverless) + Docker Compose (local)     |

**157 tests passing · 62 adversarial edge cases · 5/5 Qwen benchmark scenarios passing live (100% valid rate) · MCP server for external agent integration**

---

## Architecture

See **[docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)** for the full
system design with Mermaid diagrams.

```
elevate/
├── storefront-ui/          # Next.js 15 frontend
│   ├── app/
│   │   ├── (onboarding)/  # Setup, brand review, products (5-step flow)
│   │   ├── terminal/      # Merchant command center (decisions, attribution)
│   │   ├── builder/       # Point-and-click store builder
│   │   └── s/[slug]/      # Public storefront (DSL-rendered, themed)
│   ├── components/        # 80+ React components
│   ├── lib/
│   │   ├── ws.ts          # WebSocket client
│   │   ├── store.ts       # Zustand global state
│   │   └── fingerprint.ts # Vision Fingerprinting (perceptual dedup)
│   └── types/schemas.ts   # Zod schemas (mirror Pydantic exactly)
│
└── analytics-brain/        # FastAPI backend
    ├── app/
    │   ├── core/          # Config, Redis, WebSocket manager, security
    │   ├── models/        # Pydantic schemas (source of truth) + DB models
    │   ├── routers/       # 13 routers — products, onboarding, agent, behavior
    │   └── services/      # 18 services — Qwen, brand, vision, interceptor, telemetry
    └── tests/             # 29 test files (unit + integration + adversarial + benchmarks)
```

---

## Deep Dives

The README keeps the pitch tight. Everything below lives in dedicated
docs for anyone who wants to go deeper.

| Topic | Where |
| ----- | ----- |
| **How it works** — onboarding, 3-layer interceptor, fault-tolerant storefront, CSS sanitization, telemetry pipeline, product vision, memory loop, catalog audit, MCP server, token efficiency | [docs/TECHNICAL-DEEP-DIVE.md](./docs/TECHNICAL-DEEP-DIVE.md) |
| **Testing** — 48 test files, adversarial suites, benchmarks | [docs/TESTING.md](./docs/TESTING.md) |
| **Live Qwen benchmarks** — real API run, latency + validity per call type, reproducible | [BENCHMARKS.md](./BENCHMARKS.md) |
| **Architecture diagrams** — Mermaid flowcharts, data flow | [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) |
| **Qwen model usage** — which models, which jobs, token costs | [QWEN_USAGE.md](./QWEN_USAGE.md) |

---

## Getting Started

```bash
git clone https://github.com/Alpha-dev-001/elevate-hackathon
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

# Alibaba Cloud OSS
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

Built for the **Global AI Hackathon Series with Qwen Cloud** —
**Track 4: Autopilot Agent**.

---

## Blog Post

[Elevate: Making Qwen the Brain of a Store That Runs Itself](https://dev.to/alpha-dev-001/elevate-making-qwen-the-brain-of-a-store-that-runs-itself-582p)

---

## License

MIT — see [LICENSE](./LICENSE)
