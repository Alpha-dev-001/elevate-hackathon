# Elevate — 3-Minute Demo Script (Track 4: Autopilot Agent)

> Every beat below maps to something **verified working** on localhost
> (2026-07-02). Judges score 60% on Qwen sophistication + innovation — so the
> two things this script front-loads are (1) a store that is *visibly different
> per brand* because Qwen designed it, and (2) the autonomous decision → human
> approval → **measured outcome** loop. Nothing here is aspirational.

## The through-line (say this, in some form)
"Most tools bolt AI onto a store. Elevate is the other way round — **Qwen builds
the store, runs it, and learns what works.** The merchant just approves."

---

## Setup before you hit record
- Two pre-seeded stores exist and are **deliberately distinct**: `/s/haree`
  (light, editorial, gallery layout) and `/s/crest` (dark, Space Grotesk,
  sidebar). This is the "unique store per brand" proof — no waiting on live gen.
- Merchant terminal at `/terminal`. Storefront at `/s/haree`.
- **Split-screen layout:** terminal (merchant cockpit) on the left, storefront
  (shopper) on the right. The whole pitch is the two talking to each other.
- Clear any stale pending action first (approve/dismiss) so the card appears fresh.
- Pick the attribution path: **abandon surge** (recovery offer) OR
  `?scenario=velocity_spike` (flash sale). Both now attribute (fixed `b2e514a`).
- Hard-refresh once so no stale `.next` chunk (ChunkLoadError) shows on camera.

---

## Timeline

| Time | On screen | Narration (tighten to your voice) |
|---|---|---|
| **0:00–0:20** | Elevate landing / logo upload dropzone | "Every store looks the same and runs the same. The merchant does all the work. Watch what happens when the AI *is* the store." |
| **0:20–0:55** | **Store birth.** Upload a logo → StoreBirth streams the real Qwen steps (analyzing geometry, palette, choosing type, layout). Reveal `/s/haree`. | "One logo. Qwen reads its visual DNA and builds a complete, branded storefront — colors, type, layout personality, product copy. Not a template — *this* brand." |
| **0:55–1:15** | Flip to `/s/crest` (dark, totally different). | "Same engine, a different logo — a completely different store. Forty logos, forty distinct stores. This is Qwen as a designer, not a filter." |
| **1:15–1:35** | Store Builder / point-and-edit: click a section, type an intent ("make it cleaner / more minimal"), Qwen maps it to a valid layout change. | "The merchant stays in control. Point at anything, tell Qwen in plain words — it changes the store, inside the brand's own guardrails." |
| **1:35–2:05** | **The brain.** Split-screen. Hit **Simulate customer activity**. Behavior pulses. An option card surfaces in the terminal: *"Recover abandoned carts…"* with trigger, estimated GMV, confidence, brand-check. | "Now it's live. Qwen watches real behavior. A cart-abandon surge — and it *decides*: here's an action, here's the expected revenue, here's why it's on-brand. It waits for a human." |
| **2:05–2:25** | Merchant taps **Approve**. Cut to storefront: promo applies, storefront morphs (fluid transition). | "The merchant approves. The store updates itself — live." |
| **2:25–2:50** | Attribution dashboard: **"This action drove $56.25. Elevate's fee: $5.62."** Show the promo_id trail. | "And it *measures itself*. Every AI decision is attributed to real orders. This is the autopilot with a P&L — and the outcome feeds back so the next decision is smarter." |
| **2:50–3:00** | Logo + "Built on Qwen Cloud · Alibaba Function Compute · Track 4." | "Elevate. The store that runs itself." |

---

## How to handle the recording (practical)
- **The ~15–20s Qwen decision latency is the one trap.** In a *recorded* video,
  just **cut the wait** (jump-cut from Approve-pending to card-appears). Don't do
  it live/unedited. If you narrate over it, say "Qwen is reasoning…" and cut.
- **Store birth** also runs several Qwen calls (~30–60s). Either **speed-ramp**
  that clip 2–4× or pre-warm it, then reveal at full speed. The *reveal* is the
  wow; the wait is not.
- **Record the two stores side by side** for the 0:55–1:15 distinctness beat —
  it's the single most differentiating shot; give it real screen time.
- Keep the **terminal + storefront split-screen** for 1:35 onward so approve →
  morph reads as cause-and-effect in one frame.
- Do a **dry run** end-to-end first (the loop is verified but Qwen output varies
  run to run — you want a take where the card copy reads well).
- Separately record the **proof-of-deployment** clip (Alibaba FC console showing
  the function Running + a live `/api/health` 200 + OSS bucket) — that's a
  *different* required artifact, ~90s, not part of the 3-min story.

## What NOT to show
- Don't scroll a 90-product grid (some tiles are branded-initial placeholders for
  dead seed images — fine in passing, don't linger).
- Don't show raw JSON / API docs. Keep it product-surface only.
- Don't attempt live onboarding of a brand-new logo unedited — too much latency.
