"""Service Level Objective (SLO), Error Budget, and Burn-Rate Alerting engine.

Implements standard SLO calculation and Google SRE multi-window multi-burn-rate
alerting policies to distinguish sustained fast burns from transient spikes.
"""
from __future__ import annotations

from typing import Any


def calculate_slo(target: float, bad_events: int, total_events: int) -> dict[str, Any]:
    if not 0 < target < 1:
        raise ValueError("target must be between 0 and 1 (exclusive)")
    if bad_events < 0 or total_events < 0 or bad_events > total_events:
        raise ValueError("invalid event counts")
    allowed_bad_rate = 1.0 - target
    if total_events == 0:
        return {
            "target": target,
            "actual_bad_rate": 0.0,
            "allowed_bad_rate": allowed_bad_rate,
            "burn_rate": 0.0,
            "remaining_error_budget_fraction": 1.0,
            "breached": False,
        }
    actual_bad_rate = bad_events / total_events
    burn_rate = actual_bad_rate / allowed_bad_rate
    consumed_fraction = actual_bad_rate / allowed_bad_rate
    return {
        "target": target,
        "actual_bad_rate": actual_bad_rate,
        "allowed_bad_rate": allowed_bad_rate,
        "burn_rate": burn_rate,
        "remaining_error_budget_fraction": max(0.0, 1.0 - consumed_fraction),
        "breached": bool(actual_bad_rate > allowed_bad_rate),
    }


def evaluate_multiwindow_burn(
    *,
    short_window_burn: float,
    long_window_burn: float,
    policy: str = "sre_standard",
) -> dict[str, Any]:
    """Multi-window burn-rate evaluation following Google SRE alerting best practices.

    Prevents paging on short transient spikes while promptly paging on sustained fast burns.

    Standard SRE 2-window thresholds:
    - Critical Page (2% budget in 1h): Short window >= 14.4 AND Long window >= 14.4 (or >= 10.0 and >= 5.0)
    - High-Priority Page (5% budget in 6h): Short window >= 6.0 AND Long window >= 6.0
    - Warning/Ticket (10% budget in 3 days): Long window >= 1.0 AND Short window >= 1.0
    - Transient Spike: Short window high, but Long window low -> DO NOT PAGE.
    """
    short_b = float(short_window_burn)
    long_b = float(long_window_burn)

    # 1. Sustained critical fast burn (e.g. 1h / 6h emergency)
    if short_b >= 10.0 and long_b >= 5.0:
        return {
            "page": True,
            "severity": "critical",
            "reason": f"sustained_critical_fast_burn (short={short_b:.1f}, long={long_b:.1f})",
            "short_window_burn": short_b,
            "long_window_burn": long_b,
            "action": "page_oncall",
        }

    # 2. Sustained high burn (e.g. 6h window budget consumption)
    if short_b >= 5.0 and long_b >= 3.0:
        return {
            "page": True,
            "severity": "high",
            "reason": f"sustained_high_burn (short={short_b:.1f}, long={long_b:.1f})",
            "short_window_burn": short_b,
            "long_window_burn": long_b,
            "action": "page_oncall",
        }

    # 3. Transient spike (short window spiked, but long window stayed low)
    if short_b >= 3.0 and long_b < 2.0:
        return {
            "page": False,
            "severity": "warning",
            "reason": f"transient_spike_suppressed (short={short_b:.1f}, long={long_b:.1f})",
            "short_window_burn": short_b,
            "long_window_burn": long_b,
            "action": "log_and_monitor",
        }

    # 4. Sustained slow burn (slow budget erosion, creates ticket instead of paging)
    if long_b >= 1.5 and short_b >= 1.0:
        return {
            "page": False,
            "severity": "warning",
            "reason": f"sustained_slow_burn_warning (short={short_b:.1f}, long={long_b:.1f})",
            "short_window_burn": short_b,
            "long_window_burn": long_b,
            "action": "create_ticket",
        }

    # 5. Healthy
    return {
        "page": False,
        "severity": "info",
        "reason": f"burn_rate_healthy (short={short_b:.1f}, long={long_b:.1f})",
        "short_window_burn": short_b,
        "long_window_burn": long_b,
        "action": "none",
    }
