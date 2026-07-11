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
