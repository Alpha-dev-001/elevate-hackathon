# Elevate Sprint 3 — Storefront Architecture Spec
> Written for Opus review. Do not implement until Opus has reviewed and approved an
> implementation plan derived from this spec. This document is the architectural
> source of truth for sprint 3.

---

## What This Sprint Builds

The storefront in sprint 2 is 1/10. Every store looks structurally identical. The AI brain
exists but is invisible to store visitors. The merchant has no control after brand generation.

Sprint 3 makes Elevate real:

1. **LayoutDSL** — Qwen composes a unique store layout per brand. 40 stores → 40 genuinely
   distinct stores. Not color variations. Structural differences: different sections, different
   arrangements, different interaction patterns.

2. **Store Builder** — a live split-screen where merchants see Qwen's recommendation and
   can override it. Human-in-the-loop. Drag sections. Change colors. Preview updates instantly.

3. **Qwen Memory Loop** — the missing cognitive closure. After actions are executed and
   outcomes observed, Qwen writes a memory entry. Next decision cycle, Qwen reads what worked.
   Over time, Qwen gets genuinely smarter per store.

4. **CSS Injection** — Qwen generates a scoped CSS block per store. Micro-behaviors that
   CSS vars cannot express. Letter-spacing, hover transforms, transition timing. Every store
   has unique visual personality at this level of detail.

5. **Product Drawer** — slide-over detail view. No page navigation. Instant. Full brand DNA.

6. **StoreBirth SSE** — streaming text during brand generation that makes Qwen's work visible.

---

## Hackathon Context (Non-Negotiable)

**Deadline:** July 9, 2026 @ 2:00pm PDT
**Track:** Track 4 — Autopilot Agent

**Scoring:**
- 30% Technical Depth — *sophisticated* Qwen API usage, algorithmic innovation
- 30% Innovation & AI Creativity — architecture quality, modularity, scalability
- 25% Problem Value & Impact — real-world relevance, productization potential
- 15% Presentation & Documentation — demo clarity, architecture diagram

**What "sophisticated Qwen usage" means to judges:**
Not "we called the API." Multiple Qwen models doing distinct, non-trivial work in a
continuous loop. The Qwen call chain must be visible in the demo and the architecture diagram.

**Current Qwen calls:** 2 (VL logo analysis + Max brand generation)
**Sprint 3 Qwen calls:** 5+ (VL + Max brand + Max layout DSL + Max decision cycle with memory + outcome observer)

**Track 4 requirement:** "human-in-the-loop checkpoints at critical decisions"
Our checkpoints: store builder drag-to-reorder, color change brand guard, option card approve/dismiss, memory-informed future decisions.

---

## Architecture Overview

```
Logo Upload (OSS presigned PUT)
    │
    ▼
qwen-vl-max: analyze_logo()
    │ → LogoAnalysis (geometry, palette, mood, spatial_personality)
    ▼
qwen-max: generate_brand_token()
    │ → BrandToken (colors, typography, layout hints, mood, industry_hint)
    ▼
qwen-max: generate_layout_dsl()
    │ → LayoutDSL (sections[], global config, product_card variant)
    ▼
qwen-max: generate_brand_voice_and_guards()
    │ → BrandGuardRules + brand_voice + CSS injection block
    ▼
StoreBirth SSE stream → frontend animates each step
    │
    ▼
Store Builder (split-screen)
    │ Left: controls (layout picker, section list, color tweaker, advisory toggle)
    │ Right: live preview (same components, preview=true)
    │ Drag-to-reorder = human overrides Qwen's section arrangement
    │ Color change = brand guard fires (conversational or structured mode)
    ▼
Merchant clicks Publish
    │
    ▼
SystemState initialized in Redis from brand_token + layout_dsl
Store goes live at /s/{slug}
    │
    ▼
Customer browsing → behavior events → Redis
    │
    ▼
Anomaly detected (deterministic threshold)
    │
    ▼
qwen-max: run_decision_cycle()
    │ Reads: store state + merchant memory (what worked before)
    │ → AgentAction (flash_sale | layout_morph | scarcity_price | copy_rewrite | recovery_offer)
    ▼
Option card surfaces in merchant terminal
    │
    ▼
Merchant approves → delta executed → storefront morphs
    │
    ▼
Outcome observer (background task, runs after promo expires)
    │ Queries attribution data for that action
    │ Writes memory entry: action type, trigger, outcome, merchant behavior
    │ Upserts to merchants.qwen_memory JSONB + Redis
    ▼
Next decision cycle reads this memory → Qwen improves
```

---

## 1. LayoutDSL

### Schema (Python — add to schemas.py)

```python
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
    variant: str  # validated against type's enum at generation time
    props: dict[str, Any] = {}

class LayoutGlobalConfig(BaseModel):
    nav_style: NavStyle
    product_card: ProductCardVariant
    color_mode: Literal["light", "dark", "auto"] = "auto"
    corner_radius: Literal["none", "sm", "md", "lg", "full"] = "md"
    density: Literal["sparse", "normal", "dense"] = "normal"

class LayoutDSL(BaseModel):
    sections: list[LayoutSection]  # 2-5 sections
    global_config: LayoutGlobalConfig
    custom_css: str = ""  # Qwen-generated, sanitized CSS block

# Add to BrandToken:
class BrandToken(BaseModel):
    # ... existing fields ...
    layout_dsl: LayoutDSL | None = None  # None until generate_layout_dsl() runs
```

### Zod mirror (schemas.ts) — must match exactly

```typescript
export const LayoutSectionSchema = z.object({
  type: z.enum(['hero', 'product_grid', 'banner', 'story']),
  variant: z.string(),
  props: z.record(z.any()).default({}),
})

export const LayoutGlobalConfigSchema = z.object({
  nav_style: z.enum(['underline-tabs', 'pill-nav', 'sidebar-text', 'sticky-tabs', 'minimal-text']),
  product_card: z.enum(['hover-reveal-text', 'colored-bg-card', 'editorial-horizontal',
                        'borderless-floating', 'polaroid-card', 'image-below-text']),
  color_mode: z.enum(['light', 'dark', 'auto']).default('auto'),
  corner_radius: z.enum(['none', 'sm', 'md', 'lg', 'full']).default('md'),
  density: z.enum(['sparse', 'normal', 'dense']).default('normal'),
})

export const LayoutDSLSchema = z.object({
  sections: z.array(LayoutSectionSchema).min(2).max(5),
  global_config: LayoutGlobalConfigSchema,
  custom_css: z.string().default(''),
})
```

### generate_layout_dsl() — Qwen-Max call

**Input:** BrandToken + store_name + category + product_count
**Output:** LayoutDSL

**Prompt strategy:**
- Tell Qwen what each section type does and what variants exist
- Tell Qwen to assemble 2-5 sections that feel cohesive for this brand's mood + industry
- Tell Qwen the global config options and what each means aesthetically
- Ask for JSON output matching LayoutDSL schema
- Include coercion fallbacks (same pattern as `_STYLE_COERCE` in brand.py)
- Cache in Redis key: `layout_dsl:{merchant_id}` (TTL: forever, invalidated on re-generate)

**Coercion map needed:** Qwen will hallucinate variant names. Maintain a `_DSL_COERCE` dict
mapping near-miss values to valid ones. Log WARNINGs for unmapped values, fall back gracefully.

**Storage:** `brand_profiles.layout_dsl JSONB` column (new migration needed)

### DSL Renderer (frontend)

**`components/storefront/DSLRenderer.tsx`** — the new top-level storefront component.
Replaces LayoutRouter.tsx. Reads `store.brand_token.layout_dsl` and composes the store:

```tsx
function DSLRenderer({ store, slug }) {
  const dsl = store.brand_token?.layout_dsl
  if (!dsl) return <FallbackStorefront store={store} slug={slug} />

  return (
    <StoreShell brandToken={store.brand_token} cssVars={resolveTheme(store)}>
      <CustomCSSInjector css={dsl.custom_css} slug={slug} />
      <DSLNav store={store} navStyle={dsl.global_config.nav_style} />
      {dsl.sections.map((section, i) => (
        <DSLSection key={i} section={section} store={store} slug={slug}
                    globalConfig={dsl.global_config} />
      ))}
      <DSLFooter store={store} />
    </StoreShell>
  )
}
```

**`components/storefront/DSLSection.tsx`** — routes section.type + section.variant to the
right component:

```tsx
function DSLSection({ section, store, slug, globalConfig }) {
  switch (section.type) {
    case 'hero':       return <HeroSection variant={section.variant} store={store} {...section.props} />
    case 'product_grid': return <ProductGridSection variant={section.variant} store={store}
                                  slug={slug} cardVariant={globalConfig.product_card} {...section.props} />
    case 'banner':     return <BannerSection variant={section.variant} store={store} {...section.props} />
    case 'story':      return <StorySection variant={section.variant} store={store} {...section.props} />
    default:           return null
  }
}
```

---

## 2. Section Components

Each section type is a directory: `components/storefront/sections/hero/`,
`product-grid/`, `banner/`, `story/`.

### Hero Section Variants

**`full-bleed-image`**
- Image fills 100vh. Overlay gradient from bottom. Store name in huge display type overlaid.
- Category nav as thin horizontal strip pinned to bottom of hero.
- Product count badge: "24 pieces" in top-right corner.
- Mobile: image 60vh, text below.

**`editorial-stacked`**
- No full-bleed image. Pure typography moment.
- Store name in display font, 10–14vw, bold/black weight, stacked on two lines.
- Tagline in small mono caps below, wide letter-spacing.
- Featured product image as a right-half background (CSS position: absolute, 50% width).
- Mobile: image hidden, full-width text.

**`minimal-wordmark`**
- Just the store name. Enormous. 16–20vw. Center or left-anchored.
- No image. Color is the only visual element (brand background + text color).
- Tagline in 11px mono, 60% opacity.
- Only appropriate for brands with strong visual brand voice (Qwen decides).
- Mobile: 14vw.

**`split-50-50`**
- Exactly two halves. Left: store name + tagline + CTA button. Right: product image or logo mark.
- Clean hard edge between halves, no gradient.
- Mobile: stacked, image 40vh on top.

### Product Grid Section Variants

**`masonry-4col`**
- Pinterest/editorial grid. 4 columns desktop, 2 mobile.
- Variable card heights (image aspect ratio preserved, not cropped).
- Cards use `global_config.product_card` variant.
- No gap between masonry columns creates seamless tile effect.

**`featured-2col`**
- First product takes the left half (large). Remaining products fill right half in 2 columns.
- First product image: full-bleed within its container. Name + price overlaid.
- Right column cards: standard card variant.
- Mobile: featured product full-width, then 2-col grid.

**`horizontal-scroll`**
- Single row. Cards do not wrap. Horizontal scroll on overflow.
- Mobile-native pattern — feels like an app, not a webpage.
- Cards: fixed width (280px desktop, 200px mobile). Aspect-ratio: 3/4.
- Scroll indicator: thin progress bar below the strip.

**`single-spotlight`**
- One product at a time. Full-width treatment.
- Large product image (left), editorial copy block (right).
- Previous/next navigation arrows.
- Product description displayed in full — not truncated.
- Mobile: stacked.
- Only appropriate for stores with few (1-10) products.

### Banner Section Variants

**`scroll-ticker`**
- Infinite horizontal scroll. Repeating text separated by · or ✦.
- Text: store tagline, or "NEW DROP", or promo copy.
- Speed: 30s loop. Pause on hover.
- Background: brand accent. Text: brand background (inverted).
- Height: 36px.

**`static-strip`**
- Full-width color block. 80px height.
- Centered text + CTA button.
- Background: brand primary or accent.
- Mobile: text wraps, 100px height.

**`announcement-bar`**
- Dismissible top bar. Pinned to top of page (above nav).
- Promo code displayed: "Use LAUNCH15 for 15% off"
- X button to dismiss. Stores dismissed state in localStorage.
- Background: brand accent. Height: 44px.

### Story Section Variants

**`full-bleed-text`**
- Full-width background (brand surface color). Large padding.
- Brand voice paragraph. 24px body text. Max-width 680px, centered.
- Optional: store tagline as large pull-quote above the paragraph.
- No image. Typography is the design element.

**`split-image-story`**
- Image left (40%), text right (60%). Or reversed based on `props.image_side`.
- Story text: brand voice. 18px, generous line-height.
- Optional: founder name attribution.
- Mobile: image 200px full-width, text below.

**`quote-callout`**
- Large decorative quotation mark (brand accent color, 120px).
- Founder/brand quote in display font. 32px.
- Attribution: "— [store_name] founder" or brand tagline.
- Background: brand surface. Full-width.

---

## 3. Product Card Variants

`components/storefront/cards/` — one file per variant.

**`hover-reveal-text`** (SSENSE, Rick Owens)
- Image fills card. No text visible at rest.
- On hover: semi-transparent overlay fades in (300ms). Name + price appear.
- Add-to-cart on hover (or tap on mobile).
- Card: no border, no border-radius if `corner_radius: none`.

**`colored-bg-card`** (Glossier, Fenty)
- Brand accent or primary as card background. No white.
- Image: object-contain (product floats on color, not cropped).
- Name + price below in brand text color.
- No shadow. Strong color contrast is the visual punch.

**`editorial-horizontal`** (Net-a-Porter, Mr Porter)
- Card is landscape: image left 45%, text right 55%.
- Name in display font. Price in mono. Short description visible.
- Thin bottom border only (no full card border).
- Mobile: portrait (image top).

**`borderless-floating`** (Céline, Bottega)
- No card container at all. Image floats directly on page background.
- Name and price below, left-aligned in mono.
- Extreme whitespace between products.
- Hover: image scales 1.03, 400ms ease.

**`polaroid-card`** (independent boutiques, Etsy premium)
- White card with thick white border-bottom (40px).
- Store name or product category in small italic script at bottom.
- Subtle drop shadow.
- Image: 4:3 aspect-ratio, object-cover.

**`image-below-text`** (editorial, lookbook)
- Text above image. Category label in small caps. Product name large. Price small.
- Image below: full card width, 3:4 aspect-ratio.
- Feels like a magazine layout entry.

---

## 4. CSS Injection

Qwen generates this at brand generation time as part of `generate_brand_voice_and_guards()`.
It is part of the LayoutDSL (`layout_dsl.custom_css`).

**What Qwen can express in CSS that CSS vars cannot:**
- Per-element transition timing (some stores have snappier hover, others slower)
- Letter-spacing values for specific elements beyond what the token covers
- Custom hover transforms (translateY vs scale vs rotate)
- Text-decoration patterns (underlines, strikethroughs on sale prices)
- Scroll behavior

**Prompt for Qwen:**
```
Based on the brand's mood ({mood}) and spatial personality ({spatial_personality}),
generate a small CSS block (max 15 rules) that expresses this brand's micro-interaction
character. Use only these selectors:
  [data-store="{slug}"] .product-card
  [data-store="{slug}"] .product-card:hover
  [data-store="{slug}"] .hero-title
  [data-store="{slug}"] .section-banner
  [data-store="{slug}"] .product-price

Only use these properties: transform, transition, letter-spacing, line-height,
text-decoration, opacity, border-radius, box-shadow.
No external url(), no position: fixed, no z-index, no animation keyframes.
Return ONLY the CSS. No explanation.
```

**Sanitization (Python, before storage):**
```python
import re

ALLOWED_PROPS = {'transform', 'transition', 'letter-spacing', 'line-height',
                 'text-decoration', 'opacity', 'border-radius', 'box-shadow'}

def sanitize_css(css: str, slug: str) -> str:
    # Strip anything not scoped to this store
    allowed_selector_prefix = f'[data-store="{slug}"]'
    lines = css.strip().split('\n')
    # Remove any line containing url(), @import, @keyframes, position: fixed
    forbidden = re.compile(r'url\(|@import|@keyframes|position\s*:\s*fixed|z-index', re.I)
    safe_lines = [l for l in lines if not forbidden.search(l)]
    return '\n'.join(safe_lines)
```

**Frontend injection (`CustomCSSInjector.tsx`):**
```tsx
'use client'
import { useEffect } from 'react'

export function CustomCSSInjector({ css, slug }: { css: string; slug: string }) {
  useEffect(() => {
    if (!css) return
    const id = `store-css-${slug}`
    let el = document.getElementById(id) as HTMLStyleElement | null
    if (!el) {
      el = document.createElement('style')
      el.id = id
      document.head.appendChild(el)
    }
    el.textContent = css
    return () => el?.remove()
  }, [css, slug])
  return null
}
```

---

## 5. Store Builder

### Route

`/brand-review` — enhanced from current brand preview page.
Also accessible: merchant terminal → "Customize Store" button → opens `/brand-review?slug=x`.

### State

The builder works with a **draft DSL** — a local copy of the published DSL that the merchant
edits. Changes are saved to draft state only. "Publish Changes" sends the draft to the backend.

```typescript
// lib/builderStore.ts (Zustand)
interface BuilderStore {
  draftDSL: LayoutDSL | null
  originalDSL: LayoutDSL | null  // Qwen's recommendation, never mutated
  draftToken: BrandToken | null
  isDirty: boolean  // draft !== original
  previewMode: boolean

  setDraftDSL: (dsl: LayoutDSL) => void
  updateSection: (index: number, update: Partial<LayoutSection>) => void
  reorderSections: (from: number, to: number) => void
  addSection: (section: LayoutSection) => void
  removeSection: (index: number) => void
  updateGlobalConfig: (update: Partial<LayoutGlobalConfig>) => void
  updateColor: (key: keyof BrandColors, value: string) => void
  publish: () => Promise<void>
  reset: () => void  // revert to original Qwen recommendation
}
```

### Layout

```
/brand-review
├── Left panel (320px fixed)
│   ├── Header: "Your Store" + "Qwen's recommendation" badge
│   ├── Layout picker (4 cards with thumbnail previews)
│   ├── Sections list (drag handles via @dnd-kit/core)
│   │   └── Each section: type label + variant dropdown + remove button
│   ├── + Add Section button → modal with section type picker
│   ├── Colors section
│   │   ├── Primary picker + preview swatch
│   │   ├── Accent picker + brand guard indicator
│   │   └── Background picker
│   ├── Advisory style toggle (Conversational / Structured)
│   └── Footer: [Reset to Qwen] [Publish Store →]
│
└── Right panel (flex-1)
    ├── "Preview" badge (top bar, fixed)
    └── <DSLRenderer store={previewStore} preview={true} />
        (previewStore = store with draftDSL + draftToken applied)
```

### Drag-to-reorder

Use `@dnd-kit/core` + `@dnd-kit/sortable`. When a section is dragged:
1. `reorderSections(from, to)` updates draftDSL.sections order
2. `isDirty` becomes true
3. "Modified from Qwen's recommendation" badge appears next to section list header
4. Preview re-renders with new order instantly

This is the **human-in-the-loop** moment. Make it visible.

### Brand Guard in the Builder

When accent color changes:
1. Compare new color against `brand_guard_rules.rules` (pre-stored by Qwen)
2. If a matching rule exists: show advisory inline below the color picker
3. Advisory shows in selected mode (conversational or structured)
4. Merchant can still change the color — this is never a block, only advice
5. If merchant proceeds: "Brand guard noted. Your choice." — logged in merchant memory

No Qwen call at interaction time. Zero latency. All copy pre-generated at brand creation.

### Preview Sync

The preview is not an iframe. It is `<DSLRenderer>` rendered in the right panel with:
- `preview={true}` prop passed down to all components
- Cart/checkout interactions disabled in preview mode
- "You are previewing" indicator in the preview panel header

When any builder state changes:
```
builderStore.draftDSL changes
→ previewStore memo recomputes (draftDSL + draftToken merged onto base store)
→ DSLRenderer re-renders with new draftDSL
→ sections reorder, colors update, variants swap — instant
```

No debounce. No API call. Pure React state → render.

---

## 6. Qwen Memory Loop

### Per-Store Memory (Hackathon Scope)

**Schema (add to merchants table):**
```python
# New column: qwen_memory JSONB
# New SQLAlchemy model field:
class Merchant(Base):
    # ... existing fields ...
    qwen_memory: dict = Column(JSONB, nullable=False, server_default='{"entries": []}')
```

**Memory entry shape:**
```python
class MemoryEntry(BaseModel):
    timestamp: datetime
    action_type: str              # flash_sale, layout_morph, etc.
    trigger: str                  # "34 views in 28s for face wash"
    outcome: str                  # "8 orders, $320, +23% conversion lift"
    merchant_behavior: str        # "approved" | "dismissed" | "approved-then-dismissed"
    notes: str = ""               # anything notable Qwen should remember
```

**Redis key:** `merchant_memory:{merchant_id}` — serialized list of last 20 entries.
Backed by Postgres `merchants.qwen_memory` for persistence.

**Injected into decision_cycle prompt:**
```python
def build_memory_context(merchant_id: str) -> str:
    entries = get_memory(merchant_id)  # Redis → Postgres fallback
    if not entries:
        return ""
    lines = [f"[{e.timestamp.date()}] {e.action_type}: {e.trigger} → {e.outcome} (merchant: {e.merchant_behavior})"
             for e in entries[-10:]]  # Last 10 entries only
    return "What I know about this store:\n" + "\n".join(lines)
```

### Outcome Observer

Background task triggered when a promo expires (`promo.expires_at` passes)
or when merchant dismisses an active promo from the terminal:

```python
async def observe_outcome(action_id: int, db: AsyncSession):
    """Called after action completes. Writes memory entry."""
    action = await get_agent_action(action_id, db)
    # Query orders attributed to this action's promo
    attributed = await count_attributed_orders(action.promo_id, db)
    revenue = await sum_attributed_revenue(action.promo_id, db)

    entry = MemoryEntry(
        timestamp=datetime.utcnow(),
        action_type=action.action_type,
        trigger=action.trigger_description,
        outcome=f"{attributed} orders, ${revenue:.0f} revenue" if attributed > 0 else "no conversions",
        merchant_behavior=action.merchant_behavior,  # new field on AgentAction
    )
    await write_memory(action.merchant_id, entry, db)
```

### Cross-Store RAG (Architecture-Planned, Post-Hackathon)

Design it now. Implement after hackathon.

**Schema:** `action_outcomes` table with `embedding vector(1536)` column (pgvector).
**Embed:** `{action_type} for {industry_hint} brand, {trigger}, outcome: {outcome}`
**Query:** At decision time, find top-5 similar past outcomes across all stores.
**Inject:** "What worked for similar stores: ..." block in decision prompt.

Document this in the architecture diagram. Show the vector store in the system design.
Judges see the vision even if the full implementation runs post-hackathon.

---

## 7. StoreBirth SSE Sequence

SSE endpoint: `GET /api/brand/birth/{session_id}`

The sequence (steps streamed as Server-Sent Events):
```
step: analyzing_logo    → "Reading your logo's visual geometry..."
step: extracting_color  → "Identifying color temperature and relationships..."
step: reading_mood      → "Sensing the brand's spatial personality..."
step: generating_token  → "Defining your palette and typography..."
step: composing_layout  → "Composing your store's unique layout..."
step: writing_voice     → "Writing your brand voice and guard rules..."
step: generating_css    → "Refining your store's micro-interactions..."
step: complete          → { brand_token: {...}, layout_dsl: {...} }
```

**Frontend (`StoreBirth.tsx`):**
- Full-screen dark background (#0A0A0B)
- Centered animated text (one step at a time, fade-in/out)
- Progress indicator: thin line growing from left to right
- Each step text appears with a 150ms fade-in, stays 2s minimum, fades out
- On `complete`: transition to Store Builder (Framer Motion AnimatePresence)

**No fake delays.** Each SSE event is sent when the real Qwen call completes that step.
If Qwen is fast, the sequence moves fast. The progress bar tracks real progress.

---

## 8. Product Detail Slide-Over Drawer

**Trigger:** Click any product card in the DSL-rendered store.
**URL:** Shallow update to `/s/{slug}?p={product_id}` (supports direct links, back button).
**Data source:** Product is already in `store.products[]` — no additional API call needed.

### Layout

```
Desktop:
┌─────────────────────────────────────────────────────┐
│  [Storefront behind, scrolling disabled]             │
│  ┌─────────────────────────────────────────────┐   │
│  │  [Full-bleed image — 50% width]  │  [Info]  │   │
│  │                                   │          │   │
│  │                                   │  Name    │   │
│  │                                   │  $xx.xx  │   │
│  │                                   │          │   │
│  │                                   │  Desc.   │   │
│  │                                   │          │   │
│  │                                   │  Qty [1] │   │
│  │                                   │          │   │
│  │                                   │  [Add]   │   │
│  │                                   │          │   │
│  └─────────────────────────────────────────────┘   │
│  [More Like This: 4-product horizontal strip]        │
└─────────────────────────────────────────────────────┘

Mobile: Full-screen drawer from bottom. Image top (40vh). Info below. Scrollable.
```

### Animation

```tsx
// Framer Motion
initial={{ x: '100%' }}        // slides from right (desktop)
animate={{ x: 0 }}
exit={{ x: '100%' }}
transition={{ duration: 0.28, ease: [0.4, 0, 0.2, 1] }}
```

### Brand DNA

The drawer reads the store's `brand_token` and applies:
- Font family from `var(--s-display)` and `var(--s-body)`
- Colors from `var(--s-*)` CSS vars (already set by StoreShell)
- Corner radius from `brand_token.layout_dsl.global_config.corner_radius`
- Add-to-cart button styled in brand accent

---

## 9. Navigation Variants

`components/storefront/nav/` — one component per nav style.

**`underline-tabs`** (editorial)
- Horizontal list of categories. Active = thin underline (2px, brand accent). No background.
- Hover: underline fades in (150ms).
- Desktop: full horizontal. Mobile: horizontal scroll.

**`pill-nav`** (bold, warm-craft)
- Rounded pill buttons. Active = filled (brand accent BG, white text). Inactive = ghost.
- Desktop: inline. Mobile: scroll row.

**`sidebar-text`** (minimal-dark)
- Vertical list on the left side. Categories as plain uppercase text links.
- Active: brand accent color. Inactive: muted text.
- Desktop: fixed sidebar. Mobile: hidden behind hamburger → slide-in drawer.

**`sticky-tabs`** (bold-grid, dense)
- Tabs stick to top of page on scroll (position: sticky, top: 0).
- Active tab: solid background (brand surface-2). Indicator line below.
- Dense, tight spacing.

**`minimal-text`** (minimal, luxury)
- No visual chrome. Just plain text links, comma-separated or space-separated.
- Hover: color shift only.
- Active: brand accent.

---

## 10. Qwen Attribution UI

Judges scoring "Sophisticated Qwen usage" need to see Qwen working.

**In StoreBirth:** Streaming text with model labels. "qwen-vl-max analyzing..." / "qwen-max composing..."

**In Store Builder:**
- `✦ Qwen Recommended` badge on the default layout choice
- `✦ Generated by Qwen` caption on brand color swatches
- "Reset to Qwen's recommendation" button (if merchant has modified sections)

**In terminal:**
- `✦ qwen-max` label on each option card header (small, 9px mono)
- Estimated tokens per cycle: "~2,400 tokens" in terminal header
- Memory context indicator: "Remembers 7 previous decisions" small badge

**In architecture diagram (required submission):**
Draw every Qwen call with model name, input, output, and caching layer.

---

## 11. Database Changes Needed

New columns/tables (Alembic migrations):

```sql
-- Add to brand_profiles
ALTER TABLE brand_profiles ADD COLUMN layout_dsl JSONB;

-- Add to merchants
ALTER TABLE merchants ADD COLUMN qwen_memory JSONB NOT NULL DEFAULT '{"entries": []}';

-- Add to agent_actions
ALTER TABLE agent_actions ADD COLUMN merchant_behavior VARCHAR(32);
-- values: 'approved', 'dismissed', 'approved_then_modified'
ALTER TABLE agent_actions ADD COLUMN trigger_description TEXT;

-- Post-hackathon (design now, implement later)
-- CREATE TABLE action_outcomes (
--   id SERIAL PRIMARY KEY,
--   merchant_id UUID,
--   embedding vector(1536),
--   outcome_summary TEXT,
--   created_at TIMESTAMPTZ DEFAULT NOW()
-- );
-- CREATE INDEX ON action_outcomes USING ivfflat (embedding vector_cosine_ops);
```

---

## 12. New API Endpoints Needed

```
POST   /api/brand/dsl/{slug}            regenerate layout DSL for a store
PUT    /api/brand/dsl/{slug}            save merchant's modified DSL (draft → published)
GET    /api/brand/birth/{session_id}    SSE stream for StoreBirth sequence
GET    /api/merchant/memory/{slug}      read merchant's Qwen memory (for debugging/terminal)
POST   /api/merchant/memory/{slug}      write memory entry (internal, outcome observer)
```

---

## 13. File Plan

### Backend (analytics-brain)

**New/modified:**
- `app/models/schemas.py` — LayoutDSL, LayoutSection, LayoutGlobalConfig, MemoryEntry, ProductCardVariant, NavStyle
- `app/models/db_models.py` — layout_dsl column on BrandProfileDB, qwen_memory + merchant_behavior on respective tables
- `app/services/brand.py` — add `generate_layout_dsl()`, `generate_brand_voice_and_guards()` (expanded to include CSS block)
- `app/services/memory.py` — NEW: get_memory(), write_memory(), build_memory_context()
- `app/services/decision_engine.py` — inject memory context into decision prompt
- `app/services/outcome_observer.py` — NEW: observe_outcome() background task
- `app/routers/brand.py` — NEW: DSL regenerate, DSL save, StoreBirth SSE
- `app/routers/merchant.py` — memory read endpoint
- `alembic/versions/XXX_sprint3_layout_dsl_memory.py` — migration

### Frontend (storefront-ui)

**New:**
- `types/schemas.ts` — LayoutDSL, LayoutSection, LayoutGlobalConfig, etc.
- `lib/builderStore.ts` — Zustand builder state
- `components/storefront/DSLRenderer.tsx` — replaces LayoutRouter
- `components/storefront/DSLSection.tsx` — section routing
- `components/storefront/DSLFooter.tsx`
- `components/storefront/CustomCSSInjector.tsx`
- `components/storefront/sections/hero/FullBleedImageHero.tsx`
- `components/storefront/sections/hero/EditorialStackedHero.tsx`
- `components/storefront/sections/hero/MinimalWordmarkHero.tsx`
- `components/storefront/sections/hero/Split5050Hero.tsx`
- `components/storefront/sections/product-grid/Masonry4ColGrid.tsx`
- `components/storefront/sections/product-grid/Featured2ColGrid.tsx`
- `components/storefront/sections/product-grid/HorizontalScrollGrid.tsx`
- `components/storefront/sections/product-grid/SingleSpotlightGrid.tsx`
- `components/storefront/sections/banner/ScrollTickerBanner.tsx`
- `components/storefront/sections/banner/StaticStripBanner.tsx`
- `components/storefront/sections/banner/AnnouncementBarBanner.tsx`
- `components/storefront/sections/story/FullBleedTextStory.tsx`
- `components/storefront/sections/story/SplitImageStory.tsx`
- `components/storefront/sections/story/QuoteCalloutStory.tsx`
- `components/storefront/cards/HoverRevealCard.tsx`
- `components/storefront/cards/ColoredBgCard.tsx`
- `components/storefront/cards/EditorialHorizontalCard.tsx`
- `components/storefront/cards/BorderlessFloatingCard.tsx`
- `components/storefront/cards/PolaroidCard.tsx`
- `components/storefront/cards/ImageBelowTextCard.tsx`
- `components/storefront/nav/UnderlineTabsNav.tsx`
- `components/storefront/nav/PillNav.tsx`
- `components/storefront/nav/SidebarTextNav.tsx`
- `components/storefront/nav/StickyTabsNav.tsx`
- `components/storefront/nav/MinimalTextNav.tsx`
- `components/storefront/ProductDrawer.tsx` — slide-over product detail
- `components/storefront/StoreBirth.tsx` — SSE-driven brand generation animation
- `app/brand-review/page.tsx` — Store Builder page (enhanced from current)
- `components/builder/BuilderLeftPanel.tsx`
- `components/builder/SectionList.tsx` — with @dnd-kit drag handles
- `components/builder/SectionCard.tsx`
- `components/builder/AddSectionModal.tsx`
- `components/builder/ColorPicker.tsx`
- `components/builder/AdvisoryPanel.tsx` — brand guard advisory
- `components/builder/BuilderPreview.tsx` — right panel wrapper

**Modified:**
- `components/storefront/Storefront.tsx` — use DSLRenderer instead of LayoutRouter
- `app/s/[slug]/page.tsx` — pass ?p=productId to DSLRenderer for drawer open state
- `types/schemas.ts` — add LayoutDSL schema block

---

## 14. Demo Flow (Locked)

```
0:00 → Merchant uploads logo (Haree brand)
0:15 → StoreBirth: streaming text, each Qwen step labeled
       "qwen-vl-max: Reading your logo's visual geometry..."
       "qwen-max: Composing your store's unique layout..."
0:30 → Store Builder appears with Qwen's editorial recommendation
       Right panel: live preview showing editorial-stacked hero, ticker banner, featured-2col grid
0:40 → Merchant drags ticker banner to top of section list
       "Modified from Qwen's recommendation" indicator appears → HUMAN-IN-THE-LOOP
0:50 → Merchant clicks accent color → brand guard fires
       Conversational: "Your warm amber has a lived-in richness — navy pulls against that."
       Merchant keeps the change anyway. Preview updates instantly.
1:10 → [Publish Store]
1:15 → Haree storefront at /s/haree — editorial-stacked hero, ticker at top
       Split screen: terminal left, store right
1:30 → Customer rapidly views products (simulate button in terminal)
1:45 → Velocity spike detected — anomaly badge in terminal
2:00 → Option card rises in terminal (water-like animation)
       "Flash Sale · face wash · 15% off · 34 views, 0 conversions"
       Qwen's reasoning shown. Token count: "~2,100 tokens"
       Memory note: "Remembers 0 previous decisions for this store"
2:15 → Merchant taps Approve → storefront: announcement bar appears with promo code
       Transition: fluid, not a reload
2:25 → Attribution dashboard: Elevate-attributed revenue appears
2:35 → Quick cut: Crest store (/s/crest)
       Completely different: dark minimal-wordmark hero, horizontal-scroll grid,
       colored-bg cards, sidebar-text nav
       "Same platform. Completely different store."
       Side-by-side for 10 seconds.
2:55 → Architecture diagram flash (Qwen call chain visible)
3:00 → Done
```

---

## 15. Out of Scope (Post-Hackathon)

- Customer account creation + login
- pgvector cross-store RAG (designed, not implemented)
- Video hero section
- Lookbook section
- Ingredient-list section (Aesop-style)
- Carousel/slideshow (beyond horizontal-scroll)
- Full page builder (beyond section list + variant picker)
- Multi-language stores
- Custom domain support

---

## Open Questions for Opus Review

1. **DSL state management:** The builder uses a draft DSL that diverges from the published DSL.
   Should we use optimistic updates (apply draft immediately on publish click, rollback on error)
   or a two-phase commit (save draft → confirm → publish)?

2. **Qwen DSL generation reliability:** Qwen-Max must produce valid LayoutDSL JSON consistently.
   What prompt structure gives the highest compliance rate? Should we use function calling / tool
   use for structured output instead of `response_format: {type: "json_object"}`?

3. **Section ordering constraints:** Some section combinations break visually
   (e.g., two hero sections back-to-back). Should the renderer enforce ordering rules,
   or should Qwen be prompted to avoid bad combinations?

4. **Memory context size:** Last 10 entries injected into every decision prompt.
   Is 10 the right number? At ~100 tokens per entry, that's 1,000 extra tokens per cycle.
   Should this be configurable per store based on action frequency?

5. **Preview performance:** The preview panel re-renders on every builder state change.
   With 5 sections each containing product grids, this could be slow.
   Should preview updates be debounced (300ms)? Or is instant always better for feel?

6. **`@dnd-kit` vs other drag libraries:** `@dnd-kit` is the recommended choice for React,
   but it has a learning curve. Alternative: simple up/down arrow buttons instead of drag.
   Which is worth the implementation complexity for the demo?

7. **StoreBirth SSE + Qwen parallelism:** The 6 Qwen calls in the StoreBirth sequence
   currently run sequentially. Some can be parallelized (brand guard + CSS injection can
   both start after brand_token is generated). What's the optimal call graph for < 10s total?
