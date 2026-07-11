"""
Benchmarks — measure Qwen call performance and output quality.

Run with: pytest tests/test_benchmarks.py -v

This file defines the BenchmarkResult/BenchmarkReport infrastructure and the
5 scenario definitions, tested here with mock data so the harness itself is
covered without spending tokens on every CI run.

For a real run against the live Qwen API, see bench_live.py — it imports
BenchmarkResult/BenchmarkReport from this file and drives the actual
service functions (analyze_logo, generate_brand, decision cycle tool-calling,
analyze_product_image, generate_descriptions).
"""
import time
import statistics
import pytest
from dataclasses import dataclass, field
from typing import Any


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class BenchmarkResult:
    """One benchmark scenario result."""
    name: str
    latency_ms: float
    token_estimate: int  # rough char/4
    output_valid: bool   # passed schema validation
    output_quality: str  # "good" | "acceptable" | "poor" | "failed"
    notes: str = ""


@dataclass
class BenchmarkReport:
    """Aggregate results across all scenarios."""
    results: list[BenchmarkResult] = field(default_factory=list)

    def add(self, result: BenchmarkResult):
        self.results.append(result)

    @property
    def avg_latency_ms(self) -> float:
        times = [r.latency_ms for r in self.results]
        return statistics.mean(times) if times else 0.0

    @property
    def valid_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.output_valid) / len(self.results)

    @property
    def quality_distribution(self) -> dict[str, int]:
        dist: dict[str, int] = {}
        for r in self.results:
            dist[r.output_quality] = dist.get(r.output_quality, 0) + 1
        return dist

    def summary(self) -> str:
        lines = [
            f"Benchmark Report ({len(self.results)} scenarios)",
            f"  Avg latency: {self.avg_latency_ms:.0f}ms",
            f"  Valid rate: {self.valid_rate:.0%}",
            f"  Quality: {self.quality_distribution}",
        ]
        for r in self.results:
            status = "✓" if r.output_valid else "✗"
            lines.append(f"  {status} {r.name}: {r.latency_ms:.0f}ms ({r.output_quality})")
        return "\n".join(lines)


# ── Infrastructure tests (mock, no API calls) ────────────────────────────────

class TestBenchmarkInfrastructure:
    """Verify the benchmark framework works — uses mocks, no API calls."""

    def test_benchmark_result_creation(self):
        result = BenchmarkResult(
            name="test_scenario",
            latency_ms=1500.0,
            token_estimate=200,
            output_valid=True,
            output_quality="good",
        )
        assert result.name == "test_scenario"
        assert result.output_valid

    def test_benchmark_report_aggregation(self):
        report = BenchmarkReport()
        report.add(BenchmarkResult("a", 1000, 100, True, "good"))
        report.add(BenchmarkResult("b", 2000, 200, True, "acceptable"))
        report.add(BenchmarkResult("c", 3000, 300, False, "failed"))
        assert report.avg_latency_ms == 2000.0
        assert report.valid_rate == pytest.approx(2/3)
        assert report.quality_distribution == {"good": 1, "acceptable": 1, "failed": 1}

    def test_empty_report(self):
        report = BenchmarkReport()
        assert report.avg_latency_ms == 0.0
        assert report.valid_rate == 0.0

    def test_report_summary_format(self):
        report = BenchmarkReport()
        report.add(BenchmarkResult("brand_gen", 5000, 800, True, "good"))
        summary = report.summary()
        assert "brand_gen" in summary
        assert "5000ms" in summary


# ── Scenario definitions ──────────────────────────────────────────────────────

# Define scenarios as data (no Qwen calls needed)
BENCHMARK_SCENARIOS = [
    {
        "name": "logo_analysis",
        "model": "qwen-vl-max",
        "description": "Analyze a fashion brand logo",
        "expected_fields": ["palette", "mood", "style", "geometry"],
        "max_tokens": 512,
    },
    {
        "name": "brand_generation",
        "model": "qwen-max",
        "description": "Generate full brand identity from logo analysis",
        "expected_fields": ["palette", "typography", "brand_voice_profile", "guard_rules"],
        "max_tokens": 2500,
    },
    {
        "name": "decision_cycle",
        "model": "qwen-max",
        "description": "Propose one action from anomaly + store state",
        "expected_fields": ["tool_calls"],
        "max_tokens": 1000,
    },
    {
        "name": "product_vision",
        "model": "qwen-vl-max",
        "description": "Identify and describe a product from its photo",
        "expected_fields": ["name", "category", "colors", "suggested_price", "confident"],
        "max_tokens": 400,
    },
    {
        "name": "batch_descriptions",
        "model": "qwen-max",
        "description": "Generate descriptions for 5 products in one call",
        "expected_fields": ["descriptions"],
        "max_tokens": 2000,
    },
]


class TestScenarioDefinitions:
    """Verify benchmark scenario definitions are valid."""

    def test_five_scenarios_defined(self):
        assert len(BENCHMARK_SCENARIOS) == 5

    def test_all_scenarios_have_required_fields(self):
        for s in BENCHMARK_SCENARIOS:
            assert "name" in s
            assert "model" in s
            assert "description" in s
            assert "expected_fields" in s
            assert "max_tokens" in s
            assert s["model"] in ("qwen-max", "qwen-vl-max", "qwen-plus")

    def test_scenario_names_are_unique(self):
        names = [s["name"] for s in BENCHMARK_SCENARIOS]
        assert len(names) == len(set(names))

    def test_token_limits_are_reasonable(self):
        for s in BENCHMARK_SCENARIOS:
            assert 100 <= s["max_tokens"] <= 4000, f"{s['name']} has unreasonable max_tokens"

    def test_expected_fields_are_nonempty(self):
        for s in BENCHMARK_SCENARIOS:
            assert len(s["expected_fields"]) > 0, f"{s['name']} has no expected fields"


# ── Mock benchmark run (end-to-end pipeline, no API calls) ────────────────────

class TestMockBenchmarkRun:
    """Simulate a full benchmark run with mock data — verifies the pipeline."""

    def test_full_mock_run(self):
        """Run all 5 scenarios with mock results and verify the report."""
        report = BenchmarkReport()

        # Simulate results for each scenario
        mock_results = [
            ("logo_analysis", 12000, 200, True, "good"),
            ("brand_generation", 38000, 800, True, "good"),
            ("decision_cycle", 8000, 500, True, "acceptable"),
            ("product_vision", 15000, 300, True, "good"),
            ("batch_descriptions", 25000, 600, True, "acceptable"),
        ]

        for name, latency, tokens, valid, quality in mock_results:
            report.add(BenchmarkResult(
                name=name,
                latency_ms=latency,
                token_estimate=tokens,
                output_valid=valid,
                output_quality=quality,
            ))

        # Verify aggregate metrics
        assert len(report.results) == 5
        assert report.valid_rate == 1.0
        assert report.avg_latency_ms > 0
        assert "good" in report.quality_distribution

        # Summary should be printable
        summary = report.summary()
        assert "logo_analysis" in summary
        assert "brand_generation" in summary
        assert "100%" in summary

    def test_partial_failure_run(self):
        """Simulate a run where some scenarios fail."""
        report = BenchmarkReport()
        report.add(BenchmarkResult("logo_analysis", 12000, 200, True, "good"))
        report.add(BenchmarkResult("brand_generation", 45000, 800, False, "failed", "timeout"))
        report.add(BenchmarkResult("decision_cycle", 8000, 500, True, "good"))
        report.add(BenchmarkResult("product_vision", 15000, 300, False, "poor", "malformed JSON"))
        report.add(BenchmarkResult("batch_descriptions", 25000, 600, True, "acceptable"))

        assert report.valid_rate == pytest.approx(3/5)
        assert report.quality_distribution["failed"] == 1
        assert report.quality_distribution["poor"] == 1

    def test_latency_statistics(self):
        """Verify statistical calculations are correct."""
        report = BenchmarkReport()
        latencies = [10000, 20000, 30000, 40000, 50000]
        for i, lat in enumerate(latencies):
            report.add(BenchmarkResult(f"scenario_{i}", lat, 100, True, "good"))

        assert report.avg_latency_ms == 30000.0


# ──────────────────────────────────────────────────────────────────────────────
# LIVE BENCHMARKS (require QWEN_API_KEY) — see bench_live.py
# ──────────────────────────────────────────────────────────────────────────────
#
# To run live benchmarks:
#   1. Set QWEN_API_KEY in your environment
#   2. Run: python -m tests.bench_live   (from analytics-brain/, or inside
#      the api container: docker compose exec api python -m tests.bench_live)
#
# bench_live.py calls the real service functions directly (no server/DB/Redis
# needed) and measures, per scenario:
#   - Actual latency
#   - Token estimate (chars/4 heuristic — response usage isn't always exposed)
#   - Output validity (did it pass Pydantic validation)
#   - Output quality (heuristic per scenario, e.g. guard rules present)
#
# Results are printed as a formatted report at the end.
# Copy the report into BENCHMARKS.md for the public repo.
# ──────────────────────────────────────────────────────────────────────────────
