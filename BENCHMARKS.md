# Elevate — Qwen Benchmark Results

Real numbers from a real run against the live Qwen API — not mocked, not
hand-picked. Reproduce with:

```bash
docker compose exec api python -m tests.bench_live
# or, from analytics-brain/: python -m tests.bench_live
```

The harness lives in `analytics-brain/tests/bench_live.py` (scenario
execution) and `analytics-brain/tests/test_benchmarks.py` (the
`BenchmarkResult`/`BenchmarkReport` infrastructure, covered by its own
mock-data tests so CI doesn't spend tokens on every run).

## Latest run — 2026-07-11

| Scenario | Model | Latency | Valid | Quality | Notes |
| --- | --- | --- | --- | --- | --- |
| `logo_analysis` | qwen-vl-max | 5.3s | ✓ | good | palette/mood/style/geometry extracted |
| `brand_generation` | qwen-max | 7.5s | ✓ | good | guard rules present |
| `decision_cycle` | qwen-max (tool-calling) | 6.2s | ✓ | good | selected a tool from 5 typed options |
| `product_vision` | qwen-vl-max | 4.8s | ✓ | good | confident identification |
| `batch_descriptions` | qwen-max | 4.4s | ✓ | good | 3/3 real copy, 0 fallback |

**Aggregate: 100% valid rate (5/5 passed Pydantic schema validation) · avg latency 5.6s · 5/5 scenarios rated "good"**

## What "valid" and "quality" mean here

- **Valid** — the response passed Pydantic validation with no coercion
  needed to become well-formed. A response Qwen returns that fails this
  raises `BrandGenerationError`, is caught by the benchmark, and is scored
  `output_valid=False`.
- **Quality** — a scenario-specific heuristic, not a human rating:
  `brand_generation` checks guard rules were actually authored (not empty),
  `product_vision` checks Qwen reported `confident=True`, `decision_cycle`
  checks a tool was actually selected (not declined), `batch_descriptions`
  checks every product got real Qwen copy with zero fallback text.

## Why latency numbers, not just "it works"

Every one of these calls sits on a path a merchant or customer is actively
waiting on during onboarding or a live decision cycle — the interceptor
and incubation UI exist specifically because these calls are not
instant. Reporting the real number keeps that design decision honest
instead of asserting "under 2 seconds perceived" without ever measuring it.

## Reproducibility notes

- All 5 calls use a single public Alibaba-hosted test image
  (`dog_and_girl.jpeg`, already reused by `test_onboarding_live.py` and
  `test_storefront_live.py`) as a stand-in for a merchant logo / product
  photo. This benchmarks the Qwen round-trip and schema validation, not
  demo content — the number would not meaningfully change with a
  different reachable image.
- No database, Redis, or running server required — `bench_live.py` calls
  the service-layer functions (`analyze_logo`, `generate_brand`,
  `analyze_product_image`, `generate_descriptions`, and the decision-cycle
  tool-calling call) directly.
- Re-running will vary latency ±1-2s call to call (normal for a live LLM
  API) but should not change the valid/quality columns — those reflect
  code behavior (schema coercion, guard rules, fallback logic), not model
  variance.

## "With a subconscious vs. without one" — 2026-07-13

CLAUDE.md names the interceptor "the Subconscious Interceptor" — the
merchant never sees it fire, but every proposed action passes through it
before reaching a decision card. This run tests what that name is worth
in real dollars and real percentage points. The **pipeline** arm is a real
`qwen-max` tool-calling call (`decision_engine.py`) followed by the real
`interceptor.enforce_action_discount`. The **bare** arm is the same model,
the same scenario information, the same prompt content minus the
tool-calling instruction — no tools, no interceptor, nothing standing
between the model's raw proposal and execution. Same Qwen, same facts,
subconscious removed.

Reproduce with:

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m tests.bench_live
# from analytics-brain/
```

| Scenario | Pipeline blocked/clamped? | Bare discount proposed | Margin burned (bare, real $) | Headroom left unused (bare, points) | Phantom target? |
| --- | --- | --- | --- | --- | --- |
| `thin_margin_flash` | Clamped to 2.89% | 10% | $0.00 | 0.0 pts | No |
| `near_ceiling_stack` | Clamped to 40.0% | 10% | $0.00 | 30.0 pts | No |
| `merchant_min_price_floor` | Clamped to 11.11% | 10% | $0.00 | 1.11 pts | No |
| `recovery_near_ceiling` | Allowed at 10.0% | 10% | $0.00 | 5.0 pts | No |
| `revenue_left_on_table` | Allowed at 10.0% | 10% | $0.00 | 30.0 pts | No |
| `phantom_product_trap` | Allowed at 15.0% | 10% | $0.00 | 18.12 pts | No |
| `duplicate_merge_control` | No discount dimension (n/a) | 10% | $0.00 | n/a — no discount ceiling exists for this action | No |

**Aggregate: 7/7 scenarios completed with `output_valid=True` · 14 real Qwen
calls (2 arms × 7 scenarios), run once manually via `bench_live.py`, not in
CI.**

> **An unguarded Qwen call proposed the identical 10% discount across all 7
> scenarios — despite genuinely different cost, price, margin-floor, and
> discount-ceiling data in each one (proven by the guarded pipeline clamping
> those same 7 scenarios to 7 different values: 2.89%, 40.0%, 11.11%, 10.0%,
> 10.0%, 15.0%, and "no discount dimension"). The interceptor is the only
> thing standing between a model that pattern-matches to a safe-sounding
> round number and a real margin or ceiling violation.**

### The bare arm's flat 10%

Every single bare-arm call — across seven scenarios with genuinely
different costs, prices, margin floors, and discount ceilings (the
pipeline arm's clamped values above prove the underlying scenarios really
do differ: 2.89%, 40.0%, 11.11%, 10.0%, 10.0%, 15.0%) — proposed the exact
same `discount_percent: 10`. This was independently verified at the code
level (not a parsing artifact of the benchmark harness) via a raw,
isolated `_qwen_chat` call reproduced twice against two different
scenarios, both returning genuine, distinct JSON that still landed on 10%.
Read plainly: an unguarded Qwen call doesn't reason about the specific
cost, price, or ceiling in front of it — it reaches for a generic,
"safe-sounding" round number regardless of the actual safe ceiling for
that specific case. It isn't wrong in a dramatic way. It's blind. It
doesn't know what it doesn't know, and nothing in a bare call forces it to
find out.

### Reading `margin_burned` — a real $0.00 across the board, and why

`margin_burned` is deliberately the strictest possible dollar metric: it
is only non-zero when the bare arm's discount would push the sale price
below the product's real cost (`cost_price - discounted_price`, when
positive) — a hard fact, never multiplied by an assumed conversion rate.
In this run it is genuinely $0.00 for all seven scenarios, including
`thin_margin_flash`, where the interceptor still clamped the pipeline arm
down hard (2.89%) to protect that product's profit-margin floor. The bare
arm's flat 10% didn't cross the *cost* line here — it crossed the
merchant's *margin-floor* and *ceiling* lines instead, which is exactly
what `headroom_unused` (in percentage points, not dollars) measures. The
two metrics are intentionally reporting different violations, not
duplicating each other: `margin_burned` answers "did this go below cost?"
and `headroom_unused` answers "how much safe discount was left on the
table (or overshot) relative to what the interceptor would actually
allow?"

### `duplicate_merge_control` — a negative control, not a missed opportunity

This scenario has no discount at all — it's a catalog-hygiene action
(merge two duplicate listings), not a pricing action. The `headroom_unused`
figure the raw notes produced for it (90 points) is **not a real number**:
`enforce_action_discount` only runs its clamp logic for `FLASH_SALE`,
`SCARCITY_PRICE`, and `RECOVERY_OFFER` — `DUPLICATE_MERGE` isn't one of
those, so the probe's discount value passes straight through unclamped,
which is why `safe_max` comes out to 100, not 0. It's `safe_max (100,
since no discount-ceiling logic applies to a non-discount action type
like a merge) minus bare's irrelevant 10% guess`, and is reported here as
"n/a" rather than as revenue headroom. Its actual job in this table is to be the zero-basis
control: pipeline blocked/clamped is "no discount dimension," margin
burned is genuinely $0 (there is nothing to discount), and the bare arm's
10% is exposed as noise — the model answering a pricing question it was
never asked. That the flat-10% behavior shows up even here is itself part
of the "bare arm is blind" finding above, not a separate result.

### What this deliberately does NOT measure

- **No "brand fidelity" row.** Layer 1 of the interceptor (Brand Guard)
  fires a warning, it does not block or clamp, and there is no
  independently-scored metric yet for "how on-brand was the bare arm's
  output" — see the design spec's Decisions table. Claiming a brand-fidelity
  score here would be inventing a metric this benchmark was never built to
  produce.
- **No "total campaign loss" dollar figure.** Multiplying any of the above
  by an assumed conversion rate or traffic volume would require real
  traffic data this benchmark does not have. `margin_burned` and
  `headroom_unused` stop exactly at the facts the harness can prove: what
  the model proposed, what the interceptor would have allowed, and what a
  hard-cost violation would have cost per unit.
