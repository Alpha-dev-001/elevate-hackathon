"""
Live Qwen benchmark run — the 5 scenarios defined in test_benchmarks.py,
executed against the real Qwen API. Nothing mocked, no server required
(calls the service functions directly).

Requires QWEN_API_KEY in the environment.

Run:
  docker compose exec api python -m tests.bench_live
  (or, from analytics-brain/: python -m tests.bench_live)

Prints a BenchmarkReport summary. Copy the output into BENCHMARKS.md.
"""
from __future__ import annotations

import asyncio
import time

from app.services import vision
from app.services.brand import generate_brand, generate_descriptions, analyze_logo, _qwen_chat
from app.services.decision_engine import compose_decision_prompt
from app.services.tools import DECISION_TOOLS
from app.models.schemas import ProductCSVRow
from tests.test_benchmarks import BenchmarkResult, BenchmarkReport

# Public Alibaba-hosted image reused from the other live tests — reachable by
# qwen-vl-max without a real OSS bucket. Not a real logo or product photo;
# stands in so the benchmark measures the Qwen round-trip, not fixture setup.
IMAGE = "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241022/emyrja/dog_and_girl.jpeg"

STORE_NAME = "Aurora Bench"
CATEGORY = "footwear"
DESCRIPTION = "Minimalist, considered footwear for people who notice detail."
BRAND_VOICE = "warm and confident"


async def bench_logo_analysis(report: BenchmarkReport):
    t0 = time.time()
    try:
        analysis = await analyze_logo(IMAGE)
        report.add(BenchmarkResult(
            name="logo_analysis",
            latency_ms=(time.time() - t0) * 1000,
            token_estimate=len(str(analysis.model_dump())) // 4,
            output_valid=True,
            output_quality="good",
        ))
        return analysis
    except Exception as e:  # noqa: BLE001 — benchmark must capture, not raise
        report.add(BenchmarkResult(
            name="logo_analysis", latency_ms=(time.time() - t0) * 1000,
            token_estimate=0, output_valid=False, output_quality="failed", notes=str(e),
        ))
        return None


async def bench_brand_generation(report: BenchmarkReport, analysis):
    if analysis is None:
        report.add(BenchmarkResult(
            name="brand_generation", latency_ms=0, token_estimate=0,
            output_valid=False, output_quality="failed", notes="skipped — logo_analysis failed",
        ))
        return
    t0 = time.time()
    try:
        brand, guards = await generate_brand(analysis, STORE_NAME, CATEGORY, DESCRIPTION)
        quality = "good" if guards.rules else "acceptable"
        report.add(BenchmarkResult(
            name="brand_generation",
            latency_ms=(time.time() - t0) * 1000,
            token_estimate=len(str(brand.model_dump())) // 4,
            output_valid=True,
            output_quality=quality,
            notes=f"{len(guards.rules)} guard rules",
        ))
    except Exception as e:  # noqa: BLE001
        report.add(BenchmarkResult(
            name="brand_generation", latency_ms=(time.time() - t0) * 1000,
            token_estimate=0, output_valid=False, output_quality="failed", notes=str(e),
        ))


async def bench_decision_cycle(report: BenchmarkReport):
    prompt = compose_decision_prompt(
        store_name=STORE_NAME,
        mood="balanced",
        brand_voice=BRAND_VOICE,
        brand_rules_summary="keep accent color within palette; no clashing warm/cool combos",
        products_summary="Leather Slides ($45, stock: 30), Wool Jacket ($120, stock: 8)",
        anomaly_description="Velocity spike: 14 views in 30s on Leather Slides",
        memory_context="",
    )
    t0 = time.time()
    try:
        message = await _qwen_chat(
            model="qwen-max",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.5,
            timeout=45.0,
            tools=DECISION_TOOLS,
            tool_choice="auto",
        )
        tool_calls = message.get("tool_calls") or [] if isinstance(message, dict) else []
        valid = bool(tool_calls)
        report.add(BenchmarkResult(
            name="decision_cycle",
            latency_ms=(time.time() - t0) * 1000,
            token_estimate=len(prompt) // 4,
            output_valid=valid,
            output_quality="good" if valid else "acceptable",
            notes=(tool_calls[0].get("function", {}).get("name", "") if valid else "declined to call a tool"),
        ))
    except Exception as e:  # noqa: BLE001
        report.add(BenchmarkResult(
            name="decision_cycle", latency_ms=(time.time() - t0) * 1000,
            token_estimate=0, output_valid=False, output_quality="failed", notes=str(e),
        ))


async def bench_product_vision(report: BenchmarkReport):
    t0 = time.time()
    try:
        result = await vision.analyze_product_image(
            image_ref=IMAGE, store_name=STORE_NAME, brand_voice=BRAND_VOICE, baseline_price=40.0,
        )
        report.add(BenchmarkResult(
            name="product_vision",
            latency_ms=(time.time() - t0) * 1000,
            token_estimate=len(str(result.model_dump())) // 4,
            output_valid=True,
            output_quality="good" if result.confident else "acceptable",
            notes=f"confident={result.confident}",
        ))
    except Exception as e:  # noqa: BLE001
        report.add(BenchmarkResult(
            name="product_vision", latency_ms=(time.time() - t0) * 1000,
            token_estimate=0, output_valid=False, output_quality="failed", notes=str(e),
        ))


async def bench_batch_descriptions(report: BenchmarkReport):
    products = [
        ProductCSVRow(name="Leather Slides", price=45.0, stock=30, category="footwear"),
        ProductCSVRow(name="Wool Jacket", price=120.0, stock=8, category="apparel"),
        ProductCSVRow(name="Canvas Tote", price=35.0, stock=15, category="bags"),
    ]
    t0 = time.time()
    try:
        descriptions, fallbacks = await generate_descriptions(products, BRAND_VOICE)
        got_real_copy = len(descriptions) - len(fallbacks)
        report.add(BenchmarkResult(
            name="batch_descriptions",
            latency_ms=(time.time() - t0) * 1000,
            token_estimate=sum(len(d) for d in descriptions.values()) // 4,
            output_valid=got_real_copy == len(products),
            output_quality="good" if not fallbacks else "acceptable",
            notes=f"{got_real_copy}/{len(products)} real copy, {len(fallbacks)} fallback",
        ))
    except Exception as e:  # noqa: BLE001
        report.add(BenchmarkResult(
            name="batch_descriptions", latency_ms=(time.time() - t0) * 1000,
            token_estimate=0, output_valid=False, output_quality="failed", notes=str(e),
        ))


async def main() -> int:
    report = BenchmarkReport()
    analysis = await bench_logo_analysis(report)
    # Sequential on purpose — mirrors real onboarding order and keeps output
    # deterministic to read; the 5 calls together are what a real merchant's
    # first minute of Elevate costs in latency.
    await bench_brand_generation(report, analysis)
    await bench_decision_cycle(report)
    await bench_product_vision(report)
    await bench_batch_descriptions(report)

    print(report.summary())
    return 0 if report.valid_rate == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
