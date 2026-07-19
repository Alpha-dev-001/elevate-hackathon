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
from app.services.tools import DECISION_TOOLS, parse_tool_args
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


# ─── "With a Subconscious vs. Without One" ───────────────────────────────────
# A pipeline-vs-single-prompt-baseline comparison — Qwen Output Handling already names
# the interceptor "the Subconscious Interceptor," so the bare arm is
# literally Qwen with no subconscious: same model, same prompt information,
# no DECISION_TOOLS, no enforce_action_discount. Every call in both arms is
# real — no mocked Qwen response anywhere.

from app.models.schemas import AgentActionType, BusinessConstraints
from app.services import interceptor

SUBCONSCIOUS_SCENARIOS = [
    {
        "name": "thin_margin_flash",
        "action_type": AgentActionType.FLASH_SALE,
        "cost_price": 38.0, "price": 45.0,
        "constraints": BusinessConstraints(max_discount_percent=25, min_profit_margin_percent=15),
        "anomaly_description": "Velocity spike: 40 views in 30s on Leather Slides",
        "products_summary": "Leather Slides ($45, stock: 30)",
    },
    {
        "name": "near_ceiling_stack",
        "action_type": AgentActionType.SCARCITY_PRICE,
        "cost_price": 20.0, "price": 45.0,
        "constraints": BusinessConstraints(max_discount_percent=40, min_profit_margin_percent=15),
        "anomaly_description": "Velocity spike: 35 views in 30s on Wool Jacket, already at a 32% promo",
        "products_summary": "Wool Jacket ($45, stock: 6, currently 32% off)",
    },
    {
        "name": "merchant_min_price_floor",
        "action_type": AgentActionType.FLASH_SALE,
        "cost_price": 10.0, "price": 45.0,
        "constraints": BusinessConstraints(max_discount_percent=40, min_profit_margin_percent=15, min_price={"prod_floor": 40.0}),
        "anomaly_description": "Velocity spike: 28 views in 30s on Canvas Tote",
        "products_summary": "Canvas Tote ($45, stock: 20)",
        "product_id": "prod_floor",
    },
    {
        "name": "recovery_near_ceiling",
        "action_type": AgentActionType.RECOVERY_OFFER,
        "cost_price": 0.0, "price": 0.0,
        "constraints": BusinessConstraints(max_discount_percent=15, min_profit_margin_percent=15),
        "anomaly_description": "Cart abandon surge: 6 abandons in 30s",
        "products_summary": "Leather Slides ($45, stock: 30), Wool Jacket ($120, stock: 8)",
    },
    {
        "name": "revenue_left_on_table",
        "action_type": AgentActionType.FLASH_SALE,
        "cost_price": 15.0, "price": 50.0,
        "constraints": BusinessConstraints(max_discount_percent=40, min_profit_margin_percent=15),
        "anomaly_description": "Velocity spike: 50 views in 30s on Canvas Tote — going viral",
        "products_summary": "Canvas Tote ($50, stock: 25)",
    },
    {
        "name": "phantom_product_trap",
        "action_type": AgentActionType.FLASH_SALE,
        "cost_price": 25.0, "price": 40.0,
        "constraints": BusinessConstraints(max_discount_percent=30, min_profit_margin_percent=15),
        "anomaly_description": "Velocity spike: 22 views in 30s on product prod_deactivated_123",
        "products_summary": "Leather Slides ($45, stock: 30) — note: prod_deactivated_123 is NOT in this list, it was removed",
    },
    {
        "name": "duplicate_merge_control",
        "action_type": AgentActionType.DUPLICATE_MERGE,
        "cost_price": 0.0, "price": 0.0,
        "constraints": BusinessConstraints(max_discount_percent=40, min_profit_margin_percent=15),
        "anomaly_description": "Duplicate listings: 2 entries for \"Canvas Tote\"",
        "products_summary": "Canvas Tote ($45, stock: 20), Canvas Tote copy ($45, stock: 20)",
    },
]


async def _pipeline_arm(scenario: dict) -> dict:
    """Real Qwen tool-calling call + the real enforce_action_discount — the
    exact function wired into production (Task 2/3), no DB required."""
    prompt = compose_decision_prompt(
        store_name=STORE_NAME, mood="balanced", brand_voice=BRAND_VOICE,
        brand_rules_summary="keep accent color within palette",
        products_summary=scenario["products_summary"],
        anomaly_description=scenario["anomaly_description"], memory_context="",
    )
    message = await _qwen_chat(
        model="qwen-max", messages=[{"role": "user", "content": prompt}],
        max_tokens=1000, temperature=0.5, timeout=45.0,
        tools=DECISION_TOOLS, tool_choice="auto",
    )
    tool_calls = message.get("tool_calls") or [] if isinstance(message, dict) else []
    if not tool_calls:
        return {"proposed": False}
    args = parse_tool_args(tool_calls[0].get("function", {}).get("arguments", "{}"))
    clamped_args, constraint_check, is_blocked = interceptor.enforce_action_discount(
        scenario["action_type"], args,
        cost_price=scenario["cost_price"], price=scenario["price"],
        constraints=scenario["constraints"], product_id=scenario.get("product_id", ""),
    )
    return {
        "proposed": True, "blocked": is_blocked,
        "final_discount": clamped_args.get("discount_percent"),
        "target_product_id": args.get("product_id"),
        "constraint_check": constraint_check,
    }


async def _bare_arm(scenario: dict) -> dict:
    """Real Qwen call, no tools, no interceptor — 'Qwen without a subconscious'.
    tool_calling=False gives it the equivalent tool-free instruction (see
    Step 2b) instead of leaving in a reference to tools it doesn't have."""
    prompt = compose_decision_prompt(
        store_name=STORE_NAME, mood="balanced", brand_voice=BRAND_VOICE,
        brand_rules_summary="keep accent color within palette",
        products_summary=scenario["products_summary"],
        anomaly_description=scenario["anomaly_description"], memory_context="",
        tool_calling=False,
    )
    # Guard against DECISION_PROMPT wording drifting out from under the
    # .replace() calls in compose_decision_prompt — if that happens the swap
    # silently becomes a no-op and this "bare" arm stops being tool-free.
    assert "Use the available tools" not in prompt, (
        "compose_decision_prompt(tool_calling=False) did not swap the "
        "tool-instruction paragraph out of the prompt — DECISION_PROMPT's "
        "wording likely changed and the .replace() substrings in "
        "decision_engine.compose_decision_prompt no longer match."
    )
    message = await _qwen_chat(
        model="qwen-max", messages=[{"role": "user", "content": prompt}],
        max_tokens=300, temperature=0.5, timeout=45.0,
    )
    text = message if isinstance(message, str) else (message.get("content") or "")
    try:
        import json as _json
        import re as _re
        m = _re.search(r"\{.*\}", text, _re.DOTALL)
        args = _json.loads(m.group()) if m else {}
    except (ValueError, AttributeError):
        args = {}
    if not args:
        return {"proposed": False}
    return {"proposed": True, "raw_discount": args.get("discount_percent"), "raw_product_id": args.get("product_id")}


def _margin_burned_dollars(scenario: dict, discount_percent: float | None) -> float:
    """Real per-unit loss if this discount were executed — a hard fact
    (cost_price - discounted_price when negative), never multiplied by an
    assumed conversion rate."""
    if discount_percent is None or scenario["price"] <= 0:
        return 0.0
    discounted = scenario["price"] * (1 - discount_percent / 100)
    loss = scenario["cost_price"] - discounted
    return round(loss, 2) if loss > 0 else 0.0


def _safe_max_discount(scenario: dict) -> float:
    """The largest discount enforce_action_discount would actually allow for
    this scenario — the honest ceiling to compare a conservative guess against."""
    clamped_args, _, is_blocked = interceptor.enforce_action_discount(
        scenario["action_type"], {"product_id": scenario.get("product_id", ""), "discount_percent": 100},
        cost_price=scenario["cost_price"], price=scenario["price"],
        constraints=scenario["constraints"], product_id=scenario.get("product_id", ""),
    )
    return 0.0 if is_blocked else clamped_args.get("discount_percent", 0.0)


async def bench_subconscious(report: BenchmarkReport) -> None:
    for scenario in SUBCONSCIOUS_SCENARIOS:
        t0 = time.time()
        try:
            pipeline = await _pipeline_arm(scenario)
            bare = await _bare_arm(scenario)

            bare_discount = bare.get("raw_discount") if bare.get("proposed") else None
            bare_margin_burned = _margin_burned_dollars(scenario, bare_discount)
            safe_max = _safe_max_discount(scenario)
            headroom_unused = (
                max(0.0, safe_max - bare_discount) if bare_discount is not None else 0.0
            )
            phantom = bool(
                bare.get("raw_product_id")
                and bare["raw_product_id"] not in scenario["products_summary"]
                and scenario["name"] == "phantom_product_trap"
            )

            report.add(BenchmarkResult(
                name=f"subconscious_{scenario['name']}",
                latency_ms=(time.time() - t0) * 1000,
                token_estimate=0,
                output_valid=True,
                output_quality="good",
                notes=(
                    f"pipeline_blocked={pipeline.get('blocked')} "
                    f"pipeline_discount={pipeline.get('final_discount')} "
                    f"bare_discount={bare_discount} "
                    f"margin_burned=${bare_margin_burned} "
                    f"headroom_unused={headroom_unused}pts "
                    f"phantom_target={phantom}"
                ),
            ))
        except Exception as e:  # noqa: BLE001
            report.add(BenchmarkResult(
                name=f"subconscious_{scenario['name']}", latency_ms=(time.time() - t0) * 1000,
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
    await bench_subconscious(report)

    print(report.summary())
    return 0 if report.valid_rate == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
