# Elevate — Final Demo Video Script (rev. 2026-07-16)

> **Target: 2:50** (10-second buffer before the 3:00 hard cut).
> **Recording setup:** OBS, 1920×1080, 60fps. Split-screen from 1:00 onward (terminal left, storefront right).
> **Two stores used:** one PRE-BUILT (owoyemi-of-offa — the depth showcase), one BUILT LIVE (a fresh brand — the creation showcase).
> **One rule:** if a beat depends on Qwen thinking (~15-20s), **record it happening, then jump-cut the wait** in editing. Never show dead air.
>
> **Why this revision exists:** the 07-11 version only showed ONE autopilot
> trigger (a reactive velocity spike). Elevate actually has six distinct
> trigger mechanisms — three reactive, three proactive — feeding the same
> decision engine. Showing only one made the "autopilot" claim look thinner
> than it is. This version adds a proactive beat and the merchant-override-
> and-learn beat (shipped 2026-07-16), and tags every beat with the judging
> criterion it's proving so the narration does the mapping for the judge
> instead of leaving them to infer it.

---

## The Thesis (memorize this — it's the spine of every narration line)

> "Qwen didn't just help build this store. Qwen runs it — reactively,
> when a customer does something, and proactively, on its own schedule,
> without waiting to be triggered. Six different signals, one decision
> engine, one set of guardrails it can never override. The merchant
> approves. That's it."

---

## Judging-criteria tags used below

- **[Innovation 30%]** — sophisticated Qwen usage, non-obvious engineering
- **[Depth 30%]** — architecture quality, structural (not prompted) safety
- **[Impact 25%]** — real business pain point, productization
- **[Presentation 15%]** — legibility, a judge should never have to guess what they're looking at

Say the bracketed word out loud or caption it on screen — do not name any
other project, tool, or competitor anywhere in the video, narration, or
on-screen text. Comparisons are implicit (this is what Elevate does), never explicit.

---

## Pre-Recording Checklist

- [ ] `/s/owoyemi-of-offa` loaded and verified working — **do NOT rebuild or touch it**
- [ ] Terminal logged in as owoyemi merchant — clear any stale pending actions
- [ ] Fresh signup account ready for the live build beat (or do it live)
- [ ] Split-screen layout tested: terminal (left) + storefront (right)
- [ ] "Simulate customer activity" button accessible
- [ ] A product with real views but zero orders exists (for the proactive beat) — seed one if needed
- [ ] No stale `.next` chunks — hard-refresh both pages
- [ ] Microphone tested — narration audio clean
- [ ] Do ONE full dry run before hitting record

---

## BEAT 1 — The Hook [0:00 – 0:10] · [Presentation 15%]

**On screen:** The finished owoyemi-of-offa storefront. Already live. Already beautiful.

**Narration:**
> "This store was built by AI, and it's still being run by AI, right now,
> while you watch. Qwen designed it, stocked it, and is watching it —
> reactively and proactively. I'll show you both."

**Why this works:** Names the reactive/proactive split in the first ten seconds so every beat after this has a home in the judge's head.

---

## BEAT 2 — The Creation [0:10 – 0:35] · [Innovation 30%]

**On screen:** Fresh signup → logo drop → incubation loading state → brand reveal.

**Narration:**
> "New merchant, from zero. One input — the logo.
> *(incubation animation, speed-ramped)*
> Qwen's vision model reads it. Its reasoning model designs the full
> brand — palette, typography, voice, and the guard rules that'll govern
> everything from here on. Two models, one call chain, no template picked
> from a list."

**Edit notes:** Speed-ramp the ~45s incubation to ~8s. Land the brand reveal around 0:32.

---

## BEAT 3 — Product Vision [0:35 – 0:55] · [Depth 30%]

**On screen:** Merchant drops product photos → catalog review surfaces a flagged item.

**Narration:**
> "Photos in, no names or prices. Qwen identifies each product, writes
> the copy in the store's own voice, and prices it near baseline. And
> when it isn't sure —" *(flagged card appears)* "— it says so, instead
> of guessing. That's the difference between a feature and a runtime
> that knows its own limits."

**Edit notes:** Fast — 2-3 real photos live, hard-cut to the finished catalog.

---

## BEAT 4 — Reactive Autopilot [0:55 – 1:30] · [Depth 30% + Innovation 30%] ⭐

**On screen:** Split-screen — terminal left, storefront right.

**Step-by-step:**
1. Point at the terminal's memory badge: `✦ Remembers N previous decisions`.
2. Trigger customer activity (simulate or real events).
3. Anomaly detected — decision cycle fires. Jump-cut the ~15-20s Qwen think time.
4. Card appears — walk through trigger, action, estimated revenue, brand check, memory badge.

**Narration:**
> "The store is live. A shopper triggers a velocity spike — twenty-four
> views in thirty seconds on one product. Qwen doesn't just alert me —
> it decides: a flash sale, that exact product, informed by every prior
> approval and rejection for this store. It always waits for my tap."

---

## BEAT 4B — Proactive Autopilot [1:30 – 1:50] · [Innovation 30%] ⭐ NEW

**This beat didn't exist in the last cut — add it. It's the single easiest way to prove "proactive," not just "reactive," and it's the half of Track 4's mandate that's currently invisible in the demo.**

**On screen:** Terminal only (no customer needed on the storefront for this one — say so).

**Narration:**
> "Now watch this with nobody shopping at all. Once an hour, Qwen reviews
> the whole catalog on its own — no customer event, no trigger from me.
> It's comparing real view interest against real completed orders, and
> right now it's found one: a product with real interest and zero sales.
> That's a proactive decision — Qwen looked for a problem instead of
> waiting for one to announce itself."

**Edit notes:** If the hourly tick hasn't fired naturally, trigger `run_store_review` directly (MCP tool `elevate_run_store_review` or a script call) on camera — say plainly "I'm triggering the same proactive review Qwen runs hourly, so you don't have to wait an hour." Honesty here reads better than faking a live tick.

---

## BEAT 5 — Approve, Morph, and Override [1:50 – 2:15] · [Impact 25% + Innovation 30%]

**On screen:** The Beat-4 card, but this time edit the discount before approving.

**Step-by-step:**
1. Tap the editable discount field, change Qwen's proposed % to your own number.
2. Approve. Storefront morphs live (promo banner, price change, Framer Motion transition).

**Narration:**
> "And I don't have to take Qwen's number as-is. I can override it —" 
> *(edit the %, approve)* "— and that correction is written back. The
> next proposal for this store is shaped by the fact that I changed this
> one. One tap, the store updates live for the customer. No deploy, no
> refresh."

**Why this works:** This beat didn't exist before 2026-07-16. "The agent learns from human correction" is close to verbatim Track 4 language — showing it, not claiming it, is the single highest-value new addition to this script.

---

## BEAT 6 — The Guardrails [2:15 – 2:35] · [Depth 30%]

**On screen:** Try to sell a product below cost → hard block.

**Narration:**
> "And none of this can go wrong in a way that matters. Try to sell below
> cost —" *(hard block fires)* "— blocked. Not a prompt asking Qwen to
> behave. Deterministic code that Qwen itself cannot override, checked
> both before I approve and again the instant it executes."

**Edit notes:** First to cut if you're over time — collapse to a 10s montage (below-cost block + brand-clash warning back to back, no narration pause between).

---

## BEAT 7 — The Close [2:35 – 2:50] · [Impact 25%]

**On screen:** Both stores side by side, then title card.

```
ELEVATE
The store that runs itself — reactively and proactively.

Built on Qwen Cloud · Alibaba Cloud
Track 4: Autopilot Agent

github.com/Alpha-dev-001/elevate-hackathon
```

**Narration:**
> "Two logos, two different stores, one engine underneath — reacting to
> customers, watching the catalog on its own, learning from every
> correction. The merchant approves. Qwen runs the store."

---

## Timing Budget

| Beat | Duration | Cumulative |
|---|---|---|
| 1 — Hook | 10s | 0:10 |
| 2 — Creation | 25s | 0:35 |
| 3 — Product Vision | 20s | 0:55 |
| 4 — Reactive Autopilot ⭐ | 35s | 1:30 |
| 4B — Proactive Autopilot ⭐ NEW | 20s | 1:50 |
| 5 — Approve/Morph/Override | 25s | 2:15 |
| 6 — Guardrails | 20s | 2:35 |
| 7 — Close | 15s | 2:50 |
| **Buffer** | **10s** | **3:00** |

## What to Cut First (if you're over 3:00)

1. Beat 6 → 10s montage, no narration pause
2. Beat 3 → cut to catalog result only, skip the flagged-item aside
3. Beat 2 incubation → shorter speed-ramp

## What to NEVER Cut

- **Beat 4B (proactive)** — without it the video only proves half of Track 4's mandate
- **Beat 5's override moment** — the newest, most Track-4-specific thing you have
- The memory badge callout in Beat 4

---

## Common Judge Questions — Address in Narration

**"Is this just threshold alerts, not real AI?"**
> Beat 4: "The trigger is a simple velocity threshold — transparent and
> configurable by design. The autonomy is in the RESPONSE: which action,
> which product, what discount, in what words — informed by every prior
> outcome for this specific store."

**"Does it only react, or does it actually initiate anything?"**
> Beat 4B exists to kill this question outright — show it, don't argue it.

**"Does it actually learn, or is that just logging?"**
> Beat 5: "Every approval, rejection, AND correction feeds the next
> decision cycle. It's not fine-tuning — it's structured context a human
> can audit line by line."

**"What happens if Qwen hallucinates or gets it wrong?"**
> Beat 6: guardrails are deterministic code, not a second prompt asking
> Qwen to behave.

---

## Technical Notes for Recording

- Qwen decision cycle: ~5-15s (tool-calling). Jump-cut the wait.
- Brand generation: ~35-45s. Speed-ramp the incubation.
- Record at 1080p60. Narration audio from a real mic, recorded separately if possible so flubbed lines don't force a re-shoot of the screen capture.
- Do the dry run — the biggest killer is discovering a feature doesn't work mid-take.
- OBS scenes: (1) full-screen storefront — Beats 1-3, (2) split-screen — Beats 4-6, (3) title card — Beat 7.

---

## Proof-of-Deployment Clip (separate, ~90s, NOT part of the 3-min video)

**This is corrected from the previous revision, which incorrectly described
Alibaba Cloud Function Compute with two deployed functions — the actual
deployment is Alibaba Cloud ECS, a single Docker Compose instance. Follow
`docs/VIDEO_GUIDE.md` exactly; it already has the right shot list (ECS
console → health endpoint → OSS bucket → `upload.py` code on GitHub) and
matches what's actually running.** Do not record against the FC console —
there is nothing there.
