# Sprint 3 — AI-Native Storefront Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the structurally-identical sprint-2 storefront into 40-genuinely-distinct AI-composed stores, give the merchant a live human-in-the-loop Store Builder, and close the Qwen cognitive loop (action → outcome → memory → smarter next decision) so the autopilot visibly learns.

**Architecture:** Qwen-Max composes a per-brand `LayoutDSL` (sections + variants + global config + scoped CSS) that a new frontend `DSLRenderer` materialises from a library of section/card/nav components. A draft-DSL Store Builder lets the merchant override Qwen's arrangement before publish. A memory service injects prior outcomes into every decision cycle, and a background outcome-observer writes new memories after promos resolve. StoreBirth SSE makes the whole Qwen chain visible during generation.

**Tech Stack:** FastAPI + SQLAlchemy(async) + Redis (backend) · Next.js 15 + React 18 + Zustand + Framer Motion + @dnd-kit (frontend) · Qwen-VL-Max + Qwen-Max (DashScope, `response_format: {type:"json_object"}`) · pytest (backend) · **vitest + @testing-library/react (frontend — added in Task 0)**.

---

## Global Constraints

These apply to **every** task. Copied verbatim from the spec and CLAUDE.md.

- **Distinctness (the headline constraint):** If 40 stores were created, no two may look like they came from the same template. Distinctness is structural (section sequence, variants, card style, nav style, scoped CSS), not just color. This must hold **even when Qwen is unavailable** — the deterministic fallback DSL must itself be varied.
- **Two Qwen models only:** `qwen-vl-max` (logo) and `qwen-max` (everything else). Do not add models. Every prompt string MUST contain the literal word `json` (DashScope rejects `response_format=json_object` otherwise).
- **Qwen output is never trusted:** validate with Pydantic, coerce known near-misses, fall back deterministically. A malformed Qwen response must never produce a broken store or a 500 on the demo path.
- **Zero Qwen calls at interaction time** in the builder/brand-guard — all advisory copy is pre-generated at brand-creation time and compared locally.
- **Frontend never touches Redis/Qwen/bytes.** Strict separation. Zod schemas mirror Pydantic exactly; when a Pydantic model changes, the Zod mirror changes in the same task.
- **Token efficiency:** cache every Qwen output in Redis before returning; `layout_dsl:{merchant_id}` cached forever (invalidated on regenerate). Decision cycles send diffs, not full state.
- **Motion:** Qwen-driven transitions are fluid (`cubic-bezier(0.4,0,0.2,1)`, 350–500ms); merchant-driven changes are instant (150–200ms). All animation respects `prefers-reduced-motion`.
- **Mobile-first:** every component works at 375 / 768 / 1280px. Touch targets ≥ 44×44px. No horizontal scroll except where a variant explicitly intends it.
- **Commits:** message format `[sprint-3] <description>`. **NO `Co-Authored-By` trailer.** Commit at every green milestone. Never commit `.env`. Branch is `main` (sprint-2 merged); create a `sprint-3` branch before Task 0 if not already on one.
- **Demo-day lens:** for every task ask "if this breaks at 2:30 in the video, does the whole concept look broken?" If yes, that failure mode is P0 — handle it before moving on.

---

## Architecture Review — Findings Before Implementation

Read this before starting. These are the decisions that resolve the spec's open questions and close demo-fatal gaps. They are baked into the tasks below.

### Critical gaps the spec leaves open (closed here)

1. **Coercion alone is NOT sufficient for DSL reliability (Open Q2).** The spec's `_DSL_COERCE` map handles near-miss *values* but not: (a) Qwen putting a hero variant under a `product_grid` section, (b) Qwen inventing a `SectionType`, (c) Qwen returning 0 or 8 sections, (d) two heroes, (e) a totally garbage response. The fix is a **three-layer defense**, implemented as separate tested functions:
   - **Layer A — `coerce_variant(section_type, raw)`**: type-aware. Coerces a value only against *that section type's* enum; unknown → that type's safe default.
   - **Layer B — `normalize_dsl(dsl)`**: structural enforcement (Open Q3). Hard rules: 2–5 sections; at most one `hero`; if a hero exists it sorts first; `announcement-bar` banner always floats to page top; at least one `product_grid` (inject `masonry-4col` if missing); no two `banner` sections adjacent. The **renderer never trusts Qwen for structural safety** — `normalize_dsl` is the guarantee.
   - **Layer C — `fallback_dsl_from_token(token)`**: a deterministic, **brand-seeded** DSL composed purely from the already-validated `BrandToken`. Used when Qwen returns nothing usable. Seeded by `hash(store_name + mood + industry_hint)` so the fallback path *still* yields distinct stores — this is what protects the distinctness constraint when Qwen is down. This function is the reliability backbone.
   Decision on Open Q2 (tool-use vs json_object): **keep `response_format:{type:"json_object"}`** (consistent with the working brand pipeline; qwen-max tool-calling is less reliable for deeply nested arrays). Reliability comes from Layers A–C, not from the API mode.

2. **`layout_dsl` must reach the storefront payload.** `PublicStore.brand_token` is what the frontend reads. `BrandToken.layout_dsl` is added in Task 1 and must be populated into the public payload in Task 8, or the renderer never sees it. (Gap in spec §1 — the renderer reads `store.brand_token.layout_dsl` but nothing wires it into `PublicStore`.)

3. **No frontend test runner exists.** TDD is impossible until Task 0 adds vitest. This is sequenced first.

4. **DB migrations:** the repo has no `alembic/versions` directory in use; dev schema comes from SQLAlchemy models. New columns go in `db_models.py` (so fresh DBs are correct) **plus** an idempotent `ALTER TABLE … IF NOT EXISTS` script for existing dev DBs (Task 3). Don't assume Alembic is wired.

5. **Outcome observer scheduling (spec §6).** The spec says "background task triggered when a promo expires." There is no scheduler. Decision: schedule with `asyncio.create_task` + `asyncio.sleep(until expires_at)` at approval time, and also expose the observer for the dismiss path. For demo reliability, promo durations are short (≤ a few minutes), so an in-process timer is sufficient and visible. Document the production path (durable queue) in the diagram, don't build it.

### Open-question decisions (locked)

| # | Question | Decision |
|---|----------|----------|
| 1 | Draft DSL commit model | **Optimistic publish.** Apply draft on publish click; on backend error show a Sync-Error toast with one-tap revert. Mirrors the existing Zod-gate/delta pattern; lowest latency for the demo. |
| 2 | DSL generation structured-output mode | **`json_object` + Layers A–C** (above). No tool-use. |
| 3 | Section ordering | **Both.** Prompt asks Qwen to avoid bad combos; `normalize_dsl` *enforces* them deterministically. Renderer trusts only `normalize_dsl` output. |
| 4 | Memory context size | **Last 8 entries**, hard cap, env-overridable `MEMORY_CONTEXT_ENTRIES`. ~800 tokens/cycle. |
| 5 | Preview perf | **Instant for structure** (reorder/variant/add/remove — cheap, memoized by stable section id). **Color changes** mutate CSS vars via a `requestAnimationFrame`-batched update, not a full re-render. No 300ms debounce (feels laggy on camera). |
| 6 | @dnd-kit vs arrows | **@dnd-kit/core + /sortable.** It IS the human-in-the-loop demo moment; arrows look weak. Keyboard a11y comes free. |
| 7 | StoreBirth parallelism | After `brand_token`, run `generate_layout_dsl` and `generate_brand_voice_and_guards` (incl. CSS) **concurrently** via `asyncio.gather`; stream a step-start event before each and a step-done as each future resolves; emit `complete` when both finish. Target < 10s. |

---

## File Structure

### Backend (`analytics-brain/`)
| File | Responsibility |
|------|----------------|
| `app/models/schemas.py` (modify) | Add LayoutDSL family, enums, `MemoryEntry`; add `layout_dsl` to `BrandToken`. |
| `app/models/db_models.py` (modify) | `qwen_memory` on merchants; `merchant_behavior`, `trigger_description` on agent_actions. (`layout_dsl` lives inside existing `brand_tokens` JSONB.) |
| `app/services/layout_dsl.py` (new) | `coerce_variant`, `normalize_dsl`, `fallback_dsl_from_token`, `generate_layout_dsl`. Pure logic + one Qwen call. |
| `app/services/css_gen.py` (new) | `sanitize_css`, `generate_custom_css` (folded into brand-voice call). |
| `app/services/memory.py` (new) | `get_memory`, `write_memory`, `build_memory_context`. |
| `app/services/outcome_observer.py` (new) | `observe_outcome`, `schedule_observation`. |
| `app/services/brand.py` (modify) | `generate_brand_voice_and_guards` returns guards + voice + custom CSS; wire layout_dsl into pipeline. |
| `app/services/decision_engine.py` (modify) | Inject memory context; record token estimate; set `trigger_description`. |
| `app/routers/brand.py` (new) | `POST/PUT /api/brand/dsl/{slug}`, `GET /api/brand/birth/{session_id}` (SSE). |
| `app/routers/merchant.py` (modify) | `GET /api/merchant/memory/{slug}`. |
| `app/routers/store.py` (modify) | Thread `layout_dsl` into `PublicStore.brand_token`. |
| `app/routers/onboarding.py` (modify) | Generate + persist `layout_dsl` in the pipeline. |
| `migrations/2026_sprint3.sql` (new) | Idempotent ALTERs for existing dev DBs. |
| `tests/test_layout_dsl.py`, `tests/test_memory.py`, `tests/test_css_gen.py`, `tests/test_outcome_observer.py` (new) | Pure-function unit tests (no live server). |
| `tests/test_brand_dsl_live.py`, `tests/test_memory_live.py` (new) | Endpoint integration tests (need `docker compose up`). |

### Frontend (`storefront-ui/`)
| File | Responsibility |
|------|----------------|
| `vitest.config.ts`, `vitest.setup.ts` (new) | Test harness. |
| `types/schemas.ts` (modify) | Zod mirror of LayoutDSL family. |
| `lib/dslRegistry.ts` (new) | Maps `(type,variant)` and nav/card variants → components; single source of truth for "what variants exist". |
| `lib/builderStore.ts` (new) | Zustand draft-DSL state + reducers. |
| `components/storefront/DSLRenderer.tsx`, `DSLSection.tsx`, `DSLNav.tsx`, `DSLFooter.tsx`, `FallbackStorefront.tsx`, `CustomCSSInjector.tsx`, `ProductDrawer.tsx`, `StoreBirth.tsx` (new) | Renderer + chrome. |
| `components/storefront/sections/{hero,product-grid,banner,story}/*.tsx` (new) | 4+4+3+3 section variants. |
| `components/storefront/cards/*.tsx` (new) | 6 card variants. |
| `components/storefront/nav/*.tsx` (new) | 5 nav variants. |
| `components/builder/*.tsx` (new) | Left panel, SectionList (dnd), SectionCard, AddSectionModal, ColorPicker, AdvisoryPanel, BuilderPreview. |
| `app/brand-review/page.tsx` (modify) | Store Builder page. |
| `components/storefront/Storefront.tsx` (modify) | Render `DSLRenderer` instead of `LayoutRouter`. |
| `app/s/[slug]/page.tsx` (modify) | Pass `?p=` to open ProductDrawer. |

---

## Conventions for this plan

- **Backend unit tests** import functions directly and run with `python -m pytest tests/test_x.py -v` (no server needed). **Backend live tests** follow the existing `*_live.py` convention and require `docker compose up`.
- **Frontend tests** run with `npm run test` (vitest, added Task 0).
- Section/card/nav components are a large repetitive family. For each family, **one variant is given as complete worked code**, the rest are specified by an exact prop-contract + per-variant visual delta table, and a **smoke test iterates every registered variant** asserting it renders without throwing and emits its required test-id. This is the right altitude: the testable contract (every registered variant renders) is enforced for all; the bespoke visual code follows the worked exemplar.

---

## Phase 0 — Foundations

### Task 0: Frontend test harness (vitest)

**Files:**
- Modify: `storefront-ui/package.json`
- Create: `storefront-ui/vitest.config.ts`
- Create: `storefront-ui/vitest.setup.ts`
- Test: `storefront-ui/lib/__tests__/harness.test.ts`

**Interfaces:**
- Produces: `npm run test` (vitest) and `@testing-library/react`'s `render`/`screen` available to all later frontend tasks.

- [ ] **Step 1: Install dev deps**

```bash
cd storefront-ui
npm install -D vitest@^2 @vitejs/plugin-react@^4 jsdom@^25 @testing-library/react@^16 @testing-library/jest-dom@^6 @testing-library/user-event@^14
```

- [ ] **Step 2: Add the test script** to `storefront-ui/package.json` `"scripts"`:

```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 3: Write `vitest.config.ts`**

```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
  },
  resolve: { alias: { '@': path.resolve(__dirname, '.') } },
})
```

- [ ] **Step 4: Write `vitest.setup.ts`**

```ts
import '@testing-library/jest-dom/vitest'

// Framer Motion + components call matchMedia (prefers-reduced-motion). jsdom lacks it.
if (!window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false, media: query, onchange: null,
    addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
  }) as unknown as MediaQueryList
}
```

- [ ] **Step 5: Write the harness test** `storefront-ui/lib/__tests__/harness.test.ts`

```ts
import { describe, it, expect } from 'vitest'
describe('test harness', () => {
  it('runs and resolves @ alias world', () => { expect(1 + 1).toBe(2) })
})
```

- [ ] **Step 6: Run and verify pass**

Run: `cd storefront-ui && npm run test`
Expected: 1 passing test.

- [ ] **Step 7: Commit**

```bash
git add storefront-ui/package.json storefront-ui/package-lock.json storefront-ui/vitest.config.ts storefront-ui/vitest.setup.ts storefront-ui/lib/__tests__/harness.test.ts
git commit -m "[sprint-3] add vitest + testing-library frontend test harness"
```

---

### Task 1: Backend LayoutDSL schemas + MemoryEntry

**Files:**
- Modify: `analytics-brain/app/models/schemas.py` (append after the BrandToken block, ~line 152)
- Test: `analytics-brain/tests/test_layout_dsl.py`

**Interfaces:**
- Produces: `SectionType`, `HeroVariant`, `ProductGridVariant`, `BannerVariant`, `StoryVariant`, `ProductCardVariant`, `NavStyle` (str Enums); `LayoutSection`, `LayoutGlobalConfig`, `LayoutDSL`, `MemoryEntry` (BaseModels); `BrandToken.layout_dsl: LayoutDSL | None`.

- [ ] **Step 1: Write the failing test** `analytics-brain/tests/test_layout_dsl.py`

```python
from app.models.schemas import (
    LayoutDSL, LayoutSection, LayoutGlobalConfig, BrandToken, MemoryEntry,
    SectionType, HeroVariant, ProductGridVariant, NavStyle, ProductCardVariant,
)


def test_layout_dsl_minimal_valid():
    dsl = LayoutDSL(
        sections=[
            LayoutSection(type=SectionType.hero, variant=HeroVariant.editorial_stacked.value),
            LayoutSection(type=SectionType.product_grid, variant=ProductGridVariant.featured_2col.value),
        ],
        global_config=LayoutGlobalConfig(
            nav_style=NavStyle.underline_tabs,
            product_card=ProductCardVariant.hover_reveal_text,
        ),
        custom_css="",
    )
    assert len(dsl.sections) == 2
    assert dsl.global_config.color_mode == "auto"      # default
    assert dsl.global_config.corner_radius == "md"     # default
    assert dsl.custom_css == ""


def test_brand_token_layout_dsl_optional():
    # layout_dsl defaults to None so existing brand-token rows still validate
    assert "layout_dsl" in BrandToken.model_fields
    assert BrandToken.model_fields["layout_dsl"].default is None


def test_memory_entry_shape():
    e = MemoryEntry(
        action_type="flash_sale",
        trigger="34 views in 28s for face wash",
        outcome="8 orders, $320",
        merchant_behavior="approved",
    )
    assert e.notes == ""
    assert e.timestamp  # auto-populated
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd analytics-brain && python -m pytest tests/test_layout_dsl.py -v`
Expected: FAIL — `ImportError: cannot import name 'LayoutDSL'`.

- [ ] **Step 3: Implement schemas** — append to `app/models/schemas.py`:

```python
# ─── Sprint 3: LayoutDSL ──────────────────────────────────────────────────────
from datetime import datetime, timezone


class SectionType(str, Enum):
    hero = "hero"
    product_grid = "product_grid"
    banner = "banner"
    story = "story"

class HeroVariant(str, Enum):
    full_bleed_image = "full-bleed-image"
    editorial_stacked = "editorial-stacked"
    minimal_wordmark = "minimal-wordmark"
    split_50_50 = "split-50-50"

class ProductGridVariant(str, Enum):
    masonry_4col = "masonry-4col"
    featured_2col = "featured-2col"
    horizontal_scroll = "horizontal-scroll"
    single_spotlight = "single-spotlight"

class BannerVariant(str, Enum):
    scroll_ticker = "scroll-ticker"
    static_strip = "static-strip"
    announcement_bar = "announcement-bar"

class StoryVariant(str, Enum):
    full_bleed_text = "full-bleed-text"
    split_image_story = "split-image-story"
    quote_callout = "quote-callout"

class ProductCardVariant(str, Enum):
    hover_reveal_text = "hover-reveal-text"
    colored_bg_card = "colored-bg-card"
    editorial_horizontal = "editorial-horizontal"
    borderless_floating = "borderless-floating"
    polaroid_card = "polaroid-card"
    image_below_text = "image-below-text"

class NavStyle(str, Enum):
    underline_tabs = "underline-tabs"
    pill_nav = "pill-nav"
    sidebar_text = "sidebar-text"
    sticky_tabs = "sticky-tabs"
    minimal_text = "minimal-text"


class LayoutSection(BaseModel):
    type: SectionType
    variant: str  # validated against the type's enum by layout_dsl.coerce_variant
    props: dict[str, Any] = Field(default_factory=dict)

class LayoutGlobalConfig(BaseModel):
    nav_style: NavStyle
    product_card: ProductCardVariant
    color_mode: Literal["light", "dark", "auto"] = "auto"
    corner_radius: Literal["none", "sm", "md", "lg", "full"] = "md"
    density: Literal["sparse", "normal", "dense"] = "normal"

class LayoutDSL(BaseModel):
    sections: list[LayoutSection] = Field(min_length=2, max_length=5)
    global_config: LayoutGlobalConfig
    custom_css: str = ""


class MemoryEntry(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    action_type: str
    trigger: str
    outcome: str
    merchant_behavior: str          # approved | dismissed | approved_then_modified
    notes: str = ""
```

- [ ] **Step 4: Add `layout_dsl` to `BrandToken`** — modify the `BrandToken` class (~line 143). Add as the final field:

```python
class BrandToken(BaseModel):
    store_name: str
    tagline: str
    colors: BrandColors
    typography: BrandTypographyToken
    layout: BrandLayoutToken
    mood: str
    industry_hint: str
    brand_voice: str
    layout_dsl: "LayoutDSL | None" = None   # populated by generate_layout_dsl()
```

Add `BrandToken.model_rebuild()` at the end of the LayoutDSL block (forward ref resolution).

- [ ] **Step 5: Run to verify pass**

Run: `cd analytics-brain && python -m pytest tests/test_layout_dsl.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add analytics-brain/app/models/schemas.py analytics-brain/tests/test_layout_dsl.py
git commit -m "[sprint-3] LayoutDSL + MemoryEntry pydantic schemas"
```

---

### Task 2: Zod mirror of LayoutDSL

**Files:**
- Modify: `storefront-ui/types/schemas.ts`
- Test: `storefront-ui/types/__tests__/layoutDsl.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `LayoutSectionSchema`, `LayoutGlobalConfigSchema`, `LayoutDSLSchema`, and types `LayoutDSL`, `LayoutSection`, `LayoutGlobalConfig`; `BrandTokenSchema` extended with `layout_dsl`.

- [ ] **Step 1: Write the failing test** `storefront-ui/types/__tests__/layoutDsl.test.ts`

```ts
import { describe, it, expect } from 'vitest'
import { LayoutDSLSchema, BrandTokenSchema } from '@/types/schemas'

describe('LayoutDSLSchema', () => {
  it('parses a valid DSL and applies defaults', () => {
    const dsl = LayoutDSLSchema.parse({
      sections: [
        { type: 'hero', variant: 'editorial-stacked' },
        { type: 'product_grid', variant: 'featured-2col' },
      ],
      global_config: { nav_style: 'underline-tabs', product_card: 'hover-reveal-text' },
    })
    expect(dsl.global_config.color_mode).toBe('auto')
    expect(dsl.sections[0].props).toEqual({})
    expect(dsl.custom_css).toBe('')
  })

  it('rejects fewer than 2 sections', () => {
    expect(() =>
      LayoutDSLSchema.parse({
        sections: [{ type: 'hero', variant: 'minimal-wordmark' }],
        global_config: { nav_style: 'pill-nav', product_card: 'polaroid-card' },
      }),
    ).toThrow()
  })

  it('accepts brand_token with optional layout_dsl', () => {
    const bt = BrandTokenSchema.parse({
      store_name: 'X', tagline: 't',
      colors: { primary: '#000', accent: '#111', background: '#fff', surface: '#eee', text: '#000', text_muted: '#999' },
      typography: { display_font: 'Syne', body_font: 'Inter' },
      layout: { style: 'editorial', hero_type: 'split', product_grid: 'masonry', card_style: 'borderless', border_radius: '8px', spacing: 'balanced', category_style: 'pill' },
      mood: 'm', industry_hint: 'fashion', brand_voice: 'v',
    })
    expect(bt.layout_dsl ?? null).toBeNull()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd storefront-ui && npm run test -- layoutDsl`
Expected: FAIL — `LayoutDSLSchema` is not exported.

- [ ] **Step 3: Implement** — add to `types/schemas.ts` after the `BrandTokenSchema` block (~line 228), then extend `BrandTokenSchema`:

```ts
// ─── Sprint 3: LayoutDSL (mirrors schemas.py exactly) ──────────────────────────
export const LayoutSectionSchema = z.object({
  type: z.enum(['hero', 'product_grid', 'banner', 'story']),
  variant: z.string(),
  props: z.record(z.any()).default({}),
})

export const LayoutGlobalConfigSchema = z.object({
  nav_style: z.enum(['underline-tabs', 'pill-nav', 'sidebar-text', 'sticky-tabs', 'minimal-text']),
  product_card: z.enum([
    'hover-reveal-text', 'colored-bg-card', 'editorial-horizontal',
    'borderless-floating', 'polaroid-card', 'image-below-text',
  ]),
  color_mode: z.enum(['light', 'dark', 'auto']).default('auto'),
  corner_radius: z.enum(['none', 'sm', 'md', 'lg', 'full']).default('md'),
  density: z.enum(['sparse', 'normal', 'dense']).default('normal'),
})

export const LayoutDSLSchema = z.object({
  sections: z.array(LayoutSectionSchema).min(2).max(5),
  global_config: LayoutGlobalConfigSchema,
  custom_css: z.string().default(''),
})

export type LayoutSection = z.infer<typeof LayoutSectionSchema>
export type LayoutGlobalConfig = z.infer<typeof LayoutGlobalConfigSchema>
export type LayoutDSL = z.infer<typeof LayoutDSLSchema>
```

Then change `BrandTokenSchema` (~line 219) to append:

```ts
  layout_dsl: LayoutDSLSchema.nullable().optional(),
```

(Place the `LayoutDSLSchema` const **above** `BrandTokenSchema`, or use `z.lazy`. Simplest: move the LayoutDSL block above the BrandToken block.)

- [ ] **Step 4: Run to verify pass**

Run: `cd storefront-ui && npm run test -- layoutDsl`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add storefront-ui/types/schemas.ts storefront-ui/types/__tests__/layoutDsl.test.ts
git commit -m "[sprint-3] Zod mirror for LayoutDSL + brand_token.layout_dsl"
```

---

### Task 3: Database columns for memory + outcome attribution

**Files:**
- Modify: `analytics-brain/app/models/db_models.py`
- Create: `analytics-brain/migrations/2026_sprint3.sql`
- Test: `analytics-brain/tests/test_db_models_sprint3.py`

**Interfaces:**
- Produces: `MerchantDB.qwen_memory: dict`; `AgentActionDB.merchant_behavior: str | None`, `AgentActionDB.trigger_description: str | None`. (`layout_dsl` reuses the existing `BrandProfileDB.brand_tokens` JSONB — the BrandToken serialises with its `layout_dsl` key, no new column needed.)

- [ ] **Step 1: Write the failing test** `analytics-brain/tests/test_db_models_sprint3.py`

```python
from app.models.db_models import MerchantDB, AgentActionDB


def test_merchant_has_qwen_memory_column():
    assert "qwen_memory" in MerchantDB.__table__.columns


def test_agent_action_has_outcome_columns():
    cols = AgentActionDB.__table__.columns
    assert "merchant_behavior" in cols
    assert "trigger_description" in cols
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd analytics-brain && python -m pytest tests/test_db_models_sprint3.py -v`
Expected: FAIL — KeyError / assertion error.

- [ ] **Step 3: Implement** — add to `MerchantDB` (after `is_live`):

```python
    qwen_memory: Mapped[dict] = mapped_column(JSON, default=lambda: {"entries": []})
```

Add to `AgentActionDB` (after `executed_at`):

```python
    merchant_behavior: Mapped[str | None] = mapped_column(String, nullable=True)
    trigger_description: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 4: Write the idempotent migration** `analytics-brain/migrations/2026_sprint3.sql`

```sql
-- Sprint 3: memory loop + outcome attribution. Idempotent for existing dev DBs.
ALTER TABLE merchants     ADD COLUMN IF NOT EXISTS qwen_memory JSONB NOT NULL DEFAULT '{"entries": []}';
ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS merchant_behavior VARCHAR(32);
ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS trigger_description TEXT;
-- layout_dsl is stored inside brand_profiles.brand_tokens JSONB — no DDL needed.
```

- [ ] **Step 5: Run to verify pass**

Run: `cd analytics-brain && python -m pytest tests/test_db_models_sprint3.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Apply migration to the running dev DB**

Run: `docker compose exec db psql -U elevate -d elevate -f - < analytics-brain/migrations/2026_sprint3.sql`
Expected: `ALTER TABLE` ×3, no error on re-run.

- [ ] **Step 7: Commit**

```bash
git add analytics-brain/app/models/db_models.py analytics-brain/migrations/2026_sprint3.sql analytics-brain/tests/test_db_models_sprint3.py
git commit -m "[sprint-3] db columns: qwen_memory, merchant_behavior, trigger_description"
```

---

## Phase 1 — LayoutDSL Backend (P1 core — demo impossible without it)

### Task 4: `coerce_variant` — type-aware variant coercion (Defense Layer A)

**Files:**
- Create: `analytics-brain/app/services/layout_dsl.py`
- Test: `analytics-brain/tests/test_layout_dsl_coerce.py`

**Interfaces:**
- Produces: `coerce_variant(section_type: SectionType, raw: str) -> str` (always returns a valid variant for that type); module dicts `VALID_VARIANTS: dict[SectionType, set[str]]`, `DEFAULT_VARIANT: dict[SectionType, str]`, `_DSL_COERCE: dict[str, str]`.

- [ ] **Step 1: Write the failing test** `analytics-brain/tests/test_layout_dsl_coerce.py`

```python
from app.models.schemas import SectionType
from app.services.layout_dsl import coerce_variant, VALID_VARIANTS, DEFAULT_VARIANT


def test_exact_variant_passes_through():
    assert coerce_variant(SectionType.hero, "editorial-stacked") == "editorial-stacked"


def test_near_miss_underscore_coerced():
    assert coerce_variant(SectionType.hero, "editorial_stacked") == "editorial-stacked"


def test_synonym_coerced():
    # 'fullbleed' / 'full bleed' → full-bleed-image
    assert coerce_variant(SectionType.hero, "full bleed") == "full-bleed-image"


def test_wrong_type_variant_falls_back_to_type_default():
    # a product-grid variant requested on a hero section → hero default, never cross-type
    out = coerce_variant(SectionType.hero, "masonry-4col")
    assert out in VALID_VARIANTS[SectionType.hero]
    assert out == DEFAULT_VARIANT[SectionType.hero]


def test_garbage_falls_back_to_type_default():
    assert coerce_variant(SectionType.banner, "🔥unknown🔥") == DEFAULT_VARIANT[SectionType.banner]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd analytics-brain && python -m pytest tests/test_layout_dsl_coerce.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement** — create `app/services/layout_dsl.py`:

```python
"""LayoutDSL engine — Qwen composes the store; this validates, repairs, and
guarantees a renderable result. Three defense layers (A: coerce_variant,
B: normalize_dsl, C: fallback_dsl_from_token) so a garbage Qwen response can
never produce a broken store or a 500 on the demo path."""
from __future__ import annotations

import logging
import re

from app.models.schemas import (
    SectionType, HeroVariant, ProductGridVariant, BannerVariant, StoryVariant,
    NavStyle, ProductCardVariant,
)

logger = logging.getLogger(__name__)

VALID_VARIANTS: dict[SectionType, set[str]] = {
    SectionType.hero: {v.value for v in HeroVariant},
    SectionType.product_grid: {v.value for v in ProductGridVariant},
    SectionType.banner: {v.value for v in BannerVariant},
    SectionType.story: {v.value for v in StoryVariant},
}

DEFAULT_VARIANT: dict[SectionType, str] = {
    SectionType.hero: HeroVariant.editorial_stacked.value,
    SectionType.product_grid: ProductGridVariant.masonry_4col.value,
    SectionType.banner: BannerVariant.static_strip.value,
    SectionType.story: StoryVariant.full_bleed_text.value,
}

# Near-miss → canonical. Keys are normalized (lowercase, non-alnum stripped).
_DSL_COERCE: dict[str, str] = {
    "fullbleedimage": "full-bleed-image", "fullbleed": "full-bleed-image", "hero": "full-bleed-image",
    "editorialstacked": "editorial-stacked", "editorial": "editorial-stacked", "stacked": "editorial-stacked",
    "minimalwordmark": "minimal-wordmark", "wordmark": "minimal-wordmark", "minimal": "minimal-wordmark",
    "split5050": "split-50-50", "split": "split-50-50",
    "masonry4col": "masonry-4col", "masonry": "masonry-4col", "grid": "masonry-4col",
    "featured2col": "featured-2col", "featured": "featured-2col",
    "horizontalscroll": "horizontal-scroll", "scroll": "horizontal-scroll", "carousel": "horizontal-scroll",
    "singlespotlight": "single-spotlight", "spotlight": "single-spotlight",
    "scrollticker": "scroll-ticker", "ticker": "scroll-ticker", "marquee": "scroll-ticker",
    "staticstrip": "static-strip", "strip": "static-strip",
    "announcementbar": "announcement-bar", "announcement": "announcement-bar", "promobar": "announcement-bar",
    "fullbleedtext": "full-bleed-text", "splitimagestory": "split-image-story",
    "imagestory": "split-image-story", "quotecallout": "quote-callout", "quote": "quote-callout",
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def coerce_variant(section_type: SectionType, raw: str) -> str:
    """Return a variant guaranteed valid for `section_type`. Cross-type values
    (e.g. a grid variant on a hero) are NEVER honored — they fall back to the
    type default."""
    valid = VALID_VARIANTS[section_type]
    if raw in valid:
        return raw
    coerced = _DSL_COERCE.get(_norm(raw))
    if coerced in valid:
        return coerced
    # normalized exact match against this type's own variants
    nmap = {_norm(v): v for v in valid}
    if _norm(raw) in nmap:
        return nmap[_norm(raw)]
    logger.warning("[dsl] unmapped variant %r for %s → default", raw, section_type.value)
    return DEFAULT_VARIANT[section_type]
```

- [ ] **Step 4: Run to verify pass**

Run: `cd analytics-brain && python -m pytest tests/test_layout_dsl_coerce.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add analytics-brain/app/services/layout_dsl.py analytics-brain/tests/test_layout_dsl_coerce.py
git commit -m "[sprint-3] type-aware variant coercion (DSL defense layer A)"
```

---

### Task 5: `normalize_dsl` — structural enforcement (Defense Layer B)

**Files:**
- Modify: `analytics-brain/app/services/layout_dsl.py`
- Test: `analytics-brain/tests/test_layout_dsl_normalize.py`

**Interfaces:**
- Consumes: `coerce_variant`.
- Produces: `normalize_dsl(raw: dict) -> LayoutDSL`. Accepts a raw dict (Qwen JSON), returns a fully-valid `LayoutDSL`. Hard guarantees: 2–5 sections; ≤1 hero (extras dropped); hero (if any) first; `announcement-bar` banners floated to index 0; ≥1 `product_grid` (inject `masonry-4col` if absent); no two banners adjacent; every variant valid for its type; global_config defaults filled.

- [ ] **Step 1: Write the failing test** `analytics-brain/tests/test_layout_dsl_normalize.py`

```python
import pytest
from app.services.layout_dsl import normalize_dsl
from app.models.schemas import LayoutDSL, SectionType


def _gc():
    return {"nav_style": "underline-tabs", "product_card": "hover-reveal-text"}


def test_drops_extra_heroes_and_sorts_hero_first():
    out = normalize_dsl({
        "sections": [
            {"type": "product_grid", "variant": "masonry-4col"},
            {"type": "hero", "variant": "editorial-stacked"},
            {"type": "hero", "variant": "split-50-50"},  # extra hero — dropped
        ],
        "global_config": _gc(),
    })
    assert isinstance(out, LayoutDSL)
    assert out.sections[0].type == SectionType.hero
    assert sum(s.type == SectionType.hero for s in out.sections) == 1


def test_injects_product_grid_when_missing():
    out = normalize_dsl({
        "sections": [
            {"type": "hero", "variant": "minimal-wordmark"},
            {"type": "story", "variant": "quote-callout"},
        ],
        "global_config": _gc(),
    })
    assert any(s.type == SectionType.product_grid for s in out.sections)


def test_announcement_bar_floats_to_top():
    out = normalize_dsl({
        "sections": [
            {"type": "hero", "variant": "split-50-50"},
            {"type": "product_grid", "variant": "featured-2col"},
            {"type": "banner", "variant": "announcement-bar"},
        ],
        "global_config": _gc(),
    })
    assert out.sections[0].type == SectionType.banner
    assert out.sections[0].variant == "announcement-bar"


def test_clamps_to_five_sections():
    out = normalize_dsl({
        "sections": [{"type": "product_grid", "variant": "masonry-4col"}] * 9,
        "global_config": _gc(),
    })
    assert 2 <= len(out.sections) <= 5


def test_empty_sections_still_yields_valid_dsl():
    out = normalize_dsl({"sections": [], "global_config": _gc()})
    assert len(out.sections) >= 2
    assert any(s.type == SectionType.product_grid for s in out.sections)


def test_no_two_banners_adjacent():
    out = normalize_dsl({
        "sections": [
            {"type": "banner", "variant": "static-strip"},
            {"type": "banner", "variant": "scroll-ticker"},
            {"type": "product_grid", "variant": "masonry-4col"},
        ],
        "global_config": _gc(),
    })
    types = [s.type for s in out.sections]
    for a, b in zip(types, types[1:]):
        assert not (a == SectionType.banner and b == SectionType.banner)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd analytics-brain && python -m pytest tests/test_layout_dsl_normalize.py -v`
Expected: FAIL — `normalize_dsl` not defined.

- [ ] **Step 3: Implement** — append to `app/services/layout_dsl.py`:

```python
from app.models.schemas import (
    LayoutDSL, LayoutSection, LayoutGlobalConfig,
)

_VALID_NAV = {v.value for v in NavStyle}
_VALID_CARD = {v.value for v in ProductCardVariant}


def _coerce_global(raw: object) -> LayoutGlobalConfig:
    g = raw if isinstance(raw, dict) else {}
    nav = g.get("nav_style")
    card = g.get("product_card")
    return LayoutGlobalConfig(
        nav_style=nav if nav in _VALID_NAV else NavStyle.underline_tabs.value,
        product_card=card if card in _VALID_CARD else ProductCardVariant.hover_reveal_text.value,
        color_mode=g.get("color_mode") if g.get("color_mode") in ("light", "dark", "auto") else "auto",
        corner_radius=g.get("corner_radius") if g.get("corner_radius") in ("none", "sm", "md", "lg", "full") else "md",
        density=g.get("density") if g.get("density") in ("sparse", "normal", "dense") else "normal",
    )


def _clean_sections(raw_sections: object) -> list[LayoutSection]:
    out: list[LayoutSection] = []
    if isinstance(raw_sections, list):
        for s in raw_sections:
            if not isinstance(s, dict):
                continue
            try:
                st = SectionType(str(s.get("type", "")).strip().replace("-", "_"))
            except ValueError:
                continue
            variant = coerce_variant(st, str(s.get("variant", "")))
            props = s.get("props") if isinstance(s.get("props"), dict) else {}
            out.append(LayoutSection(type=st, variant=variant, props=props))
    return out


def normalize_dsl(raw: dict) -> LayoutDSL:
    """Defense Layer B. Turn any raw dict into a structurally-safe LayoutDSL."""
    sections = _clean_sections(raw.get("sections"))

    # Rule: at most one hero, and it leads.
    heroes = [s for s in sections if s.type == SectionType.hero]
    non_hero = [s for s in sections if s.type != SectionType.hero]
    sections = ([heroes[0]] if heroes else []) + non_hero

    # Rule: announcement-bar floats above everything (even the hero).
    announce = [s for s in sections if s.type == SectionType.banner and s.variant == "announcement-bar"]
    rest = [s for s in sections if not (s.type == SectionType.banner and s.variant == "announcement-bar")]
    sections = announce[:1] + rest

    # Rule: at least one product_grid.
    if not any(s.type == SectionType.product_grid for s in sections):
        sections.append(LayoutSection(
            type=SectionType.product_grid,
            variant=DEFAULT_VARIANT[SectionType.product_grid],
        ))

    # Rule: no two banners adjacent — drop the second of any adjacent pair.
    deduped: list[LayoutSection] = []
    for s in sections:
        if deduped and deduped[-1].type == SectionType.banner and s.type == SectionType.banner:
            continue
        deduped.append(s)
    sections = deduped

    # Clamp 2..5. Pad with a story if too short.
    if len(sections) < 2:
        sections.append(LayoutSection(type=SectionType.story, variant=DEFAULT_VARIANT[SectionType.story]))
    sections = sections[:5]

    return LayoutDSL(
        sections=sections,
        global_config=_coerce_global(raw.get("global_config")),
        custom_css=str(raw.get("custom_css") or ""),
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `cd analytics-brain && python -m pytest tests/test_layout_dsl_normalize.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add analytics-brain/app/services/layout_dsl.py analytics-brain/tests/test_layout_dsl_normalize.py
git commit -m "[sprint-3] structural DSL normalization (defense layer B)"
```

---

### Task 6: `fallback_dsl_from_token` — brand-seeded deterministic DSL (Defense Layer C)

This is the **distinctness backbone**: even with Qwen offline, two different brands get different stores.

**Files:**
- Modify: `analytics-brain/app/services/layout_dsl.py`
- Test: `analytics-brain/tests/test_layout_dsl_fallback.py`

**Interfaces:**
- Consumes: `normalize_dsl`.
- Produces: `fallback_dsl_from_token(token: BrandToken) -> LayoutDSL`. Deterministic for a given token; varied across tokens. Maps `token.layout.style` to a base arrangement, then perturbs variant/card/nav choices by `hash(store_name+mood+industry_hint)`.

- [ ] **Step 1: Write the failing test** `analytics-brain/tests/test_layout_dsl_fallback.py`

```python
from app.services.layout_dsl import fallback_dsl_from_token
from app.models.schemas import BrandToken, BrandColors, BrandTypographyToken, BrandLayoutToken


def _token(name, style, mood="m", industry="fashion"):
    return BrandToken(
        store_name=name, tagline="t",
        colors=BrandColors(primary="#000", accent="#111", background="#fff", surface="#eee", text="#000", text_muted="#999"),
        typography=BrandTypographyToken(display_font="Syne", body_font="Inter"),
        layout=BrandLayoutToken(style=style, hero_type="split", product_grid="masonry",
                                card_style="borderless", border_radius="8px", spacing="balanced", category_style="pill"),
        mood=mood, industry_hint=industry, brand_voice="v",
    )


def test_deterministic_for_same_token():
    a = fallback_dsl_from_token(_token("Haree", "editorial"))
    b = fallback_dsl_from_token(_token("Haree", "editorial"))
    assert a.model_dump() == b.model_dump()


def test_distinct_across_styles():
    sigs = set()
    for style in ("editorial", "bold-grid", "minimal-dark", "warm-craft"):
        d = fallback_dsl_from_token(_token("Store", style))
        sig = (tuple((s.type.value, s.variant) for s in d.sections),
               d.global_config.nav_style, d.global_config.product_card)
        sigs.add(sig)
    assert len(sigs) == 4   # every base style yields a structurally different store


def test_distinct_across_names_same_style():
    # 40-store distinctness: same style, different brand identity → different store
    sigs = set()
    for i in range(40):
        d = fallback_dsl_from_token(_token(f"brand-{i}", "editorial", mood=f"mood{i%5}", industry="fashion"))
        sig = (tuple((s.type.value, s.variant) for s in d.sections),
               d.global_config.nav_style, d.global_config.product_card, d.global_config.corner_radius)
        sigs.add(sig)
    assert len(sigs) >= 12   # strong structural variety from seed perturbation


def test_always_valid():
    d = fallback_dsl_from_token(_token("X", "minimal-dark"))
    assert 2 <= len(d.sections) <= 5
    assert any(s.type.value == "product_grid" for s in d.sections)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd analytics-brain && python -m pytest tests/test_layout_dsl_fallback.py -v`
Expected: FAIL — not defined.

- [ ] **Step 3: Implement** — append to `app/services/layout_dsl.py`:

```python
import hashlib
from app.models.schemas import BrandToken

# Per-style base arrangement (ordered section types) + candidate pools to pick
# from via the brand seed. Each style reads as a different store family.
_STYLE_BLUEPRINT: dict[str, dict] = {
    "editorial": {
        "sections": [SectionType.hero, SectionType.banner, SectionType.product_grid, SectionType.story],
        "hero": ["editorial-stacked", "split-50-50"],
        "grid": ["featured-2col", "masonry-4col"],
        "banner": ["scroll-ticker", "static-strip"],
        "story": ["full-bleed-text", "quote-callout"],
        "nav": ["underline-tabs", "minimal-text"],
        "card": ["editorial-horizontal", "image-below-text", "borderless-floating"],
        "radius": ["none", "sm"],
    },
    "bold-grid": {
        "sections": [SectionType.hero, SectionType.product_grid, SectionType.banner],
        "hero": ["full-bleed-image", "split-50-50"],
        "grid": ["masonry-4col", "featured-2col"],
        "banner": ["static-strip", "announcement-bar"],
        "story": ["split-image-story"],
        "nav": ["pill-nav", "sticky-tabs"],
        "card": ["colored-bg-card", "polaroid-card"],
        "radius": ["lg", "full"],
    },
    "minimal-dark": {
        "sections": [SectionType.hero, SectionType.product_grid, SectionType.story],
        "hero": ["minimal-wordmark", "full-bleed-image"],
        "grid": ["horizontal-scroll", "single-spotlight", "masonry-4col"],
        "banner": ["scroll-ticker"],
        "story": ["full-bleed-text"],
        "nav": ["sidebar-text", "minimal-text"],
        "card": ["hover-reveal-text", "borderless-floating"],
        "radius": ["none", "sm"],
    },
    "warm-craft": {
        "sections": [SectionType.banner, SectionType.hero, SectionType.product_grid, SectionType.story],
        "hero": ["split-50-50", "editorial-stacked"],
        "grid": ["masonry-4col", "featured-2col"],
        "banner": ["static-strip", "scroll-ticker"],
        "story": ["split-image-story", "quote-callout"],
        "nav": ["pill-nav", "underline-tabs"],
        "card": ["polaroid-card", "image-below-text"],
        "radius": ["md", "lg"],
    },
}


def _seed(token: BrandToken) -> int:
    raw = f"{token.store_name}|{token.mood}|{token.industry_hint}".encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def _pick(pool: list[str], seed: int, salt: int) -> str:
    return pool[(seed >> (salt * 3)) % len(pool)]


def fallback_dsl_from_token(token: BrandToken) -> LayoutDSL:
    """Defense Layer C — deterministic, brand-seeded DSL. Guarantees distinct
    stores even when Qwen is unavailable."""
    bp = _STYLE_BLUEPRINT.get(token.layout.style, _STYLE_BLUEPRINT["editorial"])
    seed = _seed(token)

    sections: list[dict] = []
    for i, st in enumerate(bp["sections"]):
        if st == SectionType.hero:
            variant = _pick(bp["hero"], seed, i)
        elif st == SectionType.product_grid:
            variant = _pick(bp["grid"], seed, i)
        elif st == SectionType.banner:
            variant = _pick(bp["banner"], seed, i)
        else:
            variant = _pick(bp["story"], seed, i)
        sections.append({"type": st.value, "variant": variant})

    raw = {
        "sections": sections,
        "global_config": {
            "nav_style": _pick(bp["nav"], seed, 7),
            "product_card": _pick(bp["card"], seed, 5),
            "color_mode": "dark" if token.layout.style == "minimal-dark" else "auto",
            "corner_radius": _pick(bp["radius"], seed, 3),
            "density": "dense" if token.layout.style == "bold-grid" else "normal",
        },
        "custom_css": "",
    }
    return normalize_dsl(raw)  # run through Layer B for the structural guarantee
```

- [ ] **Step 4: Run to verify pass**

Run: `cd analytics-brain && python -m pytest tests/test_layout_dsl_fallback.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add analytics-brain/app/services/layout_dsl.py analytics-brain/tests/test_layout_dsl_fallback.py
git commit -m "[sprint-3] brand-seeded deterministic fallback DSL (defense layer C, distinctness backbone)"
```

---

### Task 7: `generate_layout_dsl` — the Qwen-Max DSL call

**Files:**
- Modify: `analytics-brain/app/services/layout_dsl.py`
- Modify: `analytics-brain/app/routers/onboarding.py` (pipeline wiring)
- Test: `analytics-brain/tests/test_generate_layout_dsl.py`

**Interfaces:**
- Consumes: `normalize_dsl`, `fallback_dsl_from_token`, `brand._qwen_chat`, `brand._extract_json`, `BrandGenerationError`.
- Produces: `async generate_layout_dsl(token: BrandToken, store_name: str, category: str, product_count: int, *, _chat=...) -> LayoutDSL`. Never raises — falls back to `fallback_dsl_from_token` on any Qwen/parse failure. `_chat` injectable for tests.

- [ ] **Step 1: Write the failing test** `analytics-brain/tests/test_generate_layout_dsl.py`

```python
import json, asyncio
import pytest
from app.services.layout_dsl import generate_layout_dsl
from app.models.schemas import (
    BrandToken, BrandColors, BrandTypographyToken, BrandLayoutToken, LayoutDSL, SectionType,
)


def _token():
    return BrandToken(
        store_name="Haree", tagline="t",
        colors=BrandColors(primary="#000", accent="#6EE7B7", background="#0A0A0B", surface="#111", text="#fff", text_muted="#999"),
        typography=BrandTypographyToken(display_font="Syne", body_font="Inter"),
        layout=BrandLayoutToken(style="editorial", hero_type="split", product_grid="masonry",
                                card_style="borderless", border_radius="8px", spacing="balanced", category_style="pill"),
        mood="refined", industry_hint="beauty", brand_voice="quiet",
    )


def test_valid_qwen_output_parsed():
    async def fake_chat(**kw):
        return json.dumps({
            "sections": [
                {"type": "hero", "variant": "editorial-stacked"},
                {"type": "product_grid", "variant": "featured-2col"},
            ],
            "global_config": {"nav_style": "underline-tabs", "product_card": "editorial-horizontal"},
        })
    dsl = asyncio.run(generate_layout_dsl(_token(), "Haree", "beauty", 6, _chat=fake_chat))
    assert isinstance(dsl, LayoutDSL)
    assert dsl.sections[0].type == SectionType.hero


def test_qwen_hallucinated_variant_coerced_not_crashed():
    async def fake_chat(**kw):
        return json.dumps({
            "sections": [
                {"type": "hero", "variant": "big_giant_banner"},      # invalid → default
                {"type": "product_grid", "variant": "masonry_grid_4"},# near-miss → masonry-4col
            ],
            "global_config": {"nav_style": "tabs", "product_card": "mystery"},
        })
    dsl = asyncio.run(generate_layout_dsl(_token(), "Haree", "beauty", 6, _chat=fake_chat))
    assert dsl.sections[0].variant in {v.value for v in __import__("app.models.schemas", fromlist=["HeroVariant"]).HeroVariant}


def test_qwen_failure_falls_back():
    async def boom(**kw):
        raise RuntimeError("qwen down")
    dsl = asyncio.run(generate_layout_dsl(_token(), "Haree", "beauty", 6, _chat=boom))
    assert isinstance(dsl, LayoutDSL)        # never raises
    assert any(s.type == SectionType.product_grid for s in dsl.sections)


def test_qwen_non_json_falls_back():
    async def junk(**kw):
        return "I'm sorry, I cannot help with that."
    dsl = asyncio.run(generate_layout_dsl(_token(), "Haree", "beauty", 6, _chat=junk))
    assert isinstance(dsl, LayoutDSL)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd analytics-brain && python -m pytest tests/test_generate_layout_dsl.py -v`
Expected: FAIL — `generate_layout_dsl` not defined.

- [ ] **Step 3: Implement** — append to `app/services/layout_dsl.py`:

```python
from app.core.config import get_settings

LAYOUT_DSL_PROMPT = """You are an elite art director composing a UNIQUE storefront layout.
Return ONLY a json object. No prose, no markdown.

You assemble 2-5 ordered sections that feel cohesive for THIS brand's mood and industry.

Section types and their ONLY allowed variants:
- hero: full-bleed-image | editorial-stacked | minimal-wordmark | split-50-50
- product_grid: masonry-4col | featured-2col | horizontal-scroll | single-spotlight
- banner: scroll-ticker | static-strip | announcement-bar
- story: full-bleed-text | split-image-story | quote-callout

global_config:
- nav_style: underline-tabs | pill-nav | sidebar-text | sticky-tabs | minimal-text
- product_card: hover-reveal-text | colored-bg-card | editorial-horizontal | borderless-floating | polaroid-card | image-below-text
- corner_radius: none | sm | md | lg | full
- density: sparse | normal | dense

Rules:
- Exactly ONE hero, and it must be the first section (unless an announcement-bar leads).
- Include at least one product_grid.
- single-spotlight only if product_count <= 10.
- Be OPINIONATED. A luxury beauty brand and a bold streetwear brand must produce
  structurally different stores — different sections, variants, nav, and card.

Return json shaped exactly:
{
  "sections": [{"type": "...", "variant": "...", "props": {}}],
  "global_config": {"nav_style":"...","product_card":"...","corner_radius":"...","density":"..."}
}

Brand:
{brand_json}
product_count: {product_count}
Pure json. Nothing else."""


async def generate_layout_dsl(
    token: BrandToken,
    store_name: str,
    category: str,
    product_count: int,
    *,
    _chat=None,
) -> LayoutDSL:
    """qwen-max composes the store. NEVER raises — any failure (network, non-JSON,
    garbage) falls back to the brand-seeded deterministic DSL."""
    from app.services.brand import _qwen_chat, _extract_json, BrandGenerationError
    import json as _json

    chat = _chat or _qwen_chat
    brand_json = _json.dumps({
        "store_name": store_name, "category": category,
        "mood": token.mood, "industry_hint": token.industry_hint,
        "layout_style": token.layout.style, "brand_voice": token.brand_voice,
    })
    prompt = LAYOUT_DSL_PROMPT.replace("{brand_json}", brand_json).replace("{product_count}", str(product_count))

    try:
        raw = await chat(
            model=get_settings().qwen_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200, temperature=0.7, timeout=60.0,
        )
        data = _extract_json(raw)
        return normalize_dsl(data)
    except Exception as e:  # noqa: BLE001 — fallback must be total for the demo path
        logger.warning("[dsl] generate_layout_dsl falling back to deterministic DSL: %s", e)
        return fallback_dsl_from_token(token)
```

- [ ] **Step 4: Run to verify pass**

Run: `cd analytics-brain && python -m pytest tests/test_generate_layout_dsl.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Wire into the onboarding pipeline.** In `app/routers/onboarding.py`, inside `_run_brand_pipeline`, where `brand_token_result` is saved (after `brand_profile.brand_tokens = brand_token_result.model_dump()`, ~line 227), generate and attach the DSL before the dump:

```python
                if brand_profile and isinstance(brand_token_result, BrandToken):
                    from app.services.layout_dsl import generate_layout_dsl
                    product_count = existing_count or len(seed_products_raw or [])
                    brand_token_result.layout_dsl = await generate_layout_dsl(
                        brand_token_result, store_name, category, product_count,
                    )
                    brand_profile.brand_tokens = brand_token_result.model_dump()
                    # cache forever; invalidated on regenerate
                    try:
                        from app.core.redis import get_redis, Keys
                        r = await get_redis()
                        await r.set(f"layout_dsl:{merchant_id}", brand_token_result.layout_dsl.model_dump_json())
                    except Exception as ce:
                        logger.warning("[onboarding] layout_dsl cache failed for %s: %s", merchant_id, ce)
```

(Note: `existing_count` is computed a few lines below in the current code — move the `existing_count` query above this block, or reuse `product_count = len(seed_products_raw or [])`. Keep it simple: use `len(seed_products_raw or [])`.)

- [ ] **Step 6: Restart backend and smoke the pipeline**

Run: `docker compose restart api && docker compose logs api --tail 30`
Expected: no errors; on a fresh onboarding the log shows `BrandToken saved … layout.style=…` with no DSL traceback.

- [ ] **Step 7: Commit**

```bash
git add analytics-brain/app/services/layout_dsl.py analytics-brain/app/routers/onboarding.py analytics-brain/tests/test_generate_layout_dsl.py
git commit -m "[sprint-3] generate_layout_dsl qwen-max call + onboarding wiring + redis cache"
```

---

### Task 8: Thread `layout_dsl` into the public store payload

**Files:**
- Modify: `analytics-brain/app/routers/store.py`
- Test: `analytics-brain/tests/test_store_dsl_live.py`

**Interfaces:**
- Produces: `PublicStore.brand_token.layout_dsl` populated from `BrandProfileDB.brand_tokens` for live stores.

- [ ] **Step 1: Read the store router** to find where `brand_token` is built into `PublicStore`.

Run: `cd analytics-brain && grep -n "brand_token\|brand_tokens\|PublicStore" app/routers/store.py`

- [ ] **Step 2: Write the failing live test** `analytics-brain/tests/test_store_dsl_live.py`

```python
"""Requires docker compose up + a published store 'haree' with a brand_token."""
import httpx
BASE = "http://localhost:9000"


def test_public_store_includes_layout_dsl():
    r = httpx.get(f"{BASE}/api/store/haree", timeout=10)
    assert r.status_code == 200, r.text
    bt = r.json().get("brand_token")
    assert bt is not None, "haree must have a brand_token"
    dsl = bt.get("layout_dsl")
    assert dsl is not None, "layout_dsl must be threaded into the public payload"
    assert 2 <= len(dsl["sections"]) <= 5
    assert "global_config" in dsl
```

(Adjust the store path to the real route discovered in Step 1, e.g. `/api/store/{slug}` or `/shop/{slug}`.)

- [ ] **Step 3: Run to verify it fails**

Run: `cd analytics-brain && python -m pytest tests/test_store_dsl_live.py -v`
Expected: FAIL — `layout_dsl` is null (not threaded yet).

- [ ] **Step 4: Implement** — in `store.py` where the `BrandToken` is loaded from `brand_profile.brand_tokens` and attached to `PublicStore`, ensure the full dict (which now includes `layout_dsl`) is passed through. If the code reconstructs `BrandToken(**brand_tokens)`, no change is needed beyond confirming `brand_tokens` contains `layout_dsl`. If it cherry-picks fields, add `layout_dsl`. Concretely, ensure:

```python
    brand_token = BrandToken.model_validate(profile.brand_tokens) if profile and profile.brand_tokens else None
    # brand_token.layout_dsl now flows through to PublicStore unchanged
```

If `layout_dsl` is missing from an older `brand_tokens` row, lazily backfill it so existing stores aren't broken:

```python
    if brand_token is not None and brand_token.layout_dsl is None:
        from app.services.layout_dsl import fallback_dsl_from_token
        brand_token.layout_dsl = fallback_dsl_from_token(brand_token)
```

- [ ] **Step 5: Restart + run the live test**

Run: `docker compose restart api && cd analytics-brain && python -m pytest tests/test_store_dsl_live.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add analytics-brain/app/routers/store.py analytics-brain/tests/test_store_dsl_live.py
git commit -m "[sprint-3] thread layout_dsl into public store payload + lazy backfill"
```

---

## Phase 2 — DSL Renderer + Component Library (P1 core — demo-critical)

> **Family pattern (read once):** Section, card, and nav variants share a contract. For each family one variant is fully coded; the rest follow the per-variant delta table. Every variant is registered in `lib/dslRegistry.ts` and covered by a smoke test that renders it with a fixture store and asserts it (a) does not throw and (b) renders its `data-variant` test id. Bespoke visual fidelity (per the spec's §2/§3/§9 descriptions) is implemented against the worked exemplar.

### Task 9: DSL registry + routing + renderer + fallback

**Files:**
- Create: `storefront-ui/lib/dslRegistry.ts`
- Create: `storefront-ui/components/storefront/DSLRenderer.tsx`
- Create: `storefront-ui/components/storefront/DSLSection.tsx`
- Create: `storefront-ui/components/storefront/DSLNav.tsx`
- Create: `storefront-ui/components/storefront/DSLFooter.tsx`
- Create: `storefront-ui/components/storefront/FallbackStorefront.tsx`
- Create: `storefront-ui/lib/__tests__/dslRenderer.test.tsx`
- Create: `storefront-ui/test/fixtures.ts`

**Interfaces:**
- Consumes: `PublicStore`, `LayoutDSL`, `resolveTheme`, `StoreShell`.
- Produces: `SECTION_REGISTRY`, `CARD_REGISTRY`, `NAV_REGISTRY` (maps variant→component); `<DSLRenderer store slug preview? onOpenProduct? />`; `<DSLSection />`; `<DSLNav />`; `<FallbackStorefront />`.

- [ ] **Step 1: Write the test fixture** `storefront-ui/test/fixtures.ts`

```ts
import type { PublicStore, LayoutDSL } from '@/types/schemas'

export const fixtureDSL: LayoutDSL = {
  sections: [
    { type: 'hero', variant: 'editorial-stacked', props: {} },
    { type: 'product_grid', variant: 'featured-2col', props: {} },
  ],
  global_config: {
    nav_style: 'underline-tabs', product_card: 'hover-reveal-text',
    color_mode: 'auto', corner_radius: 'md', density: 'normal',
  },
  custom_css: '',
}

export const fixtureStore: PublicStore = {
  store_name: 'Haree', slug: 'haree', tagline: 'Quiet luxury',
  palette: { primary: '#0A0A0B', secondary: '#222', accent: '#6EE7B7', background: '#0A0A0B', text: '#fff' },
  typography: { display_font: 'Syne', body_font: 'Inter' },
  icons: { logo_mark: '<svg viewBox="0 0 64 64"><rect width="64" height="64"/></svg>', store_icon: '<svg/>' },
  layout: { layout_variant: 'standard' },
  products: [
    { id: 'p1', name: 'Face Wash', price: 24, available: true, category: 'care', image_url: null, description: 'd', compare_at_price: null, promo_label: null },
    { id: 'p2', name: 'Serum', price: 48, available: true, category: 'care', image_url: null, description: 'd', compare_at_price: null, promo_label: null },
  ],
  promos: [], categories: ['care'],
  brand_token: {
    store_name: 'Haree', tagline: 'Quiet luxury',
    colors: { primary: '#0A0A0B', accent: '#6EE7B7', background: '#0A0A0B', surface: '#111', text: '#fff', text_muted: '#999' },
    typography: { display_font: 'Syne', body_font: 'Inter', scale: 'editorial', letter_spacing: 'wide', weight: 'regular' },
    layout: { style: 'editorial', hero_type: 'split', product_grid: 'masonry', card_style: 'borderless', border_radius: '8px', spacing: 'balanced', category_style: 'underline-tab' },
    mood: 'refined', industry_hint: 'beauty', brand_voice: 'quiet',
    layout_dsl: fixtureDSL,
  },
}
```

- [ ] **Step 2: Write the failing renderer test** `storefront-ui/lib/__tests__/dslRenderer.test.tsx`

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DSLRenderer } from '@/components/storefront/DSLRenderer'
import { FallbackStorefront } from '@/components/storefront/FallbackStorefront'
import { fixtureStore } from '@/test/fixtures'

describe('DSLRenderer', () => {
  it('renders one DOM node per DSL section', () => {
    render(<DSLRenderer store={fixtureStore} slug="haree" />)
    const sections = document.querySelectorAll('[data-dsl-section]')
    expect(sections.length).toBe(fixtureStore.brand_token!.layout_dsl!.sections.length)
  })

  it('renders the configured nav style', () => {
    render(<DSLRenderer store={fixtureStore} slug="haree" />)
    expect(document.querySelector('[data-nav="underline-tabs"]')).toBeTruthy()
  })

  it('falls back when no layout_dsl', () => {
    const store = { ...fixtureStore, brand_token: { ...fixtureStore.brand_token!, layout_dsl: null } }
    render(<DSLRenderer store={store as any} slug="haree" />)
    expect(screen.getByTestId('fallback-storefront')).toBeTruthy()
  })
})
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd storefront-ui && npm run test -- dslRenderer`
Expected: FAIL — components not found.

- [ ] **Step 4: Implement the registry** `lib/dslRegistry.ts`. Start with placeholder leaf components that satisfy the contract (real variants land in Tasks 10–14; the registry references them lazily). To keep Task 9 self-contained and green, create thin stub variant components inline here and replace their imports as later tasks add files:

```ts
import type { ComponentType } from 'react'
import type { PublicStore, LayoutSection, LayoutGlobalConfig } from '@/types/schemas'

export interface SectionProps {
  store: PublicStore
  slug: string
  variant: string
  globalConfig: LayoutGlobalConfig
  preview?: boolean
  onOpenProduct?: (id: string) => void
  props?: Record<string, unknown>
}
export interface NavProps {
  store: PublicStore
  activeCategory: string | null
  onSelect: (c: string | null) => void
}
export interface CardProps {
  product: PublicStore['products'][number]
  slug: string
  cornerRadius: LayoutGlobalConfig['corner_radius']
  preview?: boolean
  onOpen?: (id: string) => void
}

// Registries are filled by Tasks 10-14. Keys MUST match the Zod enums exactly.
export const SECTION_REGISTRY: Record<string, Record<string, ComponentType<SectionProps>>> = {
  hero: {}, product_grid: {}, banner: {}, story: {},
}
export const CARD_REGISTRY: Record<string, ComponentType<CardProps>> = {}
export const NAV_REGISTRY: Record<string, ComponentType<NavProps>> = {}
```

- [ ] **Step 5: Implement `DSLSection.tsx`**

```tsx
'use client'
import type { LayoutSection, LayoutGlobalConfig, PublicStore } from '@/types/schemas'
import { SECTION_REGISTRY } from '@/lib/dslRegistry'

export function DSLSection({ section, store, slug, globalConfig, preview, onOpenProduct }: {
  section: LayoutSection; store: PublicStore; slug: string
  globalConfig: LayoutGlobalConfig; preview?: boolean; onOpenProduct?: (id: string) => void
}) {
  const Comp = SECTION_REGISTRY[section.type]?.[section.variant]
  if (!Comp) return null  // normalize_dsl guarantees validity; this is belt-and-suspenders
  return (
    <div data-dsl-section data-section-type={section.type} data-variant={section.variant}>
      <Comp store={store} slug={slug} variant={section.variant}
            globalConfig={globalConfig} preview={preview}
            onOpenProduct={onOpenProduct} props={section.props} />
    </div>
  )
}
```

- [ ] **Step 6: Implement `DSLNav.tsx`** (uses `NAV_REGISTRY`, falls back to a minimal inline nav so Task 9 is green before Task 14):

```tsx
'use client'
import { useState } from 'react'
import type { PublicStore } from '@/types/schemas'
import { NAV_REGISTRY } from '@/lib/dslRegistry'

export function DSLNav({ store, navStyle }: { store: PublicStore; navStyle: string }) {
  const [active, setActive] = useState<string | null>(null)
  const Comp = NAV_REGISTRY[navStyle]
  if (Comp) {
    return <div data-nav={navStyle}><Comp store={store} activeCategory={active} onSelect={setActive} /></div>
  }
  return (
    <nav data-nav={navStyle} className="flex gap-3 px-5 py-3 text-sm">
      <button onClick={() => setActive(null)}>All</button>
      {store.categories.map((c) => (
        <button key={c} onClick={() => setActive(c)}>{c}</button>
      ))}
    </nav>
  )
}
```

- [ ] **Step 7: Implement `DSLFooter.tsx`**

```tsx
import type { PublicStore } from '@/types/schemas'
export function DSLFooter({ store }: { store: PublicStore }) {
  return (
    <footer data-dsl-footer className="text-center mt-16 py-10 text-xs font-mono" style={{ color: 'var(--s-text-subtle)' }}>
      {store.store_name} · Powered by Elevate
    </footer>
  )
}
```

- [ ] **Step 8: Implement `FallbackStorefront.tsx`** — extract the no-brand_token path from the current `LayoutRouter.tsx` (lines 144–215) verbatim into this component (same JSX, same Chip helper), exported as `FallbackStorefront`, with `data-testid="fallback-storefront"` added to the root `<main>`.

- [ ] **Step 9: Implement `DSLRenderer.tsx`**

```tsx
'use client'
import { useMemo } from 'react'
import type { PublicStore } from '@/types/schemas'
import { LayoutDSLSchema } from '@/types/schemas'
import { resolveTheme } from '@/lib/storeTheme'
import { StoreShell } from '@/components/store/StoreShell'
import { DSLSection } from './DSLSection'
import { DSLNav } from './DSLNav'
import { DSLFooter } from './DSLFooter'
import { FallbackStorefront } from './FallbackStorefront'

export function DSLRenderer({ store, slug, preview, onOpenProduct, dslOverride }: {
  store: PublicStore; slug: string; preview?: boolean
  onOpenProduct?: (id: string) => void
  dslOverride?: PublicStore['brand_token'] extends infer T ? any : never
}) {
  // dslOverride lets the builder inject a draft DSL without mutating the store.
  const parsed = useMemo(() => {
    const candidate = dslOverride ?? store.brand_token?.layout_dsl
    if (!candidate) return null
    const r = LayoutDSLSchema.safeParse(candidate)
    return r.success ? r.data : null
  }, [store.brand_token, dslOverride])

  if (!parsed || !store.brand_token) return <FallbackStorefront store={store} slug={slug} />

  const theme = resolveTheme(store)
  const hasAnnounce = parsed.sections[0]?.variant === 'announcement-bar'

  return (
    <StoreShell brandToken={store.brand_token} cssVars={theme.cssVars}>
      <div data-store={slug}>
        {!hasAnnounce && <DSLNav store={store} navStyle={parsed.global_config.nav_style} />}
        {parsed.sections.map((section, i) => (
          <DSLSection key={`${section.type}-${i}`} section={section} store={store} slug={slug}
                      globalConfig={parsed.global_config} preview={preview} onOpenProduct={onOpenProduct} />
        ))}
        <DSLFooter store={store} />
      </div>
    </StoreShell>
  )
}
```

- [ ] **Step 10: Run to verify pass**

Run: `cd storefront-ui && npm run test -- dslRenderer`
Expected: PASS (3 tests). (Sections render via `DSLSection` returning null until registries fill, BUT the test asserts `[data-dsl-section]` wrapper count — the wrapper div renders regardless. ✓)

- [ ] **Step 11: Commit**

```bash
git add storefront-ui/lib/dslRegistry.ts storefront-ui/components/storefront/DSLRenderer.tsx storefront-ui/components/storefront/DSLSection.tsx storefront-ui/components/storefront/DSLNav.tsx storefront-ui/components/storefront/DSLFooter.tsx storefront-ui/components/storefront/FallbackStorefront.tsx storefront-ui/test/fixtures.ts storefront-ui/lib/__tests__/dslRenderer.test.tsx
git commit -m "[sprint-3] DSLRenderer + section/nav routing + registry + fallback"
```

---

### Task 10: Hero section family (4 variants)

**Files:**
- Create: `storefront-ui/components/storefront/sections/hero/EditorialStackedHero.tsx` (worked exemplar)
- Create: `.../hero/FullBleedImageHero.tsx`, `MinimalWordmarkHero.tsx`, `Split5050Hero.tsx`
- Modify: `storefront-ui/lib/dslRegistry.ts` (register all 4)
- Test: `storefront-ui/components/storefront/sections/__tests__/hero.test.tsx`

**Interfaces:**
- Consumes: `SectionProps` from `dslRegistry`.
- Produces: 4 hero components registered under `SECTION_REGISTRY.hero`.

**Per-variant delta table** (all share: read `store.store_name`, `store.tagline`, `store.brand_token.colors`; root element gets `data-hero` test id; respect `prefers-reduced-motion`; mobile rules per spec §2):

| Variant | Key visual (spec §2) |
|---------|----------------------|
| `editorial-stacked` | No full-bleed image. Store name display font 10–14vw, black weight, 2 lines. Tagline mono caps wide-tracking below. Featured product image as right-half absolute bg (50% width, hidden < md). |
| `full-bleed-image` | First product image fills 100vh (60vh mobile), bottom gradient overlay, name overlaid huge, category strip pinned bottom, "N pieces" badge top-right. |
| `minimal-wordmark` | Store name only, 16–20vw (14vw mobile), color-on-color, tagline 11px mono 60% opacity. No image. |
| `split-50-50` | Two hard halves: left name+tagline+CTA, right product image/logo mark. Stacked on mobile (image 40vh top). |

- [ ] **Step 1: Write the failing smoke test** `sections/__tests__/hero.test.tsx`

```tsx
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { SECTION_REGISTRY } from '@/lib/dslRegistry'
import { fixtureStore } from '@/test/fixtures'

const HERO_VARIANTS = ['full-bleed-image', 'editorial-stacked', 'minimal-wordmark', 'split-50-50']

describe('hero family', () => {
  it('registers all 4 hero variants', () => {
    for (const v of HERO_VARIANTS) expect(SECTION_REGISTRY.hero[v]).toBeTruthy()
  })
  it.each(HERO_VARIANTS)('%s renders without throwing', (variant) => {
    const Comp = SECTION_REGISTRY.hero[variant]
    const { container } = render(
      <Comp store={fixtureStore} slug="haree" variant={variant}
            globalConfig={fixtureStore.brand_token!.layout_dsl!.global_config} />,
    )
    expect(container.querySelector('[data-hero]')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd storefront-ui && npm run test -- hero`
Expected: FAIL — registry empty.

- [ ] **Step 3: Implement the exemplar** `EditorialStackedHero.tsx`

```tsx
'use client'
import { motion, useReducedMotion } from 'framer-motion'
import type { SectionProps } from '@/lib/dslRegistry'

export function EditorialStackedHero({ store }: SectionProps) {
  const reduced = useReducedMotion()
  const featured = store.products[0]
  const c = store.brand_token!.colors
  const [l1, ...rest] = store.store_name.split(' ')
  return (
    <header data-hero className="relative overflow-hidden px-6 md:px-10 py-20 md:py-28"
            style={{ background: c.background, color: c.text }}>
      {featured?.image_url && (
        <div aria-hidden className="hidden md:block absolute top-0 right-0 h-full w-1/2 bg-cover bg-center opacity-90"
             style={{ backgroundImage: `url(${featured.image_url})` }} />
      )}
      <motion.h1
        initial={{ opacity: 0, y: reduced ? 0 : 24 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: reduced ? 0 : 0.5, ease: [0.4, 0, 0.2, 1] }}
        className="relative z-10 font-black leading-[0.92] max-w-[60%]"
        style={{ fontFamily: 'var(--s-display)', fontSize: 'clamp(2.5rem, 11vw, 9rem)' }}>
        <span className="block">{l1}</span>
        {rest.length > 0 && <span className="block">{rest.join(' ')}</span>}
      </motion.h1>
      <p className="relative z-10 mt-6 text-xs md:text-sm uppercase tracking-[0.3em]"
         style={{ fontFamily: 'var(--s-body)', color: c.text_muted }}>
        {store.tagline}
      </p>
    </header>
  )
}
```

- [ ] **Step 4: Implement the other 3 variants** following the exemplar's structure and the delta table. Each: `'use client'`, root has `data-hero`, reads `store.brand_token!.colors`, respects `useReducedMotion`, mobile rules per spec. (Full code per the table — same imports/shape as the exemplar, differing in JSX/styles.)

- [ ] **Step 5: Register all 4** — in `lib/dslRegistry.ts`, replace the empty `hero: {}` with:

```ts
import { EditorialStackedHero } from '@/components/storefront/sections/hero/EditorialStackedHero'
import { FullBleedImageHero } from '@/components/storefront/sections/hero/FullBleedImageHero'
import { MinimalWordmarkHero } from '@/components/storefront/sections/hero/MinimalWordmarkHero'
import { Split5050Hero } from '@/components/storefront/sections/hero/Split5050Hero'
// ...
  hero: {
    'editorial-stacked': EditorialStackedHero,
    'full-bleed-image': FullBleedImageHero,
    'minimal-wordmark': MinimalWordmarkHero,
    'split-50-50': Split5050Hero,
  },
```

- [ ] **Step 6: Run to verify pass**

Run: `cd storefront-ui && npm run test -- hero`
Expected: PASS (5 tests: 1 registry + 4 render).

- [ ] **Step 7: Commit**

```bash
git add storefront-ui/components/storefront/sections/hero storefront-ui/lib/dslRegistry.ts storefront-ui/components/storefront/sections/__tests__/hero.test.tsx
git commit -m "[sprint-3] hero section family (4 variants)"
```

---

### Task 11: Product-grid section family (4 variants)

**Files:**
- Create: `.../sections/product-grid/Featured2ColGrid.tsx` (exemplar), `Masonry4ColGrid.tsx`, `HorizontalScrollGrid.tsx`, `SingleSpotlightGrid.tsx`
- Modify: `lib/dslRegistry.ts`
- Test: `.../sections/__tests__/productGrid.test.tsx`

**Interfaces:**
- Consumes: `SectionProps`; `CARD_REGISTRY[globalConfig.product_card]` to render each product; `onOpenProduct`.
- Produces: 4 grids under `SECTION_REGISTRY.product_grid`. Each renders `store.products` using the configured card variant and wires `onOpen` → `onOpenProduct`.

**Delta table** (spec §2 product-grid): `masonry-4col` 4col/2col masonry, variable heights; `featured-2col` first product large left half, rest 2-col right; `horizontal-scroll` single non-wrapping row, fixed-width cards, progress bar; `single-spotlight` one product at a time, prev/next arrows, full description.

- [ ] **Step 1: Failing smoke test** `productGrid.test.tsx` — same shape as hero test: assert all 4 registered under `SECTION_REGISTRY.product_grid`, each renders a `[data-grid]` root and at least one `[data-product]` for the 2-product fixture. Include a guard test: with `CARD_REGISTRY` empty the grid must still render `[data-grid]` (cards optional until Task 12) — so grids must not throw when `CARD_REGISTRY[card]` is undefined (render a minimal inline card fallback).

- [ ] **Step 2: Run to verify it fails.** `npm run test -- productGrid` → FAIL.

- [ ] **Step 3: Implement `Featured2ColGrid.tsx` exemplar**

```tsx
'use client'
import type { SectionProps } from '@/lib/dslRegistry'
import { CARD_REGISTRY } from '@/lib/dslRegistry'

export function Featured2ColGrid({ store, slug, globalConfig, onOpenProduct }: SectionProps) {
  const Card = CARD_REGISTRY[globalConfig.product_card]
  const [first, ...rest] = store.products
  const radius = globalConfig.corner_radius
  return (
    <section data-grid="featured-2col" className="px-4 md:px-8 py-12 grid gap-4 md:grid-cols-2">
      {first && (
        <button data-product onClick={() => onOpenProduct?.(first.id)}
                className="relative block w-full aspect-[3/4] overflow-hidden text-left"
                style={{ background: 'var(--s-surface)' }}>
          {first.image_url && <img src={first.image_url} alt={first.name} className="w-full h-full object-cover" />}
          <span className="absolute bottom-3 left-3 font-medium" style={{ color: 'var(--s-text)' }}>
            {first.name} · ${first.price}
          </span>
        </button>
      )}
      <div className="grid grid-cols-2 gap-4">
        {rest.map((p) =>
          Card
            ? <Card key={p.id} product={p} slug={slug} cornerRadius={radius} onOpen={onOpenProduct} />
            : <button key={p.id} data-product onClick={() => onOpenProduct?.(p.id)} className="block text-left">
                {p.name} · ${p.price}
              </button>,
        )}
      </div>
    </section>
  )
}
```

- [ ] **Step 4: Implement the other 3** per the delta table (each root `data-grid="<variant>"`, each product is a `[data-product]` button calling `onOpenProduct`). `single-spotlight` keeps local index state with prev/next.

- [ ] **Step 5: Register all 4** under `product_grid` in `dslRegistry.ts`.

- [ ] **Step 6: Run to verify pass.** `npm run test -- productGrid` → PASS.

- [ ] **Step 7: Commit**

```bash
git add storefront-ui/components/storefront/sections/product-grid storefront-ui/lib/dslRegistry.ts storefront-ui/components/storefront/sections/__tests__/productGrid.test.tsx
git commit -m "[sprint-3] product-grid section family (4 variants)"
```

---

### Task 12: Product-card family (6 variants)

**Files:**
- Create: `.../cards/HoverRevealCard.tsx` (exemplar) + `ColoredBgCard.tsx`, `EditorialHorizontalCard.tsx`, `BorderlessFloatingCard.tsx`, `PolaroidCard.tsx`, `ImageBelowTextCard.tsx`
- Modify: `lib/dslRegistry.ts`
- Test: `.../cards/__tests__/cards.test.tsx`

**Interfaces:**
- Consumes: `CardProps`.
- Produces: 6 cards in `CARD_REGISTRY`. Each: root `[data-card="<variant>"]` + `[data-product]`, click → `onOpen(product.id)`, applies `cornerRadius`, uses `var(--s-*)`.

**Delta table** = spec §3 (hover-reveal, colored-bg, editorial-horizontal, borderless-floating, polaroid, image-below-text).

- [ ] **Step 1: Failing smoke test** — assert all 6 keys present in `CARD_REGISTRY`; each renders `[data-card]`; clicking calls `onOpen` with the product id (use `user-event`).

- [ ] **Step 2: Run → FAIL.** `npm run test -- cards`

- [ ] **Step 3: Implement `HoverRevealCard.tsx` exemplar**

```tsx
'use client'
import { useState } from 'react'
import type { CardProps } from '@/lib/dslRegistry'

const RADIUS: Record<string, string> = { none: '0', sm: '4px', md: '10px', lg: '18px', full: '9999px' }

export function HoverRevealCard({ product, cornerRadius, onOpen }: CardProps) {
  const [hover, setHover] = useState(false)
  return (
    <button data-card="hover-reveal-text" data-product onClick={() => onOpen?.(product.id)}
            onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
            className="relative block w-full aspect-[3/4] overflow-hidden text-left"
            style={{ borderRadius: RADIUS[cornerRadius], background: 'var(--s-surface)' }}>
      {product.image_url && <img src={product.image_url} alt={product.name} className="w-full h-full object-cover" />}
      <div className="absolute inset-0 flex flex-col justify-end p-3 transition-opacity duration-300"
           style={{ background: 'linear-gradient(transparent, rgba(0,0,0,0.6))', opacity: hover ? 1 : 0, color: '#fff' }}>
        <span className="font-medium">{product.name}</span>
        <span className="text-sm">${product.price}</span>
      </div>
    </button>
  )
}
```

- [ ] **Step 4: Implement the other 5** per spec §3 and the delta table.

- [ ] **Step 5: Register all 6** in `CARD_REGISTRY`.

- [ ] **Step 6: Run → PASS.** `npm run test -- cards`

- [ ] **Step 7: Commit**

```bash
git add storefront-ui/components/storefront/cards storefront-ui/lib/dslRegistry.ts storefront-ui/components/storefront/cards/__tests__/cards.test.tsx
git commit -m "[sprint-3] product-card family (6 variants)"
```

---

### Task 13: Banner (3) + Story (3) section families

**Files:**
- Create: `.../sections/banner/ScrollTickerBanner.tsx`, `StaticStripBanner.tsx`, `AnnouncementBarBanner.tsx`
- Create: `.../sections/story/FullBleedTextStory.tsx`, `SplitImageStory.tsx`, `QuoteCalloutStory.tsx`
- Modify: `lib/dslRegistry.ts`
- Test: `.../sections/__tests__/bannerStory.test.tsx`

**Interfaces:** 3 banners under `SECTION_REGISTRY.banner`, 3 stories under `SECTION_REGISTRY.story`. Each root: `[data-banner="…"]` / `[data-story="…"]`. `announcement-bar` reads/writes `localStorage[`elevate-dismiss-${slug}`]` for dismissal; story variants use `store.brand_token.brand_voice`/`tagline`.

- [ ] **Step 1: Failing smoke test** — assert 3 banner + 3 story keys registered; each renders its root test id; `announcement-bar` has a dismiss button that removes it.
- [ ] **Step 2: Run → FAIL.** `npm run test -- bannerStory`
- [ ] **Step 3: Implement `ScrollTickerBanner.tsx` exemplar** (infinite marquee, 30s loop, pause on hover, accent bg / inverted text, 36px, `prefers-reduced-motion` → static). Implement the other 5 per spec §2.
- [ ] **Step 4: Register all 6.**
- [ ] **Step 5: Run → PASS.**
- [ ] **Step 6: Commit**

```bash
git add storefront-ui/components/storefront/sections/banner storefront-ui/components/storefront/sections/story storefront-ui/lib/dslRegistry.ts storefront-ui/components/storefront/sections/__tests__/bannerStory.test.tsx
git commit -m "[sprint-3] banner + story section families (6 variants)"
```

---

### Task 14: Navigation family (5 variants)

**Files:**
- Create: `.../nav/UnderlineTabsNav.tsx` (exemplar), `PillNav.tsx`, `SidebarTextNav.tsx`, `StickyTabsNav.tsx`, `MinimalTextNav.tsx`
- Modify: `lib/dslRegistry.ts` (`NAV_REGISTRY`)
- Test: `.../nav/__tests__/nav.test.tsx`

**Interfaces:** `NavProps`. 5 nav components in `NAV_REGISTRY`; each renders category buttons calling `onSelect`, root carries the variant via DSLNav's wrapper. Spec §9 deltas.

- [ ] **Step 1: Failing smoke test** — all 5 registered; each renders a button per category + an "All"; clicking calls `onSelect`.
- [ ] **Step 2: Run → FAIL.** `npm run test -- /nav/`
- [ ] **Step 3: Implement `UnderlineTabsNav.tsx` exemplar** + the other 4 per spec §9 (`sidebar-text` is a fixed left column on desktop, hamburger drawer on mobile; `sticky-tabs` uses `position: sticky; top:0`).
- [ ] **Step 4: Register all 5 in `NAV_REGISTRY`.**
- [ ] **Step 5: Run → PASS.**
- [ ] **Step 6: Commit**

```bash
git add storefront-ui/components/storefront/nav storefront-ui/lib/dslRegistry.ts storefront-ui/components/storefront/nav/__tests__/nav.test.tsx
git commit -m "[sprint-3] navigation family (5 variants)"
```

---

### Task 15: Swap Storefront → DSLRenderer + distinctness guard test

**Files:**
- Modify: `storefront-ui/components/storefront/Storefront.tsx`
- Test: `storefront-ui/lib/__tests__/distinctness.test.tsx`

**Interfaces:** `Storefront` renders `<DSLRenderer>` instead of `<LayoutRouter>`. (`LayoutRouter.tsx` is retained only as the source of `FallbackStorefront`; the cart/promo chrome it owned moves into `DSLRenderer` via `StoreShell` children — see note.)

> **Note on cart/promo chrome:** `LayoutRouter` currently renders the floating cart button, `<Cart/>`, and promo bar. Move that chrome into `DSLRenderer` (render the cart button + `<Cart/>` inside `StoreShell`, above the `data-store` div; render a promo bar when `store.promos.length > 0` unless an `announcement-bar` section already leads). This keeps cart working after the swap.

- [ ] **Step 1: Add cart/promo chrome to `DSLRenderer`** (port lines 73–98 + 59–71 of `LayoutRouter.tsx` into `DSLRenderer`, guarding the promo bar against a leading announcement-bar). Re-run `npm run test -- dslRenderer` — still green.

- [ ] **Step 2: Write the distinctness guard test** `lib/__tests__/distinctness.test.tsx`

```tsx
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { DSLRenderer } from '@/components/storefront/DSLRenderer'
import { fixtureStore, fixtureDSL } from '@/test/fixtures'
import type { LayoutDSL } from '@/types/schemas'

function signature(dsl: LayoutDSL) {
  const store = { ...fixtureStore, brand_token: { ...fixtureStore.brand_token!, layout_dsl: dsl } }
  const { container } = render(<DSLRenderer store={store as any} slug="x" />)
  return [...container.querySelectorAll('[data-dsl-section]')]
    .map((n) => `${n.getAttribute('data-section-type')}:${n.getAttribute('data-variant')}`).join('|')
    + '|' + (container.querySelector('[data-nav]')?.getAttribute('data-nav') ?? '')
}

describe('rendered distinctness', () => {
  it('different DSLs produce different rendered structural signatures', () => {
    const a = signature(fixtureDSL)
    const b: LayoutDSL = {
      ...fixtureDSL,
      sections: [
        { type: 'banner', variant: 'announcement-bar', props: {} },
        { type: 'product_grid', variant: 'horizontal-scroll', props: {} },
        { type: 'story', variant: 'quote-callout', props: {} },
      ],
      global_config: { ...fixtureDSL.global_config, nav_style: 'sidebar-text', product_card: 'colored-bg-card' },
    }
    expect(signature(b)).not.toBe(a)
  })
})
```

- [ ] **Step 3: Run to verify it fails** (if Storefront still imports LayoutRouter, this passes trivially; the meaningful failure is in Step 4). `npm run test -- distinctness`

- [ ] **Step 4: Swap in `Storefront.tsx`** — replace `import { LayoutRouter }` and `return <LayoutRouter .../>` (line 7, 72) with:

```tsx
import { DSLRenderer } from './DSLRenderer'
// ...
  return <DSLRenderer store={store} slug={slug} />
```

- [ ] **Step 5: Run all frontend tests.** `cd storefront-ui && npm run test` → all green.

- [ ] **Step 6: Manual demo check** — `docker compose up`, open `http://localhost:3000/s/haree`. Confirm a composed store renders (not the old uniform layout). Try a second store (`crest`) — confirm it looks structurally different.

- [ ] **Step 7: Commit**

```bash
git add storefront-ui/components/storefront/Storefront.tsx storefront-ui/components/storefront/DSLRenderer.tsx storefront-ui/lib/__tests__/distinctness.test.tsx
git commit -m "[sprint-3] storefront renders DSLRenderer; distinctness guard test"
```

---

### Task 16: Product Drawer slide-over + `?p=` routing

**Files:**
- Create: `storefront-ui/components/storefront/ProductDrawer.tsx`
- Modify: `storefront-ui/components/storefront/DSLRenderer.tsx` (own drawer open state; pass `onOpenProduct`)
- Modify: `storefront-ui/app/s/[slug]/page.tsx` (read `?p=` searchParam → initial open)
- Test: `storefront-ui/components/storefront/__tests__/productDrawer.test.tsx`

**Interfaces:** `<ProductDrawer product slug onClose preview? />`. Slides from right (desktop) / bottom (mobile), Framer Motion `x:'100%'→0`, 0.28s `[0.4,0,0.2,1]`. Reads brand DNA via `var(--s-*)`. "More like this" strip. Updates URL shallowly to `/s/{slug}?p={id}` (history pushState, no nav). `preview` disables add-to-cart.

- [ ] **Step 1: Failing test** — render `DSLRenderer`, click a `[data-product]`, assert `[data-product-drawer]` appears with the product name; click close → drawer gone; assert `window.location.search` contains `p=`.
- [ ] **Step 2: Run → FAIL.** `npm run test -- productDrawer`
- [ ] **Step 3: Implement `ProductDrawer.tsx`** (AnimatePresence wrapper, backdrop, brand-styled add-to-cart wired to `useCart`, "More Like This" = up to 4 same-category products).
- [ ] **Step 4: Wire into `DSLRenderer`** — add `const [openId,setOpenId]=useState<string|null>(initialProductId??null)`, pass `onOpenProduct={(id)=>{setOpenId(id); history.pushState(null,'',`/s/${slug}?p=${id}`)}}`, render `<ProductDrawer>` when `openId`. Disable body scroll while open.
- [ ] **Step 5: Wire `page.tsx`** — accept `searchParams: Promise<{p?: string}>`, pass `initialProductId` to `Storefront`→`DSLRenderer`.
- [ ] **Step 6: Run → PASS** + manual check at `/s/haree?p=<id>` opens the drawer directly.
- [ ] **Step 7: Commit**

```bash
git add storefront-ui/components/storefront/ProductDrawer.tsx storefront-ui/components/storefront/DSLRenderer.tsx storefront-ui/app/s/[slug]/page.tsx storefront-ui/components/storefront/__tests__/productDrawer.test.tsx
git commit -m "[sprint-3] product slide-over drawer + ?p= shallow routing"
```

---

## Phase 3 — Store Builder (P2 — human-in-the-loop demo moment)

### Task 17: builderStore (Zustand) reducers

**Files:**
- Create: `storefront-ui/lib/builderStore.ts`
- Test: `storefront-ui/lib/__tests__/builderStore.test.ts`

**Interfaces:** `useBuilderStore` with state `{ draftDSL, originalDSL, draftToken, isDirty, previewMode }` and actions `setFromStore(dsl, token)`, `updateSection(i, partial)`, `reorderSections(from, to)`, `addSection(s)`, `removeSection(i)`, `updateGlobalConfig(partial)`, `updateColor(key, value)`, `reset()`, `markPublished()`. `isDirty` = `JSON.stringify(draftDSL) !== JSON.stringify(originalDSL)` (also true on color/token edits).

- [ ] **Step 1: Failing test** `builderStore.test.ts`

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { useBuilderStore } from '@/lib/builderStore'
import { fixtureDSL } from '@/test/fixtures'

const token: any = { colors: { primary: '#000', accent: '#6EE7B7', background: '#fff', surface: '#eee', text: '#000', text_muted: '#999' } }

beforeEach(() => useBuilderStore.getState().reset())

describe('builderStore', () => {
  it('starts clean after setFromStore', () => {
    useBuilderStore.getState().setFromStore(fixtureDSL, token)
    expect(useBuilderStore.getState().isDirty).toBe(false)
  })
  it('reorderSections makes it dirty and swaps order', () => {
    useBuilderStore.getState().setFromStore(fixtureDSL, token)
    useBuilderStore.getState().reorderSections(0, 1)
    const s = useBuilderStore.getState()
    expect(s.isDirty).toBe(true)
    expect(s.draftDSL!.sections[0].type).toBe('product_grid')
  })
  it('updateSection changes a variant', () => {
    useBuilderStore.getState().setFromStore(fixtureDSL, token)
    useBuilderStore.getState().updateSection(0, { variant: 'minimal-wordmark' })
    expect(useBuilderStore.getState().draftDSL!.sections[0].variant).toBe('minimal-wordmark')
  })
  it('removeSection respects min 2', () => {
    useBuilderStore.getState().setFromStore(fixtureDSL, token)
    useBuilderStore.getState().removeSection(0)
    expect(useBuilderStore.getState().draftDSL!.sections.length).toBe(2) // refused below min
  })
  it('reset reverts to original', () => {
    useBuilderStore.getState().setFromStore(fixtureDSL, token)
    useBuilderStore.getState().updateColor('accent', '#FF0000')
    useBuilderStore.getState().reset()
    expect(useBuilderStore.getState().isDirty).toBe(false)
  })
})
```

- [ ] **Step 2: Run → FAIL.** `npm run test -- builderStore`
- [ ] **Step 3: Implement `builderStore.ts`** (Zustand store; `removeSection` is a no-op when length is 2; `addSection` no-op at 5; deep-clone on `setFromStore`; recompute `isDirty` after every mutator).
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit**

```bash
git add storefront-ui/lib/builderStore.ts storefront-ui/lib/__tests__/builderStore.test.ts
git commit -m "[sprint-3] builderStore draft-DSL state + reducers"
```

---

### Task 18: SectionList drag-to-reorder (@dnd-kit)

**Files:**
- Install: `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`
- Create: `storefront-ui/components/builder/SectionList.tsx`, `SectionCard.tsx`
- Test: `storefront-ui/components/builder/__tests__/sectionList.test.tsx`

**Interfaces:** `<SectionList />` reads `useBuilderStore`, renders one `SectionCard` per draft section with a drag handle (`@dnd-kit/sortable`), a variant `<select>` (per-type options from `dslRegistry`), and a remove button. On drag end → `reorderSections`. A "Modified from Qwen's recommendation" badge shows when `isDirty`.

- [ ] **Step 1: Install** `cd storefront-ui && npm install @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities`
- [ ] **Step 2: Failing test** — render with `setFromStore(fixtureDSL)`, assert a `SectionCard` per section, assert variant `<select>` lists that type's variants, changing it calls `updateSection`, clicking remove on a 3-section draft reduces to 2. (Drag is exercised via the store's `reorderSections` unit test in Task 17; here assert the keyboard sensor reorders by simulating dnd-kit's `onDragEnd` handler directly.)
- [ ] **Step 3: Run → FAIL.** `npm run test -- sectionList`
- [ ] **Step 4: Implement `SectionCard.tsx` + `SectionList.tsx`** with `DndContext`+`SortableContext`, `useSortable` per card, `KeyboardSensor`+`PointerSensor`, `arrayMove` → `reorderSections`. Export the `onDragEnd` for testability. Variant options come from a `VARIANTS_BY_TYPE` map exported from `dslRegistry` (`Object.keys(SECTION_REGISTRY[type])`).
- [ ] **Step 5: Run → PASS.**
- [ ] **Step 6: Commit**

```bash
git add storefront-ui/package.json storefront-ui/package-lock.json storefront-ui/components/builder/SectionList.tsx storefront-ui/components/builder/SectionCard.tsx storefront-ui/components/builder/__tests__/sectionList.test.tsx
git commit -m "[sprint-3] builder SectionList drag-to-reorder (@dnd-kit)"
```

---

### Task 19: Left panel — layout picker, add-section modal, color picker + brand-guard advisory

**Files:**
- Create: `storefront-ui/components/builder/BuilderLeftPanel.tsx`, `AddSectionModal.tsx`, `ColorPicker.tsx`, `AdvisoryPanel.tsx`
- Test: `storefront-ui/components/builder/__tests__/advisory.test.tsx`

**Interfaces:** `<BuilderLeftPanel store brandGuards advisoryMode />`. Layout picker = 4 cards (one per `BrandLayoutToken.style`) that call `fallback_dsl`-equivalent? No — they call `setFromStore` with a precomputed DSL fetched from backend regenerate (Task 20) OR locally swap `global_config` presets. **Decision:** layout picker swaps `global_config` presets locally (instant); "Regenerate with Qwen" is a separate button (Task 20). Color picker → `updateColor`; on accent change, compare against `brandGuards.allowed_color_palette` locally and, if outside it, render `<AdvisoryPanel>` with the matching rule's pre-written `warning_message` (Zero Qwen calls — spec §5). Advisory has Conversational/Structured modes.

- [ ] **Step 1: Failing test** `advisory.test.tsx` — given guards with `allowed_color_palette: ['#6EE7B7']` and a rule for `field:'accent'`, changing accent to `#FF0000` shows the rule's `warning_message`; changing to an allowed hex shows nothing; advisory never triggers a network call (assert `fetch` not called).
- [ ] **Step 2: Run → FAIL.** `npm run test -- advisory`
- [ ] **Step 3: Implement** the four components. `AdvisoryPanel` switches copy by `advisoryMode`. `ColorPicker` uses an `<input type="color">` + hex field. "Brand guard noted. Your choice." appears if merchant proceeds.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit**

```bash
git add storefront-ui/components/builder/BuilderLeftPanel.tsx storefront-ui/components/builder/AddSectionModal.tsx storefront-ui/components/builder/ColorPicker.tsx storefront-ui/components/builder/AdvisoryPanel.tsx storefront-ui/components/builder/__tests__/advisory.test.tsx
git commit -m "[sprint-3] builder left panel + local brand-guard advisory (zero-latency)"
```

---

### Task 20: BuilderPreview + publish (optimistic) + PUT/POST DSL endpoints

**Files:**
- Create: `storefront-ui/components/builder/BuilderPreview.tsx`
- Create: `analytics-brain/app/routers/brand.py` (`PUT` + `POST /api/brand/dsl/{slug}`)
- Modify: `analytics-brain/app/main.py` (register router)
- Modify: `storefront-ui/lib/api.ts` (`saveDsl`, `regenerateDsl`)
- Test: `storefront-ui/components/builder/__tests__/builderPreview.test.tsx`; `analytics-brain/tests/test_brand_dsl_live.py`

**Interfaces:**
- Backend `PUT /api/brand/dsl/{slug}` body = `LayoutDSL` JSON → validate with Pydantic + `normalize_dsl` → persist to `brand_profiles.brand_tokens.layout_dsl` + cache `layout_dsl:{merchant_id}` → return saved DSL. `POST /api/brand/dsl/{slug}` → regenerate via `generate_layout_dsl` → persist → return.
- `<BuilderPreview store />` renders `<DSLRenderer store dslOverride={draftDSL} preview />`, memoized so unchanged sections don't re-render; color edits update CSS vars via rAF.
- Frontend `api.saveDsl(slug, dsl)` (optimistic: apply then toast-revert on error).

- [ ] **Step 1: Backend failing live test** `test_brand_dsl_live.py` — `PUT /api/brand/dsl/haree` with a valid DSL returns 200 + the normalized DSL; with a 1-section DSL it still returns a normalized ≥2-section DSL (normalize applied); `GET /api/store/haree` then reflects the saved sections.
- [ ] **Step 2: Run → FAIL** (router not registered).
- [ ] **Step 3: Implement `app/routers/brand.py`** (auth via `get_current_merchant`, resolve merchant by slug, validate `LayoutDSL`, run `normalize_dsl(dsl.model_dump())`, write to `BrandProfileDB.brand_tokens`, commit, cache). Register in `main.py`.
- [ ] **Step 4: Run backend live test → PASS** (after `docker compose restart api`).
- [ ] **Step 5: Frontend failing test** `builderPreview.test.tsx` — render `BuilderPreview` after `setFromStore`, reorder a section, assert the preview's `[data-dsl-section]` order updates without a full remount (assert a stable element via `data-testid` persists).
- [ ] **Step 6: Implement `BuilderPreview.tsx` + `api.saveDsl/regenerateDsl`.** Run → PASS.
- [ ] **Step 7: Commit**

```bash
git add analytics-brain/app/routers/brand.py analytics-brain/app/main.py analytics-brain/tests/test_brand_dsl_live.py storefront-ui/components/builder/BuilderPreview.tsx storefront-ui/lib/api.ts storefront-ui/components/builder/__tests__/builderPreview.test.tsx
git commit -m "[sprint-3] builder preview + DSL save/regenerate endpoints (optimistic publish)"
```

---

### Task 21: brand-review page assembly + Qwen attribution

**Files:**
- Modify: `storefront-ui/app/brand-review/page.tsx`
- Test: `storefront-ui/app/__tests__/brandReview.test.tsx`

**Interfaces:** split-screen: `<BuilderLeftPanel>` (320px) + `<BuilderPreview>` (flex-1). Loads brand via `GET /onboarding/brand`, `setFromStore(brand_token.layout_dsl, brand_token)`. "✦ Qwen Recommended" badge on the unmodified layout; "Reset to Qwen" when `isDirty`; "Publish Store →" → `saveDsl` then `POST /onboarding/publish` → redirect to `/s/{slug}`.

- [ ] **Step 1: Failing test** — render the page with a mocked brand fetch; assert "✦ Qwen Recommended" badge present; after a reorder, "Reset to Qwen" appears; Publish calls `saveDsl` then publish.
- [ ] **Step 2: Run → FAIL.** `npm run test -- brandReview`
- [ ] **Step 3: Implement the page** (client component; AnimatePresence between StoreBirth handoff in Task 29 and the builder).
- [ ] **Step 4: Run → PASS** + manual: complete onboarding → land on builder → drag → publish → live store reflects changes.
- [ ] **Step 5: Commit**

```bash
git add storefront-ui/app/brand-review/page.tsx storefront-ui/app/__tests__/brandReview.test.tsx
git commit -m "[sprint-3] Store Builder page assembly + Qwen attribution badges"
```

---

## Phase 4 — Qwen Memory Loop (P3 — closes the cognitive loop, impresses judges)

### Task 22: Memory service

**Files:**
- Create: `analytics-brain/app/services/memory.py`
- Test: `analytics-brain/tests/test_memory.py`

**Interfaces:** `async get_memory(merchant_id, db, redis) -> list[MemoryEntry]` (Redis `merchant_memory:{id}` → Postgres `merchants.qwen_memory` fallback); `async write_memory(merchant_id, entry, db, redis) -> None` (append, cap last 20, write both); `build_memory_context(entries: list[MemoryEntry], limit: int = MEMORY_CONTEXT_ENTRIES) -> str`.

- [ ] **Step 1: Failing test** `test_memory.py` (pure `build_memory_context`, no DB):

```python
from datetime import datetime, timezone
from app.models.schemas import MemoryEntry
from app.services.memory import build_memory_context


def _e(action, outcome, behavior="approved"):
    return MemoryEntry(timestamp=datetime(2026, 6, 27, tzinfo=timezone.utc),
                       action_type=action, trigger="t", outcome=outcome, merchant_behavior=behavior)


def test_empty_returns_empty_string():
    assert build_memory_context([]) == ""


def test_includes_action_outcome_and_behavior():
    ctx = build_memory_context([_e("flash_sale", "8 orders, $320")])
    assert "flash_sale" in ctx and "$320" in ctx and "approved" in ctx
    assert ctx.startswith("What I know about this store:")


def test_caps_to_limit():
    entries = [_e("flash_sale", f"{i} orders") for i in range(20)]
    ctx = build_memory_context(entries, limit=8)
    assert ctx.count("\n") <= 8  # header + 8 lines max
```

- [ ] **Step 2: Run → FAIL.** `python -m pytest tests/test_memory.py -v`
- [ ] **Step 3: Implement `memory.py`** — `MEMORY_CONTEXT_ENTRIES = int(os.getenv("MEMORY_CONTEXT_ENTRIES", "8"))`; `build_memory_context` formats `[date] action: trigger → outcome (merchant: behavior)` for the last `limit`; `get_memory`/`write_memory` with Redis-first/Postgres-fallback and best-effort Redis (never raise on Redis down).
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit**

```bash
git add analytics-brain/app/services/memory.py analytics-brain/tests/test_memory.py
git commit -m "[sprint-3] qwen memory service: get/write/build_context"
```

---

### Task 23: Inject memory into decision cycle + token + attribution

**Files:**
- Modify: `analytics-brain/app/services/decision_engine.py`
- Test: `analytics-brain/tests/test_decision_memory.py`

**Interfaces:** `DECISION_PROMPT` gains a `{memory_context}` slot; `run_decision_cycle` calls `build_memory_context(await get_memory(...))`, injects it, sets `action_db.trigger_description = anomaly_desc`, and computes `estimated_tokens = len(prompt)//4` returned in the WS payload (`payload["estimated_tokens"]`, `payload["memory_count"]`).

- [ ] **Step 1: Failing test** `test_decision_memory.py` — unit-test a new pure helper `compose_decision_prompt(store_name, mood, brand_voice, rules, products, anomaly, memory_context)` that asserts the memory context appears in the prompt when non-empty and the prompt still contains the literal word `json`.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — extract `compose_decision_prompt` (testable), inject memory, add token estimate + `memory_count` to the WS payload, set `trigger_description`.
- [ ] **Step 4: Run → PASS** + `docker compose restart api`, fire a decision, confirm logs show memory context length.
- [ ] **Step 5: Commit**

```bash
git add analytics-brain/app/services/decision_engine.py analytics-brain/tests/test_decision_memory.py
git commit -m "[sprint-3] inject merchant memory into decision cycle + token/memory attribution"
```

---

### Task 24: Outcome observer

**Files:**
- Create: `analytics-brain/app/services/outcome_observer.py`
- Modify: the action-approve path (find with grep below) to call `schedule_observation`
- Test: `analytics-brain/tests/test_outcome_observer.py`

**Interfaces:** `async observe_outcome(action_id, db, redis) -> MemoryEntry` (counts attributed orders/revenue by `promo_id`, builds + writes a `MemoryEntry`); `schedule_observation(action_id, expires_at_ms)` (`asyncio.create_task` sleeping until expiry, then `observe_outcome`). Also called immediately on dismiss with `merchant_behavior='dismissed'`.

- [ ] **Step 1: Find the approve path.** `cd analytics-brain && grep -rn "approve\|APPROVED\|merchant_behavior" app/routers app/services`
- [ ] **Step 2: Failing test** — unit-test the pure `summarize_outcome(attributed_count, revenue, behavior) -> str` ("8 orders, $320 revenue" vs "no conversions") and that `observe_outcome` with a fake db/redis writes one entry with the right `action_type` and `merchant_behavior`.
- [ ] **Step 3: Run → FAIL.**
- [ ] **Step 4: Implement `outcome_observer.py`** using existing order/attribution helpers (reuse whatever the dashboard router uses to attribute revenue to a promo). Wire `schedule_observation` into approve, and a direct `observe_outcome(..., behavior='dismissed')` into dismiss.
- [ ] **Step 5: Run → PASS** + manual: approve a short flash_sale, place a test order, wait for expiry, confirm a memory entry appears via `GET /api/merchant/memory/{slug}` (Task 25).
- [ ] **Step 6: Commit**

```bash
git add analytics-brain/app/services/outcome_observer.py analytics-brain/app/routers analytics-brain/tests/test_outcome_observer.py
git commit -m "[sprint-3] outcome observer: action→outcome→memory entry"
```

---

### Task 25: Memory read endpoint + terminal "remembers N" badge

**Files:**
- Modify: `analytics-brain/app/routers/merchant.py`
- Modify: `storefront-ui/app/terminal/page.tsx`
- Test: `analytics-brain/tests/test_memory_live.py`

**Interfaces:** `GET /api/merchant/memory/{slug}` → `{ entries: MemoryEntry[], count }`. Terminal shows "Remembers N previous decisions" and per-card "~N tokens" + "✦ qwen-max" from Task 23's payload.

- [ ] **Step 1: Failing live test** — `GET /api/merchant/memory/haree` returns 200 with an `entries` array and integer `count`.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement endpoint + terminal badges** (read `payload.memory_count`/`estimated_tokens` from the agent_action WS event).
- [ ] **Step 4: Run → PASS** + manual: terminal shows the badge.
- [ ] **Step 5: Commit**

```bash
git add analytics-brain/app/routers/merchant.py storefront-ui/app/terminal/page.tsx analytics-brain/tests/test_memory_live.py
git commit -m "[sprint-3] memory read endpoint + terminal memory/token attribution"
```

---

## Phase 5 — CSS Injection + StoreBirth SSE (P4)

### Task 26: CSS generation + sanitization

**Files:**
- Create: `analytics-brain/app/services/css_gen.py`
- Modify: `analytics-brain/app/services/brand.py` (CSS folded into a `generate_brand_voice_and_guards` call OR appended to layout generation — keep within existing brand-voice work)
- Test: `analytics-brain/tests/test_css_gen.py`

**Interfaces:** `sanitize_css(css: str, slug: str) -> str` (strip `url()`, `@import`, `@keyframes`, `position:fixed`, `z-index`; keep only lines scoped to `[data-store="{slug}"]`; allow only the property allowlist); `async generate_custom_css(token, slug, *, _chat=None) -> str` (qwen-max, ≤15 rules, never raises → `""`).

- [ ] **Step 1: Failing test** `test_css_gen.py`

```python
from app.services.css_gen import sanitize_css


def test_strips_forbidden_constructs():
    css = '[data-store="haree"] .product-card { transform: scale(1.02); background: url(http://x/y.png); }\n@import "evil.css";'
    out = sanitize_css(css, "haree")
    assert "url(" not in out and "@import" not in out


def test_drops_unscoped_rules():
    css = 'body { display: none; }\n[data-store="haree"] .hero-title { letter-spacing: 0.2em; }'
    out = sanitize_css(css, "haree")
    assert "body {" not in out
    assert "letter-spacing" in out


def test_position_fixed_and_zindex_removed():
    css = '[data-store="haree"] .product-price { position: fixed; z-index: 999; opacity: 0.8; }'
    out = sanitize_css(css, "haree")
    assert "position" not in out and "z-index" not in out
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement `css_gen.py`** (line-based filter per spec §4 + property allowlist enforcement; `generate_custom_css` uses the spec §4 prompt with `[data-store="{slug}"]` selectors). Store the result into `brand_token.layout_dsl.custom_css` in the onboarding pipeline (after DSL generation in Task 7 — append a follow-up that sets `layout_dsl.custom_css = sanitize_css(await generate_custom_css(...), slug)`).
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit**

```bash
git add analytics-brain/app/services/css_gen.py analytics-brain/app/services/brand.py analytics-brain/app/routers/onboarding.py analytics-brain/tests/test_css_gen.py
git commit -m "[sprint-3] qwen CSS injection generation + sanitizer"
```

---

### Task 27: CustomCSSInjector frontend

**Files:**
- Create: `storefront-ui/components/storefront/CustomCSSInjector.tsx`
- Modify: `storefront-ui/components/storefront/DSLRenderer.tsx` (render it with `parsed.custom_css`)
- Test: `storefront-ui/components/storefront/__tests__/cssInjector.test.tsx`

**Interfaces:** `<CustomCSSInjector css slug />` injects/updates a `<style id="store-css-{slug}">`, cleans up on unmount (spec §4).

- [ ] **Step 1: Failing test** — render with `css='[data-store="haree"] .product-card{opacity:.9}'` slug `haree`; assert `document.getElementById('store-css-haree')!.textContent` contains the css; unmount → element removed; empty css → no style element.
- [ ] **Step 2: Run → FAIL.** `npm run test -- cssInjector`
- [ ] **Step 3: Implement** (the spec §4 component verbatim) + render in `DSLRenderer` inside `data-store` div.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit**

```bash
git add storefront-ui/components/storefront/CustomCSSInjector.tsx storefront-ui/components/storefront/DSLRenderer.tsx storefront-ui/components/storefront/__tests__/cssInjector.test.tsx
git commit -m "[sprint-3] scoped custom CSS injector"
```

---

### Task 28: StoreBirth SSE endpoint

**Files:**
- Modify: `analytics-brain/app/routers/brand.py` (`GET /api/brand/birth/{session_id}`)
- Test: `analytics-brain/tests/test_storebirth_live.py`

**Interfaces:** SSE (`text/event-stream`) streaming ordered `step:` events (`analyzing_logo`→…→`complete`) per spec §7, with a final `complete` carrying `{brand_token, layout_dsl}`. After `brand_token`, run `generate_layout_dsl` and the voice/CSS work concurrently (`asyncio.gather`), emitting step-start before and step-done as each resolves. No fake delays.

- [ ] **Step 1: Failing live test** — connect to `/api/brand/birth/{session}` (use `httpx` streaming), assert the stream yields a `complete` event containing `layout_dsl` within 15s for an already-generated brand (or a deterministic test session).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** the SSE generator (`StreamingResponse`, `media_type="text/event-stream"`). Reuse cached brand if present; otherwise drive the real pipeline. Each `yield f"event: step\ndata: {json}\n\n"`.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit**

```bash
git add analytics-brain/app/routers/brand.py analytics-brain/tests/test_storebirth_live.py
git commit -m "[sprint-3] StoreBirth SSE endpoint (ordered + parallel qwen steps)"
```

---

### Task 29: StoreBirth frontend animation

**Files:**
- Create: `storefront-ui/components/storefront/StoreBirth.tsx`
- Modify: the onboarding flow (incubation page) to render `<StoreBirth>` and hand off to `/brand-review` on `complete`
- Test: `storefront-ui/components/storefront/__tests__/storeBirth.test.tsx`

**Interfaces:** `<StoreBirth sessionId onComplete(payload) />`. Subscribes to the SSE endpoint (`EventSource`), shows one step at a time (150ms fade-in, 2s min, fade-out), thin progress line tracking real steps, dark `#0A0A0B` bg, model labels ("qwen-vl-max…", "qwen-max…"). On `complete` → `onComplete` → AnimatePresence to builder.

- [ ] **Step 1: Failing test** — mock `EventSource`, push `step` events then `complete`; assert step text renders and `onComplete` fires with the payload.
- [ ] **Step 2: Run → FAIL.** `npm run test -- storeBirth`
- [ ] **Step 3: Implement `StoreBirth.tsx`** (provide an injectable `eventSourceFactory` so the test can mock it).
- [ ] **Step 4: Wire into onboarding** + manual: upload logo → StoreBirth streams labeled steps → lands on builder.
- [ ] **Step 5: Run → PASS.**
- [ ] **Step 6: Commit**

```bash
git add storefront-ui/components/storefront/StoreBirth.tsx storefront-ui/app/\(onboarding\) storefront-ui/components/storefront/__tests__/storeBirth.test.tsx
git commit -m "[sprint-3] StoreBirth SSE-driven generation animation"
```

---

## Phase 6 — Demo Hardening & Documentation

### Task 30: Architecture diagram + DEVLOG + two-store demo verification

**Files:**
- Create: `docs/architecture-sprint3.md` (or update the repo architecture diagram)
- Modify: `DEVLOG.md`
- Test: manual demo dry-run

**Interfaces:** none — documentation + verification.

- [ ] **Step 1: Draw the Qwen call chain** (5+ calls) in the architecture diagram: qwen-vl-max(logo) → qwen-max(brand_token) → qwen-max(layout_dsl) → qwen-max(voice+guards+css) → qwen-max(decision cycle w/ memory) → outcome observer → memory store → next decision. Show Redis caches and the (post-hackathon) pgvector store dashed.
- [ ] **Step 2: Seed/verify two visually-distinct demo stores** (`haree` editorial + `crest` minimal-dark). Confirm side-by-side they read as different platforms. If they're too similar, the fallback seed perturbation (Task 6) or Qwen prompt (Task 7) needs a nudge — fix and re-verify.
- [ ] **Step 3: Run the full demo script (spec §14) end-to-end** locally: upload → StoreBirth → builder drag → color guard → publish → velocity spike → decision card (token + "remembers N") → approve → morph → second store. Note any P0 breakage and fix before claiming done.
- [ ] **Step 4: Write the DEVLOG entry** (Approach / Qwen calls + est. tokens / Problems / Solutions / Edge cases tested / Next) covering the whole sprint.
- [ ] **Step 5: Run the full test suites**

Run: `cd analytics-brain && python -m pytest tests -v` (live tests need `docker compose up`) and `cd storefront-ui && npm run test`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add docs/architecture-sprint3.md DEVLOG.md
git commit -m "[sprint-3] architecture diagram (5+ qwen call chain) + sprint devlog"
```

---

## Self-Review

**Spec coverage** (spec sections → tasks):
- §1 LayoutDSL schema/Zod/generation/renderer → Tasks 1, 2, 4–9.
- §2 Section components (hero/grid/banner/story) → Tasks 10, 11, 13.
- §3 Product cards (6) → Task 12.
- §4 CSS injection → Tasks 26, 27.
- §5 Store Builder → Tasks 17–21.
- §6 Memory loop (per-store) → Tasks 22–25. Cross-store RAG = documented only (Task 30) per "design now, build later".
- §7 StoreBirth SSE → Tasks 28, 29.
- §8 Product drawer → Task 16.
- §9 Nav variants (5) → Task 14.
- §10 Qwen attribution UI → Tasks 21 (builder badges), 23/25 (terminal), 29 (StoreBirth labels), 30 (diagram).
- §11 DB changes → Tasks 1, 3 (layout_dsl folded into brand_tokens JSONB — documented deviation, no new column).
- §12 API endpoints → Tasks 20 (dsl POST/PUT), 25 (memory GET), 28 (birth SSE). `POST /api/merchant/memory` is internal → folded into Task 24's `write_memory` (no public route needed; documented).
- §13 File plan → covered across phases.
- §14 Demo flow → Task 30 dry-run.
- §15 Out of scope → respected (cross-store RAG, accounts, etc. not built).
- Open questions 1–7 → resolved in the Architecture Review table.

**Placeholder scan:** logic-heavy tasks carry full code; repetitive component families carry a full exemplar + per-variant delta table + a smoke test enforcing every registered variant renders. No "TODO/handle edge cases" left as the actual deliverable.

**Type consistency:** `coerce_variant(SectionType, str)->str`, `normalize_dsl(dict)->LayoutDSL`, `fallback_dsl_from_token(BrandToken)->LayoutDSL`, `generate_layout_dsl(...)->LayoutDSL` are used consistently. Frontend `SectionProps`/`CardProps`/`NavProps` defined once in `dslRegistry.ts` and consumed by every variant. `build_memory_context(list[MemoryEntry], limit)->str` consistent across Tasks 22–23. `SECTION_REGISTRY`/`CARD_REGISTRY`/`NAV_REGISTRY` names consistent across Tasks 9–14, 18.

**Known deviations from spec (intentional, flagged):** (a) `layout_dsl` stored inside existing `brand_tokens` JSONB instead of a new `brand_profiles.layout_dsl` column — avoids an unused-Alembic dependency, simpler, same data. (b) No public `POST /api/merchant/memory` route — memory writes are internal-only via the observer. (c) Outcome observer uses an in-process `asyncio` timer (demo-appropriate), with the durable-queue path documented, not built.

---

**Plan complete and saved to `docs/superpowers/plans/sprint-3-implementation-plan.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
