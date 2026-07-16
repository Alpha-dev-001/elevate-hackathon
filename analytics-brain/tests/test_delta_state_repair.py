"""SystemState cached in Redis before baseline_price existed on Product must
not 500 every request against that store forever — load_state self-heals
by backfilling the missing field instead of crashing. Real bug found live:
the "Xair" demo store's cached state predated baseline_price, and every
request touching it (storefront, /builder) 500'd until this fix."""
import asyncio
import json
from unittest.mock import AsyncMock, patch

from app.services.delta import load_state, _repair_stale_products


def _run(coro):
    return asyncio.run(coro)


STALE_STATE_JSON = json.dumps({
    "version": 1,
    "last_updated": 0,
    "products": {
        "p1": {
            "id": "p1", "merchant_id": "m1", "name": "Widget", "description": None,
            "price": 40.0, "cost_price": 20.0, "stock": 5, "category": "misc",
            "image_urls": [], "is_active": True, "qwen_generated_description": False,
            "is_featured": False, "featured_label": None,
            # baseline_price deliberately omitted — the stale-cache scenario
        },
    },
    "active_promos": {},
    "layout_config": {},
    "qr_campaigns": {},
})


class TestRepairStaleProducts:
    def test_backfills_missing_baseline_price_from_price(self):
        state_dict = json.loads(STALE_STATE_JSON)
        repaired = _repair_stale_products(state_dict)
        assert repaired["products"]["p1"]["baseline_price"] == 40.0

    def test_leaves_present_baseline_price_untouched(self):
        state_dict = json.loads(STALE_STATE_JSON)
        state_dict["products"]["p1"]["baseline_price"] = 55.0
        repaired = _repair_stale_products(state_dict)
        assert repaired["products"]["p1"]["baseline_price"] == 55.0


class TestLoadStateSelfHeals:
    def test_stale_cached_state_loads_instead_of_raising(self):
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=STALE_STATE_JSON)
        redis_mock.set = AsyncMock()

        with patch("app.services.delta.get_redis", new_callable=AsyncMock, return_value=redis_mock):
            state = _run(load_state("m1"))

        assert state is not None
        assert state.products["p1"].baseline_price == 40.0

    def test_repair_is_written_back_to_redis(self):
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=STALE_STATE_JSON)
        redis_mock.set = AsyncMock()

        with patch("app.services.delta.get_redis", new_callable=AsyncMock, return_value=redis_mock):
            _run(load_state("m1"))

        redis_mock.set.assert_awaited_once()

    def test_no_cached_state_returns_none(self):
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)

        with patch("app.services.delta.get_redis", new_callable=AsyncMock, return_value=redis_mock):
            assert _run(load_state("m1")) is None

    def test_healthy_state_round_trips_unchanged(self):
        healthy = json.loads(STALE_STATE_JSON)
        healthy["products"]["p1"]["baseline_price"] = 40.0
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=json.dumps(healthy))
        redis_mock.set = AsyncMock()

        with patch("app.services.delta.get_redis", new_callable=AsyncMock, return_value=redis_mock):
            state = _run(load_state("m1"))

        assert state.products["p1"].baseline_price == 40.0
        redis_mock.set.assert_not_awaited()  # no repair needed, no rewrite
