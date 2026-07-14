from app.services.interceptor import enforce_uplift
from app.models.schemas import BusinessConstraints


DEFAULT = BusinessConstraints(max_uplift_percent=10.0)


def test_within_ceiling_passes_clean():
    final_price, violations = enforce_uplift(20.0, 21.0, DEFAULT)
    assert final_price == 21.0
    assert violations == []


def test_exceeds_ceiling_gets_clamped_with_warning():
    final_price, violations = enforce_uplift(20.0, 25.0, DEFAULT)
    assert final_price == 22.0  # 20 * 1.10
    assert len(violations) == 1
    assert violations[0].severity == "warning"
    assert violations[0].rule == "max_uplift"
    assert "10" in violations[0].message


def test_zero_uplift_ceiling_blocks_any_increase_to_baseline():
    constraints = BusinessConstraints(max_uplift_percent=0.0)
    final_price, violations = enforce_uplift(20.0, 22.0, constraints)
    assert final_price == 20.0
    assert violations[0].clamped_value == 20.0


def test_exactly_at_ceiling_passes_clean():
    final_price, violations = enforce_uplift(20.0, 22.0, DEFAULT)
    assert final_price == 22.0
    assert violations == []
