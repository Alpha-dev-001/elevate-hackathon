# Elevate — Upgrade Backlog (living document)

> A product manager's running map of where each shipped sprint can deepen.
> **Append, never delete.** When an item ships, mark it `✅ shipped (date)` and
> leave it in place — this is the audit trail of how the product matured.
> Each item is framed by **why a business owner cares**, then the granular
> decision or work behind it.
>
> Legend: `🔲 open` · `🔜 next` · `🧪 prototyped` · `✅ shipped` · `🧭 principle (decided)`

---

## Cross-cutting principles (decided — don't relitigate without reason)

- 🧭 **Customers never see Elevate. Merchants do.** A shopper logging into
  "Emma Fashion" sees Emma Fashion's *own* branded storefront — its palette,
  fonts, logo, domain — and never Elevate chrome. Elevate's UI (the dark mint
  admin/terminal) is the *merchant's* cockpit only. Two distinct visual worlds:
  the storefront wears the merchant's brand; the terminal wears Elevate's.
  _(Answers the "would customers see Elevate UI or the store UI?" question:
  the store's, always.)_
- 🧭 **Qwen proposes, the merchant disposes.** Generated brand/decisions are
  defaults the owner can always override. Nothing Qwen makes is permanent.
- 🧭 **Margins and internals never leave the backend.** cost_price, stock counts,
  and telemetry internals are never exposed on customer surfaces.

---

## Sprint 1 — "The Store Comes Alive" — upgrade areas

What shipped: merchant auth, logo→brand pipeline (qwen-vl-max → qwen-max),
OSS logo upload, products + batched descriptions, publish, public storefront.
Where it can deepen:

### 1. Identity & accounts
- 🔜 **Customer accounts (per store).** Today only *merchants* have logins.
  Shoppers can't sign in, save carts, or see orders. _Owner value:_ repeat
  buyers, saved details, order history = retention.
  - Decision: customer identity is **scoped to one store** (a customer of
    Emma Fashion isn't automatically known to another store) — unless we later
    offer an opt-in "Elevate ID" wallet. Default to store-scoped.
  - Granular: branded login/signup that lives at `/s/{slug}/account`, styled in
    the *store's* brand (see principle above), not Elevate's.
  - Guest checkout must stay possible — never force an account to buy.
- 🔲 **Merchant roles / staff seats.** One owner today. Real shops have staff.
  Role-based access (owner / manager / staff) on the terminal.
- 🔲 **Password reset + email verification.** No recovery flow exists yet.
- 🔲 **Session hardening.** Refresh tokens, device list, logout-everywhere.

### 2. Onboarding & brand generation
- 🔜 **Brand editability / override.** The owner can't change a single color or
  font after generation. _Owner value:_ it's *their* brand. Ship inline editing
  (palette, fonts, tagline) + a "regenerate / give me another direction" with a
  steer ("darker", "more playful"). Ties into the Sprint-2 `brand_tweak` reflex
  (edit → instant apply → Qwen's guard rule warns *in its own words* if it
  breaks coherence, but never blocks).
- 🔜 **Brand distinctiveness.** Generated stores currently feel samey (safe
  fonts, generic taglines). _Owner value:_ a brand that looks like *them*, not a
  template. Work: richer logo reading (energy/era/density/type cues),
  category-aware prompts (streetwear ≠ homeware in voice/type/layout), higher
  diversity, and offering 2–3 directions to choose from.
- 🔲 **Logo handling.** One logo, one shot. Add: re-upload/replace, multiple
  marks (horizontal/stacked/favicon), background removal, SVG logo support,
  size/format guidance in the dropzone.
- 🔲 **Incubation transparency.** The ~40s wait shows generic phases. Stream the
  *actual* steps ("found 3 dominant colors… choosing a serif to match the
  geometry…") for trust and delight.
- 🔲 **Brand versioning.** Keep a history of generated/edited brands so an owner
  can revert. Brand is an asset; treat it like one.

### 3. Brand system (design quality)
- ✅ **Text contrast safety (storefront).** Accent-as-text now auto-derives a
  WCAG-AA-safe variant (shipped 2026-06-15). _Next:_ extend the same guarantee
  to the brand-review preview and any merchant-facing brand surfaces.
- 🔲 **Better accent selection at generation time.** The deeper fix behind the
  contrast issue: Qwen sometimes returns near-greyscale accents (#B7B7B7).
  Push the prompt toward vivid, usable accents; validate saturation/contrast and
  re-roll if weak.
- 🔲 **Bolder use of the palette.** Colors are extracted well but applied timidly
  on the storefront. Use primary/secondary in hero blocks, section dividers,
  hover states — make the brand assert itself.
- 🔲 **Font loading robustness.** If a Qwen-named Google Font doesn't exist, fall
  back gracefully instead of system default. Validate font names against a known
  list; preload for no flash-of-unstyled-text.
- 🔲 **SVG icon quality.** Marks are minimal/geometric. Raise the bar; add
  category icons; ensure crispness at favicon size.

### 4. Products & inventory
- ✅ **Large-batch descriptions** chunked + parallel (shipped 2026-06-15).
- 🔜 **Regenerate descriptions** action for stores imported before the fix, and
  for owners who want a re-write in a new voice.
- 🔲 **Product images via OSS** (same presigned flow as the logo). Today product
  images are pasted URLs; let owners upload files. Add a branded placeholder
  when none.
- 🔲 **Variants / SKUs** (size, color), per-variant stock and price. Real
  catalogs aren't flat.
- 🔲 **Inventory management.** Edit/delete products, low-stock flags, restock,
  bulk edit. Today it's add-only.
- 🔲 **Category taxonomy.** Free-text categories now → structured, filterable
  collections that drive storefront navigation.
- 🔲 **Pricing & margin tools.** CSV imports assume a 60% cost ratio. Let owners
  set real costs, see margins, and get Qwen pricing suggestions (Sprint 2+).
- 🔲 **CSV robustness.** Column mapping UI, error report per row, dedupe,
  re-import/update by name.

### 5. Storefront (customer experience)
- 🔜 **Cart & checkout.** The store renders but can't sell yet. _Owner value:_
  this is the whole point. Cart (store-branded), checkout, payment (Alipay/card),
  order creation. Guest-first.
- 🔲 **Product detail page** at `/s/{slug}/{productId}` — gallery, full
  description, variant picker, related products.
- 🔲 **Search & filter / collections.** Browsing breaks past ~20 products.
- 🔲 **Custom domains.** `shop.emmafashion.com` instead of `/s/emma-fashion`.
  Big owner-perceived-legitimacy win. Needs wildcard TLS + domain verification.
- 🔲 **SEO & sharing.** Per-store `<meta>`, Open Graph (logo + tagline), sitemap,
  SSR/ISR for speed and indexability.
- 🔲 **Mobile polish.** Sticky cart, large imagery, single-column tuning (the
  storefront is mobile-first but untested on real devices).
- 🔲 **Empty/edge states.** "Sold out" everywhere, out-of-stock CTAs, a real
  404 store page in-brand.

### 6. Platform & infrastructure
- 🔜 **Deploy to Alibaba Cloud Function Compute** (hackathon requirement). Today
  everything runs locally. Needs: `s.yaml` functions, RDS Postgres + Tair Redis
  provisioned (currently local docker), provisioned concurrency for warm starts,
  the health-ping cron, and a screen recording proving the deploy.
- 🔲 **Secrets & config management.** Move from `.env` to FC env/secret store.
- 🔲 **DB migrations.** Wire Alembic properly (today dev uses create_all).
- 🔲 **Observability.** SLS logs, request metrics, Qwen call tracing/cost meter.
- 🔲 **Rate limiting & abuse.** Throttle signups, uploads, and Qwen-triggering
  endpoints. Cap upload size server-side.

### 7. Trust, safety & data
- 🔲 **Upload safety.** Validate image bytes (not just content-type), strip EXIF,
  cap dimensions; we already sanitize SVG — keep tightening.
- 🔲 **Slug & store-name moderation.** Reserved words, profanity, impersonation.
- 🔲 **Data lifecycle.** Account deletion, data export, orphan-asset cleanup in
  OSS (test artifacts already accumulate).
- 🔲 **Backups & recovery.** Redis is a cache; ensure Postgres is the durable
  truth everywhere and is backed up.

---

## Sprint 2 — "The Brain Wakes Up" — (to be built; areas seeded as we go)
Realtime telemetry → anomaly trigger → Qwen decision cycles → terminal option
cards → interceptor (3 layers) → storefront hot-reload → brand-tweak reflex.
_Upgrade areas will be appended here as Sprint 2 ships._

---

## Sprint 4+ / "AI IS the store" — vision capture (logged 2026-06-29)

> Captured from the founder's direction dump. The through-line: **Qwen is not a
> wrapper around a shop — Qwen *is* the shop's brain.** Everything below should
> make a merchant *want Qwen to do more*, never feel fenced in by it. Sequenced
> against the hackathon clock elsewhere; this is the durable backlog.

### A. The Qwen-as-runtime loop (the flagship cluster — one nervous system)
These are not four features; they're one self-improving loop. Build them so they
share the memory/decision/outcome plumbing already in `services/memory.py` +
`outcome_observer.py`.
- 🔜 **Per-customer personalization.** Now that shoppers log in per brand (RBAC,
  Sprint 4), Qwen tailors recommendations / storefront emphasis to the
  *individual* shopper from their own views + orders — not just the store.
  _Owner value:_ relevance → conversion + retention. Granular: per-customer
  signal in Redis, decision cycle reads it, personalized product ordering /
  hero. Respect the margins/internals-stay-backend principle.
- 🔜 **Proactive Qwen → merchant.** Option cards surface *on their own* by
  urgency (not only on anomaly), and Qwen **learns the merchant's approve/dismiss
  patterns** to tune what (and when) it proposes. _Owner value:_ the cockpit
  feels alive and gets smarter about *this* owner.
- 🧪 **Qwen self-extends its config on repeated requests.** Partly built
  (`capability_tracker.py`, `GET /api/brand/capabilities/{slug}`). Finish: the
  terminal widget surfacing proposed capabilities, and the loop where a
  recurring unmet intent → Qwen proposes a NEW config dimension.
- 🔲 **Merchant → Qwen feature requests.** Merchant tells Qwen, in words, what
  they wish the store could do. Qwen either (a) does it within existing config,
  or (b) **escalates a structured request** to the Elevate team to build. Closes
  the "I just wish merchants could tell Qwen and boom" loop. Tie to capability
  tracker.
- 🔲 **Qwen ↔ merchant conversation + relationship.** Qwen actually *talks* to
  the merchant (status, nudges, asks). Onboarding sets the tone: "What should
  Qwen call you?" — a named, personal relationship, not a tool. _Owner value:_
  trust; merchants who want Qwen on their side.

### B. Qwen autonomy in operations
- 🔲 **Qwen-run inventory management.** Low-stock detection, restock nudges,
  hide/feature by stock, demand-aware ordering suggestions. (Extends the
  inventory-management item under Sprint 1 §4.)
- 🔲 **Qwen self-A/B-tests design.** Aggregate which DSL variants shoppers
  engage with vs. those never used; Qwen proposes/test new layout additions and
  keeps winners. _Owner value:_ the store optimizes itself. (Autopilot story.)
- 🔲 **Pricing/discount autonomy.** "If a discount works, keep/extend it." Qwen
  proposes promos, measures lift via the existing attribution loop, doubles down
  on what converts — always inside the interceptor's margin/discount ceilings.

### C. Lifecycle & communications
- 🔲 **Qwen-drafted customer email.** Personalized from real data when it exists;
  a sensible default welcome/follow-up when it doesn't. Recommend, re-engage,
  and send a discount **only when warranted**. _Hard rule:_ **no spamming** —
  frequency caps + "did the last one work?" gating.
- 🔲 **Promo-notification timing.** Qwen decides *when* to notify, as the store
  would — not on a dumb schedule.
- 🔲 **Notifications surface (in-site + email).** Both merchant- and
  customer-facing. Merchant urgency cards can "pop from nowhere"; customers get
  in-store + email notices. Needs a notifications model + delivery path.

### D. Commerce depth
- 🔲 **Smarter checkout.** Don't ask for a name if the shopper is signed in;
  ask for the info that's actually useful. _Qwen sees all_ — use what we know.
- 🔲 **Orders carry location (+ "Transit-tree" core).** Persist location/shipping
  on orders so Qwen can **group orders by location** and reason about
  logistics/fulfillment. Foundation for delivery intelligence.
- 🔜 **Customer → order history.** Link orders to `customer_id` when signed in
  (today cart is guest `session_id`); show past orders on `/s/{slug}/account`.
  (Also in `docs/CHAIN.md` NEXT #4.)

### E. Storefront / builder UX & motion
- 🔲 **Cart affordance: icon, not just "Add".** Replace/augment the "Add" button
  with a cart icon (consider both). Small, high-frequency polish.
- 🔲 **Cart presentation variants.** Popup / slide-in from left·right·top·bottom
  as DSL config, per brand. (Extends Sprint-4 `cart_style`.)
- 🔲 **Collapsible advanced pickers in the builder.** Basic controls first, then
  an "advanced" disclosure for power tweaks (cart direction, motion, etc.) — keep
  the first run simple, let depth be opt-in.
- 🔲 **Motion as part of the brand.** Subtle, branded animation baked into the
  DSL *at store creation* (Qwen chooses motion personality like it chooses type).
  Polish micro-interactions with the `impeccable` design pass. Respect
  `prefers-reduced-motion`.

### F. Trust, safety & economics
- 🔲 **Anti-gaming the AI surface.** Guard against shoppers/merchants trying to
  manipulate Qwen (prompt injection via product text, fake velocity to trigger
  promos, intent-spam to force capabilities). Rate-limit + validate every
  Qwen-triggering input. (Extends Sprint 1 §6 abuse item.)
- 🔲 **Qwen's cut / take-rate accounting.** Track Elevate's economic share per
  store ("Qwen code stuff to know Qwen's cut") — the revenue model instrumented
  in code. Needs definition before build (flag as a decision).
