from travel_data_platform.services.alert_rule_evaluator import AlertRuleEvaluator


def test_evaluate_below_target():
    evaluator = AlertRuleEvaluator()

    candidates = evaluator.evaluate(
        current_price=5900000,
        currency="VND",
        target_price=6000000,
        min_price_7d=None,
    )

    assert len(candidates) == 1
    assert candidates[0].alert_type == "BELOW_TARGET"
    assert candidates[0].current_price == 5900000
    assert candidates[0].target_price == 6000000


def test_evaluate_new_low_7d():
    evaluator = AlertRuleEvaluator()

    candidates = evaluator.evaluate(
        current_price=5800000,
        currency="VND",
        target_price=None,
        min_price_7d=5800000,
    )

    assert len(candidates) == 1
    assert candidates[0].alert_type == "NEW_LOW_7D"
    assert candidates[0].baseline_price == 5800000


def test_evaluate_both_rules():
    evaluator = AlertRuleEvaluator()

    candidates = evaluator.evaluate(
        current_price=5700000,
        currency="VND",
        target_price=6000000,
        min_price_7d=5700000,
    )

    assert len(candidates) == 2
    assert {candidate.alert_type for candidate in candidates} == {
        "BELOW_TARGET",
        "NEW_LOW_7D",
    }


def test_evaluate_no_alert():
    evaluator = AlertRuleEvaluator()

    candidates = evaluator.evaluate(
        current_price=6500000,
        currency="VND",
        target_price=6000000,
        min_price_7d=5800000,
    )

    assert candidates == []
