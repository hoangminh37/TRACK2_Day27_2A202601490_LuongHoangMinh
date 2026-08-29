"""Distribution shift and data drift detection module.

Implements Kolmogorov-Smirnov (KS) test, Population Stability Index (PSI),
and robust statistical ratios to detect distribution drift across pipeline runs.
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np
from scipy import stats


def calculate_psi(baseline: np.ndarray, current: np.ndarray, num_buckets: int = 10) -> float:
    """Calculate Population Stability Index (PSI) between baseline and current distributions."""
    if baseline.size == 0 or current.size == 0:
        return 0.0

    # Determine bin edges based on combined quantiles
    combined = np.concatenate([baseline, current])
    quantiles = np.linspace(0, 100, num_buckets + 1)
    bin_edges = np.percentile(combined, quantiles)
    bin_edges = np.unique(bin_edges)
    if len(bin_edges) < 2:
        return 0.0

    # Add epsilon bounds
    bin_edges[0] -= 1e-5
    bin_edges[-1] += 1e-5

    base_counts, _ = np.histogram(baseline, bins=bin_edges)
    cur_counts, _ = np.histogram(current, bins=bin_edges)

    # Convert to fractions with Laplace smoothing
    eps = 1e-4
    base_pct = (base_counts + eps) / (baseline.size + eps * len(base_counts))
    cur_pct = (cur_counts + eps) / (current.size + eps * len(cur_counts))

    psi = float(np.sum((cur_pct - base_pct) * np.log(cur_pct / base_pct)))
    return max(0.0, psi)


def detect_distribution_shift(
    current_values: Iterable[float],
    baseline_values: Iterable[float],
    *,
    ratio_threshold: float = 3.0,
    ks_alpha: float = 0.01,
) -> dict[str, Any]:
    """Detect distribution shift using a hybrid of Kolmogorov-Smirnov test and robust moments."""
    cur = np.asarray(list(current_values), dtype=float)
    base = np.asarray(list(baseline_values), dtype=float)

    # Filter out NaNs/Infs
    cur = cur[np.isfinite(cur)]
    base = base[np.isfinite(base)]

    if cur.size == 0 or base.size == 0:
        return {"is_anomaly": False, "score": 0.0, "method": "ks_and_ratio", "reason": "empty_input"}

    cur_mean = float(np.mean(cur))
    base_mean = float(np.mean(base))

    # Mean ratio
    if base_mean == 0:
        ratio = float("inf") if cur_mean != 0 else 1.0
    else:
        ratio = max(abs(cur_mean / base_mean), abs(base_mean / cur_mean)) if cur_mean != 0 else float("inf")

    # KS 2-sample test
    ks_stat = 0.0
    p_value = 1.0
    if cur.size >= 3 and base.size >= 3:
        ks_res = stats.ks_2samp(cur, base)
        ks_stat = float(ks_res.statistic)
        p_value = float(ks_res.pvalue)

    # PSI calculation
    psi_val = calculate_psi(base, cur)

    # Anomaly conditions:
    # 1. Significant mean ratio change
    # 2. Strong KS shift with significant p-value (p < alpha and statistic > 0.4)
    # 3. PSI > 0.25 (significant distribution drift)
    is_anomaly = bool(
        (np.isfinite(ratio) and ratio >= ratio_threshold)
        or (not np.isfinite(ratio) and (cur_mean != base_mean))
        or (p_value < ks_alpha and ks_stat >= 0.4)
        or (psi_val > 0.25 and cur.size >= 5 and base.size >= 5)
    )

    score = float(ratio if np.isfinite(ratio) else (ks_stat * 10.0))

    return {
        "is_anomaly": is_anomaly,
        "score": score,
        "method": "ks_and_ratio",
        "reason": (
            f"baseline_mean={base_mean:.3f}, current_mean={cur_mean:.3f}, "
            f"ratio={ratio:.2f}, ks_stat={ks_stat:.3f}, p_val={p_value:.4f}, psi={psi_val:.3f}"
        ),
    }
