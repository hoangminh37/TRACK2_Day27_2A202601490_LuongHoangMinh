import pytest
from student_api import slo_status


def test_burn_rate_math():
    result = slo_status(0.995, bad_events=2, total_events=100)
    assert result["allowed_bad_rate"] == pytest.approx(0.005)
    assert result["actual_bad_rate"] == pytest.approx(0.02)
    assert result["burn_rate"] == pytest.approx(4.0)
    assert result["breached"] is True


def test_zero_events_is_safe():
    result = slo_status(0.99, bad_events=0, total_events=0)
    assert result["burn_rate"] == 0
    assert result["breached"] is False


def test_multiwindow_sustained_fast_burn_pages():
    from student_api import multiwindow_burn
    res = multiwindow_burn(short_window_burn=14.4, long_window_burn=14.4)
    assert res["page"] is True
    assert res["severity"] == "critical"


def test_multiwindow_transient_spike_does_not_page():
    from student_api import multiwindow_burn
    res = multiwindow_burn(short_window_burn=14.4, long_window_burn=0.5)
    assert res["page"] is False

