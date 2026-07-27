from domain.speed import evaluate_speed_policy, normalize_speed_limit, resolve_limits, speed_status


def test_normalize_speed_limit_list():
    assert normalize_speed_limit([0, 60]) == {"min": 0.0, "max": 60.0}
    assert normalize_speed_limit(80) == {"min": None, "max": 80.0}
    assert normalize_speed_limit({"0": 10, "1": 90}) == {"min": 10.0, "max": 90.0}


def test_evaluate_overspeed_policy():
    viols = evaluate_speed_policy(
        95,
        min_speed=0,
        max_speed=80,
        alert_overspeed=True,
        alert_underspeed=False,
    )
    assert len(viols) == 1
    assert viols[0]["violation_type"] == "overspeed"
    assert viols[0]["detail"]["speed"] == 95
    assert viols[0]["detail"]["limit_max"] == 80
    assert viols[0]["detail"]["over_speeding_pct"] == 18.8


def test_evaluate_skips_existing():
    viols = evaluate_speed_policy(
        100,
        max_speed=60,
        existing_types={"overspeed"},
    )
    assert viols == []


def test_evaluate_underspeed():
    viols = evaluate_speed_policy(
        20,
        min_speed=40,
        max_speed=80,
        alert_overspeed=True,
        alert_underspeed=True,
    )
    assert len(viols) == 1
    assert viols[0]["violation_type"] == "underspeed"


def test_resolve_limits_prefers_event():
    mn, mx = resolve_limits(event_limit=[5, 70], policy_min=0, policy_max=80)
    assert mn == 5.0 and mx == 70.0
    mn, mx = resolve_limits(event_limit=None, policy_min=0, policy_max=80)
    assert mn == 0.0 and mx == 80.0


def test_speed_status():
    assert speed_status(90, max_speed=80) == "overspeed"
    assert speed_status(30, min_speed=40, max_speed=80) == "underspeed"
    assert speed_status(50, min_speed=0, max_speed=80) == "ok"
    assert speed_status(None) == "unknown"
