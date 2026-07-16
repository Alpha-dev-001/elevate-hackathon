"""Tests for duplicate_scan's pure grouping/selection/hashing logic — the
5th autopilot trigger. Same convention as test_store_review.py: test the
pure functions directly. The DB/Redis/Qwen-touching I/O wrappers
(find_duplicate_group, run_duplicate_scan) follow store_review.py's own
precedent of having no dedicated unit test — see the plan's Task 5 note."""
import re

from app.models.db_models import ProductDB
from app.services.duplicate_scan import (
    group_by_primary_image,
    duplicate_candidate_groups,
    format_duplicate_description,
    _duplicate_group_hash,
)


def _product(id, name, image_url=None, qwen_generated=True):
    return ProductDB(
        id=id, merchant_id="m1", name=name, price=10.0, cost_price=5.0,
        image_urls=[image_url] if image_url else [],
        qwen_generated_description=qwen_generated,
    )


class TestGroupByPrimaryImage:
    def test_empty_list_returns_empty_dict(self):
        assert group_by_primary_image([]) == {}

    def test_products_without_images_are_excluded(self):
        products = [_product("p1", "A"), _product("p2", "B")]
        assert group_by_primary_image(products) == {}

    def test_groups_by_first_image_url(self):
        products = [
            _product("p1", "A", "https://x/a.jpg"),
            _product("p2", "A copy", "https://x/a.jpg"),
            _product("p3", "B", "https://x/b.jpg"),
        ]
        groups = group_by_primary_image(products)
        assert set(groups.keys()) == {"https://x/a.jpg", "https://x/b.jpg"}
        assert [p.id for p in groups["https://x/a.jpg"]] == ["p1", "p2"]
        assert [p.id for p in groups["https://x/b.jpg"]] == ["p3"]

    def test_single_product_per_image_still_grouped(self):
        """Grouping doesn't filter singletons — callers check len(group) >= 2."""
        products = [_product("p1", "A", "https://x/a.jpg")]
        assert len(group_by_primary_image(products)["https://x/a.jpg"]) == 1


class TestDuplicateCandidateGroups:
    """Same image_url is necessary but not sufficient for auto-merge — a
    shared stock/placeholder photo across genuinely different products
    (common in CSV imports) must never be treated as a duplicate."""

    def test_same_image_same_name_is_a_candidate(self):
        products = [
            _product("p1", "AirPods 2", "https://x/a.jpg"),
            _product("p2", "AirPods 2", "https://x/a.jpg"),
        ]
        groups = duplicate_candidate_groups(products)
        assert len(groups) == 1
        assert {p.id for p in groups[0]} == {"p1", "p2"}

    def test_same_image_different_name_is_not_a_candidate(self):
        """The exact scenario a shared placeholder/stock photo produces:
        two unrelated products, one image_url. Must not be flagged."""
        products = [
            _product("p1", "Xbox Series X", "https://x/placeholder.jpg"),
            _product("p2", "Logitech MX Master Mouse", "https://x/placeholder.jpg"),
        ]
        assert duplicate_candidate_groups(products) == []

    def test_name_match_is_case_and_whitespace_insensitive(self):
        products = [
            _product("p1", "Leather Slides", "https://x/a.jpg"),
            _product("p2", "  leather   slides ", "https://x/a.jpg"),
        ]
        groups = duplicate_candidate_groups(products)
        assert len(groups) == 1
        assert {p.id for p in groups[0]} == {"p1", "p2"}

    def test_three_way_split_by_name_within_one_image(self):
        """Two products share a name (real duplicate) and a third shares
        only the image (different item) — only the matching pair returns."""
        products = [
            _product("p1", "Slides", "https://x/a.jpg"),
            _product("p2", "Slides", "https://x/a.jpg"),
            _product("p3", "Sandals", "https://x/a.jpg"),
        ]
        groups = duplicate_candidate_groups(products)
        assert len(groups) == 1
        assert {p.id for p in groups[0]} == {"p1", "p2"}


class TestFormatDuplicateDescription:
    def test_count_leads_the_sentence(self):
        """decision_engine._extract_count() greps the first \\d+ in the
        description for the grounded GMV estimate — the duplicate count
        must be the first digit token, ahead of any digit in a product id
        (e.g. prod_0, prod_1) or name."""
        group = [_product(f"prod_{i}", "AirPods 2") for i in range(3)]
        desc = format_duplicate_description(group)
        m = re.search(r"\d+", desc)
        assert m.group() == "3"

    def test_includes_product_ids_for_qwen_to_target(self):
        """decision_engine's DECISION_PROMPT only ever passes name/price/stock
        in products_summary, never IDs — propose_duplicate_merge's tool call
        needs real product IDs to act on, so the anomaly text must carry them
        directly, the same way the reactive trigger's anomaly text already
        embeds the spiking product's ID (behavior_tracker.anomaly_description)."""
        group = [_product("prod_aaa", "Slides"), _product("prod_bbb", "Slides")]
        desc = format_duplicate_description(group)
        assert "prod_aaa" in desc
        assert "prod_bbb" in desc

    def test_includes_product_name(self):
        group = [_product("p1", "Leather Slides"), _product("p2", "Leather Slides")]
        assert "Leather Slides" in format_duplicate_description(group)


class TestDuplicateGroupHash:
    def test_deterministic(self):
        assert _duplicate_group_hash(["p1", "p2"]) == _duplicate_group_hash(["p1", "p2"])

    def test_order_independent(self):
        """Same group, different arg order → same hash — callers (detection
        time vs. dismiss time) can't guarantee the same ordering."""
        assert _duplicate_group_hash(["p1", "p2"]) == _duplicate_group_hash(["p2", "p1"])

    def test_different_groups_differ(self):
        assert _duplicate_group_hash(["p1", "p2"]) != _duplicate_group_hash(["p1", "p3"])
