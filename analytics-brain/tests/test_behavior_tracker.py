"""Tests for behavior_tracker.anomaly_description — per-product targeting."""
import os

# Override thresholds before importing the module
os.environ["ANOMALY_THRESHOLD"] = "5"
os.environ["ANOMALY_WINDOW_SECONDS"] = "30"

from app.services.behavior_tracker import anomaly_description


class TestAnomalyDescription:
    """anomaly_description returns (description, product_id) tuples."""

    def test_no_anomaly_below_threshold(self):
        desc, pid = anomaly_description(2, 10)
        assert desc is None
        assert pid is None

    def test_abandon_surge_no_product(self):
        """Abandon surge is store-wide — no single product to target."""
        desc, pid = anomaly_description(5, 0)
        assert desc is not None
        assert "Cart abandon surge" in desc
        assert "5 abandons" in desc
        assert pid is None

    def test_abandon_surge_ignores_per_product_views(self):
        """Abandon surge takes priority over velocity even with per-product data."""
        desc, pid = anomaly_description(
            7, 25, {"prod-1": 15, "prod-2": 10}
        )
        assert "Cart abandon surge" in desc
        assert pid is None

    def test_velocity_spike_with_per_product_views(self):
        """Velocity spike identifies the spiking product."""
        desc, pid = anomaly_description(
            0, 24, {"prod-a": 20, "prod-b": 4}
        )
        assert desc is not None
        assert "Velocity spike" in desc
        assert "prod-a" in desc
        assert "20 views" in desc
        assert pid == "prod-a"

    def test_velocity_spike_picks_highest_product(self):
        """When multiple products have views, the highest one is selected."""
        desc, pid = anomaly_description(
            0, 30, {"prod-x": 5, "prod-y": 22, "prod-z": 3}
        )
        assert pid == "prod-y"
        assert "22 views" in desc

    def test_velocity_spike_without_per_product_views(self):
        """Falls back to store-wide count when per-product data is missing."""
        desc, pid = anomaly_description(0, 24)
        assert desc is not None
        assert "Velocity spike" in desc
        assert "24 views" in desc
        assert pid is None

    def test_velocity_spike_with_empty_per_product_views(self):
        """Empty per-product dict falls back to store-wide count."""
        desc, pid = anomaly_description(0, 24, {})
        assert desc is not None
        assert "Velocity spike" in desc
        assert pid is None

    def test_velocity_threshold_is_threshold_times_4(self):
        """Velocity spike triggers at ANOMALY_THRESHOLD * 4 = 20 views."""
        # 19 views — below threshold
        desc, pid = anomaly_description(0, 19, {"p1": 19})
        assert desc is None
        assert pid is None

        # 20 views — at threshold
        desc, pid = anomaly_description(0, 20, {"p1": 20})
        assert desc is not None
        assert pid == "p1"

    def test_abandon_threshold_takes_priority(self):
        """When both thresholds are crossed, abandon surge wins."""
        desc, pid = anomaly_description(5, 24, {"p1": 20})
        assert "Cart abandon surge" in desc
        assert pid is None
