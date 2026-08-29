from student_api import detect_metric


def test_large_volume_drop_is_anomaly():
    history = [1000, 1010, 995, 1008, 1004, 1012, 998]
    result = detect_metric(300, history, method="zscore")
    assert result["is_anomaly"] is True


def test_stable_value_is_not_anomaly():
    history = [1000, 1010, 995, 1008, 1004, 1012, 998]
    result = detect_metric(1002, history, method="zscore")
    assert result["is_anomaly"] is False


def test_mad_zero_handling():
    history = [100, 100, 100, 100, 100]
    result = detect_metric(300, history, method="mad")
    assert result["is_anomaly"] is True


def test_auto_context_seasonality():
    # Saturday history ~ 250, overall history ~ 600
    overall_history = [600, 610, 595, 608, 604, 612, 598]
    saturday_history = [250, 245, 255, 248, 252]
    # Current value is 250 on a Saturday (normal for Saturday, but would be drop if compared to 600)
    res = detect_metric(
        250,
        overall_history,
        method="auto",
        context={"day_of_week": 5, "same_segment_history": saturday_history},
    )
    assert res["is_anomaly"] is False

