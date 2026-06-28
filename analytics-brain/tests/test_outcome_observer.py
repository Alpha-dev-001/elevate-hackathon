from app.services.outcome_observer import summarize_outcome


def test_summary_with_conversions():
    assert summarize_outcome(8, 320.0) == "8 orders, $320 revenue"


def test_summary_no_conversions():
    assert summarize_outcome(0, 0.0) == "no conversions"


def test_summary_rounds_revenue():
    assert summarize_outcome(3, 99.6) == "3 orders, $100 revenue"
