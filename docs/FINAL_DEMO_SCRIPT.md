# Elevate — Final Demo Video Script

> **Target: 2:50** (10-second buffer before the 3:00 hard cut).
> **Recording setup:** OBS, 1920×1080, 60fps. Split-screen from 1:10 onward (terminal left, storefront right).
> **Two stores used:** one PRE-BUILT (owoyemi-of-offa — the depth showcase), one BUILT LIVE (a fresh brand — the creation showcase).
> **One rule:** if a beat depends on Qwen thinking (~15-20s), **record it happening, then jump-cut the wait** in editing. Never show dead air.

---

## The Thesis (memorize this — it's the spine of every narration line)

> "Qwen didn't just help build this store. Qwen IS the store.
> It designed the brand, cataloged the products, watches the customers,
> makes the decisions, and learns from every outcome.
> The merchant approves. That's it."

---

## Pre-Recording Checklist

- [ ] `/s/owoyemi-of-offa` loaded and verified working — **do NOT rebuild or touch it**
- [ ] Terminal logged in as owoyemi merchant — clear any stale pending actions
- [ ] Fresh signup account ready for the live build beat (or do it live)
- [ ] Split-screen layout tested: terminal (left) + storefront (right)
- [ ] "Simulate customer activity" button accessible
- [ ] No stale `.next` chunks — hard-refresh both pages
- [ ] Microphone tested — narration audio clean
- [ ] Do ONE full dry run before hitting record

---

## BEAT 1 — The Hook [0:00 – 0:12]

**On screen:** The finished owoyemi-of-offa storefront. Already live. Already beautiful.

**Narration:**
> "This store was built by AI. Not designed with AI assistance — built.
> Qwen read one logo and created everything you see: the colors, the fonts,
> the layout, every product description, even the rules that protect the brand."

**Why this works:** You lead with the result, not the process. Judges see a real, polished store in the first frame. The hook is "AI built this entire thing" — not "let me show you a signup form."

---

## BEAT 2 — The Creation [0:12 – 0:45]

**On screen:** Fresh signup → logo drop → incubation loading state → brand reveal.

**Narration:**
> "Let me build another one. New merchant, from zero. One input — the logo."
>
> *(incubation animation plays — "Analyzing geometry... Extracting palette...")*
>
> "Qwen's vision model reads the logo. Its text model designs the full brand —
> palette, typography, voice, layout, and the guard rules that'll govern
> everything from here on. All from one image."
>
> *(brand reveal — store shell appears)*
>
> "That's the store. Qwen built it. Now it'll run it."

**Edit notes:** Speed-ramp the incubation (it takes ~45s real-time — cut to ~8s). Show the streaming text animation — it's the "magic moment." The brand reveal should land around 0:40.

**Why this works:** Judges see the full creation loop in 33 seconds. The two-model architecture (VL reads, Max designs) is demonstrated visually, not explained in a diagram.

---

## BEAT 3 — Product Vision [0:45 – 1:10]

**On screen:** Merchant drops product photos → Qwen reads each one → catalog review surfaces.

**Narration:**
> "Now products. I drop photos — no names, no prices, no descriptions.
> Qwen's vision model looks at every one: identifies the product, reads
> the brand off the packaging if it can, picks the colorways, writes the
> copy in the store's voice, and prices it near my baseline."
>
> *(catalog review card surfaces with flagged products)*
>
> "And when it's not sure — it says so. These flagged for my review
> instead of guessing. I fix one, approve the rest."

**Edit notes:** If using the pre-built owoyemi store, show the 98-photo folder in Explorer → hard-cut → scroll the finished store. If live-building, show 3-5 photos being processed (real-time), then approve.

**Why this works:** The `confident=False` flag is the credibility moment. It shows Qwen has self-awareness about its own limitations — not just hallucinating confidently. This is what separates "AI feature" from "AI runtime."

---

## BEAT 4 — The Autopilot [1:10 – 1:55] ⭐ CENTERPIECE

**This is the beat that wins or loses Track 4. Give it room.**

**On screen:** Split-screen — terminal (merchant cockpit) left, storefront (customer view) right.

**Step-by-step:**

1. **Show the terminal header.** Point out the memory badge: `✦ qwen-max · Remembers N previous decisions · ~X tokens`. This is your proof of the learning loop — say it out loud.

2. **Trigger customer activity.** Click "Simulate customer activity" or let real behavior events flow. Watch the storefront (right side) as events come in.

3. **Wait for the anomaly.** The behavior tracker detects a velocity spike or cart abandon surge. The decision cycle fires.

4. **Jump-cut the Qwen thinking time (~15-20s).** In the edit, cut from "trigger fired" to "card appears." If narrating over it: "Qwen is reasoning about what to do..."

5. **The decision card appears.** Walk through it:
   - ⚡ **Trigger** — what Qwen detected (e.g., "Velocity spike: 24 views on Linen Blazer")
   - 🎯 **Action** — what Qwen proposes (e.g., "Flash sale: 15% off Linen Blazer")
   - 💰 **Est. Revenue** — grounded estimate from real anomaly count × avg price
   - 📊 **Confidence** — how sure Qwen is
   - 🛡️ **Brand alignment** — the interceptor's check
   - 🧠 **Memory badge** — "Informed by N prior outcomes"

**Narration:**
> "Now the autopilot. The store is live and Qwen watches real shopper
> behavior. Here — a velocity spike on a specific product. Twenty-four
> views in thirty seconds."
>
> *(decision card surfaces)*
>
> "Qwen doesn't just alert me — it decides. A flash sale on that exact
> product, fifteen percent, with expected revenue, confidence, and a
> brand-safety check. And this" *(hover over memory badge)* "— it's
> reading what worked before for this store. Every approval, every
> rejection, every outcome. The next decision is smarter than the last."
>
> "It waits for me. It always waits."

**Why this works:** This is the single most important 45 seconds. You show:
- Real-time event-driven architecture (not polling, not scripts)
- Native Qwen tool-calling (5 structured tools, typed parameters)
- Per-product targeting (not generic store-wide actions)
- Memory loop (the cognitive cycle judges score on)
- Human-in-the-loop (merchant stays in control)

---

## BEAT 5 — Approve + Morph [1:55 – 2:15]

**On screen:** Tap **Approve** → storefront morphs (promo banner appears, price changes, fluid Framer Motion transition).

**Narration:**
> "One tap. The store updates live — the customer sees the new price
> instantly. No deploy, no refresh, no admin panel. Qwen proposed,
> I approved, the store morphed."

**Edit notes:** This needs to be in the SAME frame as Beat 4's split-screen. The approve → morph cause-and-effect must be visible in one shot. The Framer Motion fluid transition is the visual payoff — let it play, don't cut through it.

---

## BEAT 6 — The Guardrails [2:15 – 2:35]

**On screen:** Try to break the brand. Either:
- Change the accent color to something clashing → brand warning fires
- Set a product price below cost → hard block ("Selling at a loss is blocked")

**Narration:**
> "And Qwen has guardrails it wrote itself and can never override.
> Try to break the brand palette — it stops me, in its own words,
> referencing the specific logo it analyzed. Try to sell below cost —
> hard block. No exceptions. The AI built the rules, and the code
> enforces them. This isn't prompt engineering — it's structural safety."

**Why this works:** This answers the "is it actually safe?" question before judges ask it. The brand warning in Qwen's own words (referencing the specific logo) is a killer visual — it proves the guard rules aren't generic templates.

---

## BEAT 7 — The Close [2:35 – 2:50]

**On screen:** Pull back to show both stores (owoyemi + the one you just built). Side by side. Completely different brands, completely different stores. Then:

**Title card:**
```
ELEVATE
The store that runs itself.

Built on Qwen Cloud · Alibaba Cloud
Track 4: Autopilot Agent

github.com/Alpha-dev-001/elevate-hackathon
```

**Narration:**
> "Two logos. Two completely different stores. Same engine.
> Qwen builds it, stocks it, prices it, runs it, guards it — and
> learns from every decision. The merchant just approves.
> That's Elevate."

---

## Timing Budget

| Beat | Duration | Cumulative |
|---|---|---|
| 1 — Hook | 12s | 0:12 |
| 2 — Creation | 33s | 0:45 |
| 3 — Product Vision | 25s | 1:10 |
| 4 — Autopilot ⭐ | 45s | 1:55 |
| 5 — Approve + Morph | 20s | 2:15 |
| 6 — Guardrails | 20s | 2:35 |
| 7 — Close | 15s | 2:50 |
| **Buffer** | **10s** | **3:00** |

---

## What to Cut First (if you're over 3:00)

1. **Beat 3 detail** — show the folder + result, cut the per-product narration
2. **Beat 6** — the guardrails are important but not Track-4-core. Move to a 10-second montage
3. **Beat 2 incubation** — cut the loading animation shorter

## What to NEVER Cut

- Beat 4 (the autopilot loop) — this is 60% of your Track 4 score
- Beat 5 (approve → morph) — the cause-and-effect payoff
- The memory badge callout — the learning loop is the hardest thing to show and exactly what judges reward

---

## Common Judge Questions — Address in Narration

**"Is this just threshold alerts, not real AI?"**
> Bake this into Beat 4: "The trigger is a simple velocity threshold —
> that's by design, transparent and configurable. The autonomy is in
> the RESPONSE: Qwen decides what action, which product, what discount,
> in what words — informed by every prior outcome."

**"Does it actually learn or is that just logging?"**
> Point at the memory badge. Say: "Memory is structured context injection —
> every approval, rejection, and outcome feeds back into the next decision
> cycle. It's auditable, immediate, and has zero cold-start cost."

**"What happens if Qwen hallucinates?"**
> Beat 6 covers this: "Three defense layers guarantee a renderable store
> regardless of what Qwen returns. If the AI call fails entirely, a
> deterministic hash generates a distinct fallback layout."

---

## Technical Notes for Recording

- **The Qwen decision cycle takes ~5-15s** (tool-calling mode). Jump-cut the wait.
- **Brand generation takes ~35-45s.** Speed-ramp the incubation loading state.
- **Product vision takes ~10-20s per image.** Show 2-3 real-time, then hard-cut to the catalog.
- **Record at 1080p60.** Judges watch on laptop screens — clarity matters.
- **Narration audio:** use a decent mic, not laptop speakers. Record narration SEPARATELY if possible — you can re-record flubbed lines without re-recording screen.
- **Do the dry run.** The biggest recording killer is discovering a feature doesn't work mid-take.
- **OBS scenes to set up:**
  1. Full-screen storefront (Beats 1, 2, 3)
  2. Split-screen: terminal left + storefront right (Beats 4, 5, 6)
  3. Title card (Beat 7)

---

## Proof-of-Deployment Clip (separate, ~90s, NOT part of the 3-min video)

Record this separately for the "short screen recording proving Alibaba Cloud deployment" requirement:

1. Open Alibaba Cloud FC console
2. Show the two deployed functions (bms-frontend, bms-backend-brain)
3. Hit the health endpoint
4. Open the live storefront URL
5. Show a live WebSocket connection

This is a checkbox item, not a scoring item. Keep it short.
