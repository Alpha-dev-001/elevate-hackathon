# Elevate — Work Chain (resume from any session)

> Single source for "where are we, what's next." Update the **Next** list as items
> ship. Memory mirror: `~/.claude/.../memory/elevate-sprint3-done-sprint4-direction.md`.
> Branch: `main` (sprint-3 merged; sprint-4 committed directly as `[sprint-4]`).
> Commits: prefix `[sprint-3]`/`[sprint-4]`, **NO Co-Authored-By**. Don't push to origin without asking.

---

## How to resume (cold start)

```bash
docker compose up -d            # web :3000, api :9000, pg, redis
# if a dependency was added since the image was built:
docker compose exec web npm install         # host npm install does NOT reach the container
# if the dev server is stuck on an old build error:
docker compose exec web sh -c 'rm -rf /app/.next/*' && docker compose restart web

# apply any pending migrations (idempotent):
for f in analytics-brain/migrations/2026_sprint*.sql; do
  docker compose exec -T db psql -U elevate -d elevate -f - < "$f"; done

# tests
cd storefront-ui && npx vitest run                 # frontend (vitest)
cd analytics-brain && .venv/Scripts/python.exe -m pytest tests -k "not live and not behavior" -q   # backend units
```

**Key URLs:** `/` (smart home) · `/login` (merchant) · `/terminal` (dashboard) ·
`/builder?slug=haree` (Store Builder) · `/s/haree` & `/s/crest` (live stores, deliberately distinct) ·
`/s/{slug}/account` (branded customer auth). API docs: `localhost:9000/docs`.

**Demo merchant id** (haree): `merchant_6ad7232b264f`. Mint a merchant token for curl:
`docker compose exec -T api sh -c 'cd /app && PYTHONPATH=/app python -c "from app.core.security import create_access_token; print(create_access_token(\"merchant_6ad7232b264f\"))"'`

---

## DONE chain

**Sprint 3 (merged):** LayoutDSL engine (3-layer defense: `coerce_variant`→`normalize_dsl`→`fallback_dsl_from_token`, `analytics-brain/app/services/layout_dsl.py`) · `DSLRenderer` + registry (`storefront-ui/lib/dslRegistry.ts`, `registerVariants.ts`): 4 hero / 4 grid / 3 banner / 3 story / 6 card / 5 nav · Store Builder (`lib/builderStore.ts`, @dnd-kit) · Qwen memory loop (`services/memory.py`, `outcome_observer.py`, decision-cycle injection) · CSS injection (`css_gen.py` + `CustomCSSInjector`) · StoreBirth SSE endpoint (`/api/brand/birth/{slug}` + `StoreBirth.tsx`).

**Sprint 4 (committed on main):**
1. `add_to_cart` as DSL config (shared autonomy) — grids + `cards/CardAddToCart.tsx`.
2. Per-store **product-detail** (3) + **cart** (2) variants — `ProductDrawer.tsx` (switches layout+motion), `Cart.tsx` (`variant` prop). Fixed `_coerce_global` dropping optional config.
3. **RBAC** — JWT `role`; `CustomerDB` + `customer_auth.py` (`/s/{slug}/auth/*`, cookie `elevate_customer`, cross-store 403); branded `/s/[slug]/account` (`CustomerAccount.tsx`); merchant `/login`; smart `/`; builder gated to owning merchant.
4. **Point-and-edit** — `editMode` → `EditTargetWrap` (sections+nav clickable in preview); `EditPopover.tsx` (instant variant swap OR free-text "Ask Qwen"); `POST /api/brand/edit-intent/{slug}` (qwen-max maps intent→validated option).
5. **Self-extending config** — edit-intent returns `satisfiable`; unmet intents tracked in `merchants.capability_requests` (`capability_tracker.py`); on recurrence (≥2) Qwen **proposes a new capability**. `GET /api/brand/capabilities/{slug}`.

**Fixes this session:** moved Store Builder `/brand-review`→`/builder` (route-group collision broke whole app); container `npm install` for @dnd-kit; builder preview `translateZ(0)` containing block (fixed sidebar nav was covering controls); minimal-text nav overflow; full-bleed hero clip; Crest given a distinct dark identity (`scripts/diversify_crest.py`).

---

## NEXT chain (ordered — each is a clean pick-up)

1. **Surface capability proposals to the merchant** — terminal/builder widget reading `GET /api/brand/capabilities/{slug}`: "✦ Qwen proposes N new capabilities" with the list. Backend already returns it; just needs UI. *Acceptance:* proposed capabilities (status=proposed) show in the terminal.

2. **Mount StoreBirth in onboarding** — the SSE component (`StoreBirth.tsx`) + endpoint exist but the onboarding incubation flow still uses the WS `brand_ready` path. Wire `StoreBirth` into the incubation step so the labeled qwen-vl/qwen-max steps are visible, then hand off to `/builder?slug=`. *Acceptance:* logo upload → streamed steps → builder.

3. **Point-and-edit beyond existing options** — today it only picks among allowed variants. Extend so an intent can (a) add a NEW section (`add_section` patch), and (b) edit hero/section copy (needs a `props.copy` field on sections + Qwen text-gen). *Acceptance:* "add a testimonials section" inserts one.

4. **Customer → order history** — link orders to `customer_id` when signed in (cart is guest `session_id` today); add `/s/{slug}/account` order list. *Acceptance:* a logged-in customer sees past orders.

5. **Legacy full-page detail** (`/s/[slug]/[productId]` → `ProductDetail.tsx`) is NOT variant-aware (drawer is primary). Make it honor `product_detail`, or retire the route. *Acceptance:* consistent with the drawer.

6. **Polish:** Crest `sidebar-text` rail crowds 13 categories (cap/scroll the rail); some Crest product images 404 (seed-data URLs); `add_to_cart` etc. not yet shown in the builder's section-level UI beyond the "Store behavior" panel.

7. **Deploy to Alibaba** (hackathon requirement) — follow `ALIBABA_DEPLOY.md` + `s.yaml` + `analytics-brain/Dockerfile`. Test WebSocket on FC early (API Gateway fallback noted). *Acceptance:* backend live on Function Compute + screen recording.

8. **Post-hackathon (designed, not built):** cross-store pgvector RAG for decision cycles.

---

## Qwen accounting (2 models: qwen-vl-max + qwen-max)

**Does, live:** ① logo→analysis (vl-max) · ② brand: palette/type/voice/guards/SVG icons · ③ BrandToken (layout DNA) · ④ LayoutDSL · ⑤ scoped CSS · ⑥ product descriptions (batched) + seed products · ⑦ catalog pricing review · ⑧ decision cycle **reading per-store memory** → option cards · ⑨ point-and-edit intent → DSL patch · ⑩ **detects unmet intents → proposes new capabilities**. Memory loop closed (approve/dismiss → outcome_observer → memory → next decision).

**Gotchas to remember:** route-group paths can collide with top-level pages (whole-app build error); web container has its own `node_modules` volume; redis `__del__` prints a harmless "Event loop is closed" at script exit; `normalize_dsl` must preserve every optional `global_config` field (see `_coerce_global`).
