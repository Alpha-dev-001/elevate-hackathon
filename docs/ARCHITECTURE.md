# Elevate — Architecture

> **The codebase is the body. Qwen is the brain.**
> Elevate is an AI-native commerce platform where Qwen isn't a feature bolted
> onto a store — it *builds* the store from a logo, *renders* a layout unique to
> the brand, *runs* the store from live behavior, and *learns* what works for
> each store over time. The merchant stays in control through option cards, not
> chat: **human-in-the-loop at every critical decision** (Track 4: Autopilot Agent).

These diagrams render natively on GitHub. To export a PNG for the demo/Devpost,
paste any block into <https://mermaid.live> or use the VS Code Mermaid extension.

---

## 1. System overview

How a request flows through the two services and the Alibaba Cloud layer.

```mermaid
flowchart TB
    subgraph Client["🧑‍💼 Clients"]
        M["Merchant Terminal<br/>(Elevate cockpit — option cards)"]
        S["Storefront /s/{slug}<br/>(shopper — wears the brand)"]
    end

    subgraph FE["Frontend — Next.js 15"]
        UI["App Router · Zustand · Framer Motion<br/>DSLRenderer + section/card/nav registries"]
        WS["WebSocket client (lib/ws.ts)"]
    end

    subgraph BE["Backend — FastAPI · Alibaba Cloud ECS (Docker)"]
        API["REST: onboarding · products · brand DSL · orders"]
        WSM["WebSocket manager<br/>(the realtime nervous system — zero polling)"]
        ICPT["Subconscious Interceptor<br/>3 layers · immutable · Qwen cannot override"]
        QWEN["Qwen service (2 models)"]
    end

    subgraph AI["🧠 Qwen Cloud"]
        VL["qwen-vl-max<br/>(multimodal — logo vision)"]
        MAX["qwen-max<br/>(reasoning · structured JSON)"]
    end

    subgraph DATA["Alibaba Cloud data layer"]
        OSS[("OSS<br/>logos · SVG icons")]
        RDS[("PostgreSQL<br/>source of truth")]
        TAIR[("Redis<br/>fast operational layer")]
    end

    M <--> UI
    S <--> UI
    UI <--> WS
    WS <--> WSM
    UI -->|REST| API
    API --> ICPT
    ICPT --> QWEN
    QWEN --> VL
    QWEN --> MAX
    API --> RDS
    API --> TAIR
    UI -->|presigned STS upload| OSS
    WSM --> RDS
    WSM --> TAIR
```

**Design rules made explicit here:**
- Frontend and backend are strictly separated — no shared code.
- All live data flows over WebSocket; REST only for onboarding, uploads, health.
- FastAPI never touches file bytes — the browser uploads logos straight to OSS
  via a short-lived STS token (serverless functions must not stream binaries).
- Redis is never the only copy of anything important; Postgres is the truth.

**Deployment:** the backend runs on **Alibaba Cloud ECS** — a single instance
running the FastAPI service, PostgreSQL, and Redis as Docker containers — with
**Alibaba OSS** for logo/asset storage (`analytics-brain/app/routers/upload.py`
uses the `oss2` SDK) and **Qwen Cloud** for all model calls. The frontend can be
hosted anywhere (only the backend must run on Alibaba per the hackathon rules).

---

## 2. The Qwen cognitive loop — 6+ distinct call types, 2 models

This is the heart of the "60%" (Technical Depth + Innovation). One logo becomes
a fully-branded, self-running store, and **the loop closes** so Qwen gets smarter
per store: action → outcome → memory → a better next decision.

```mermaid
flowchart TD
    LOGO["Logo uploaded to OSS"] --> C1

    C1["① qwen-vl-max · analyze_logo()<br/>image → LogoAnalysis (geometry, palette, mood)"]
    C1 --> C2["② qwen-max · generate_brand()<br/>→ palette · type · voice · SVG icons · BrandGuardRules"]
    C2 --> C3["③ qwen-max · generate_layout_dsl()<br/>→ LayoutDSL: sections[] + global_config<br/>Defense A/B/C — a broken/templated store is impossible"]
    C3 --> C4["④ qwen-max · generate_custom_css()<br/>→ scoped CSS, sanitized to [data-store=slug]"]
    C4 --> C6["⑥ qwen-max · generate_descriptions()<br/>ONE batched call for all products (never a per-item loop)"]

    C4 -.StoreBirth SSE streams ①–④ as visible steps.-> BUILDER

    BUILDER["🧑 Store Builder — human-in-the-loop<br/>drag-reorder · variant swap · point-and-edit<br/>instant local brand-guard advisory (0 Qwen latency)"]
    BUILDER --> PUB["Publish → /s/{slug} live"]

    PUB --> BROWSE["Shopper browsing → behavior events<br/>→ Redis → deterministic anomaly threshold"]
    BROWSE --> C5

    C5["⑤ qwen-max · run_decision_cycle()<br/>reads MEMORY first, then decides ONE action<br/>→ AgentAction option card"]
    C5 --> CHECK{"🧑 Merchant<br/>approve / dismiss<br/>(human-in-the-loop checkpoint)"}
    CHECK -->|approve| DELTA["Delta executed → storefront morphs (fluid)<br/>promo_id attached for attribution"]
    CHECK -->|dismiss| OBS
    DELTA --> ATTR["Attribution: orders joined by promo_id<br/>'this action drove $X · your fee $Y'"]
    ATTR --> OBS["Outcome Observer (background)<br/>counts attributed orders on promo expiry"]
    OBS --> MEM[("MemoryEntry →<br/>merchants.qwen_memory + Redis")]
    MEM -. injected into next cycle .-> C5

    EDIT["⑦ qwen-max · edit-intent / capabilities<br/>point-and-edit → validated DSL option;<br/>a recurring unmet intent → proposes a NEW capability"]
    BUILDER --> EDIT
    EDIT -.-> C3

    style C1 fill:#1f2a44,color:#fff
    style C2 fill:#1f2a44,color:#fff
    style C3 fill:#1f2a44,color:#fff
    style C4 fill:#1f2a44,color:#fff
    style C5 fill:#3b1f44,color:#fff
    style C6 fill:#1f2a44,color:#fff
    style EDIT fill:#3b1f44,color:#fff
    style CHECK fill:#6EE7B7,color:#000
    style BUILDER fill:#6EE7B7,color:#000
    style MEM fill:#2a2a30,color:#fff
```

**Why the loop matters for judging:** Track 4 rewards an agent that (1) automates a
real workflow, (2) has meaningful human checkpoints, (3) *learns over time*, and
(4) does the heavy lifting itself. The green nodes are the human checkpoints; the
`MemoryEntry → next cycle` edge is the learning; the six purple/blue calls are Qwen
doing the work — not orchestrating simpler tools.

---

## 3. The Subconscious Interceptor — 3 layers, immutable

Every proposed action (Qwen's *or* the merchant's) passes through all three layers
before it can take effect. Qwen authored Layer 1 at brand-generation time but can
never override the stack.

```mermaid
flowchart LR
    IN["Proposed action<br/>(Qwen decision · merchant edit · price change)"] --> L1

    L1["Layer 1 — Brand Guard<br/>Qwen-authored rules<br/>(color/layout coherence)"]
    L1 -->|flags, does not block| L2
    L2["Layer 2 — Business Constraints<br/>margin floor · discount ceiling<br/>→ auto-clamp + warn"]
    L2 --> L3
    L3["Layer 3 — System Safety<br/>price &lt; cost · stock &lt; 0 · expired promo<br/>→ HARD BLOCK"]
    L3 -->|passes| OUT["Applied · pushed to all sockets"]
    L3 -.->|violation| STOP["Blocked (409) — surfaced to merchant"]

    style L1 fill:#FFD166,color:#000
    style L2 fill:#FFD166,color:#000
    style L3 fill:#FF6B6B,color:#000
    style OUT fill:#6EE7B7,color:#000
```

---

## 4. Data strategy (two layers)

| Layer | Store | Holds |
|---|---|---|
| **Postgres (RDS)** — source of truth | durable | merchants, products, orders, brand profiles (`brand_tokens` JSONB incl. `layout_dsl` + `custom_css`), `agent_actions`, `qwen_memory` |
| **Redis (Tair)** — fast operational | best-effort cache | behavior events, product velocity, pending actions, `layout_dsl:{id}`, `merchant_memory:{id}`, WS/session state |

Rule: if it must exist tomorrow, it goes to Postgres first, then Redis for speed.

---

## 5. Distinctness guarantee — 40 logos → 40 distinct stores

Three layers make a broken or templated store impossible, even with Qwen offline:

- **A · `coerce_variant`** — type-aware; a hallucinated or cross-type variant falls
  to that slot's type default.
- **B · `normalize_dsl`** — structural rules the renderer *alone* trusts (≤1 leading
  hero, ≥1 grid, 2–5 sections, no adjacent banners).
- **C · `fallback_dsl_from_token`** — deterministic and **brand-seeded**
  (`hash(store_name + mood + industry)`), so stores stay distinct if the Qwen call
  fails entirely.

_Post-hackathon (designed, not built): `action_outcomes` embeddings for cross-store
RAG — "what worked for similar brands" injected at decision time (pgvector + ivfflat)._
