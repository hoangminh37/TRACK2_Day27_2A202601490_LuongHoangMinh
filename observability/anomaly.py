"""Robust anomaly detection engine for data observability.

Provides standard Z-score, Median Absolute Deviation (MAD), Exponentially Weighted Moving Average (EWMA),
and a context-aware 'auto' detector supporting seasonality, segment history, and robust statistics.
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def zscore_detector(current: float, history: Iterable[float], threshold: float = 3.0) -> dict[str, Any]:
    values = np.asarray(list(history), dtype=float)
    if values.size < 3:
        return {"is_anomaly": False, "score": 0.0, "method": "zscore", "reason": "insufficient_history"}
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std == 0:
        score = float("inf") if float(current) != mean else 0.0
    else:
        score = abs(float(current) - mean) / std
    return {
        "is_anomaly": bool(score > threshold),
        "score": float(score),
        "method": "zscore",
        "reason": f"mean={mean:.3f}, std={std:.3f}, threshold={threshold}",
    }


def mad_detector(current: float, history: Iterable[float], threshold: float = 3.5) -> dict[str, Any]:
    """Robust Modified Z-score using Median Absolute Deviation (MAD).

    Handles zero-MAD cases by falling back to mean absolute deviation or sample std.
    """
    values = np.asarray(list(history), dtype=float)
    if values.size < 3:
        return {"is_anomaly": False, "score": 0.0, "method": "mad", "reason": "insufficient_history"}
    median = float(np.median(values))
    abs_diff = np.abs(values - median)
    mad = float(np.median(abs_diff))

    if mad > 0:
        modified_z = 0.6745 * abs(float(current) - median) / mad
    else:
        # Fallback to mean absolute deviation or std for zero-MAD
        mean_ad = float(np.mean(abs_diff))
        if mean_ad > 0:
            modified_z = 0.7979 * abs(float(current) - median) / mean_ad
        else:
            std = float(np.std(values))
            if std > 0:
                modified_z = abs(float(current) - median) / std
            else:
                modified_z = 0.0 if float(current) == median else float("inf")

    return {
        "is_anomaly": bool(modified_z > threshold),
        "score": float(modified_z),
        "method": "mad",
        "reason": f"median={median:.3f}, mad={mad:.3f}, threshold={threshold}",
    }


def ewma_detector(
    current: float,
    history: Iterable[float],
    alpha: float = 0.3,
    threshold: float = 3.0,
) -> dict[str, Any]:
    """Exponentially Weighted Moving Average (EWMA) detector for tracking recency and drift."""
    values = np.asarray(list(history), dtype=float)
    if values.size < 3:
        return {"is_anomaly": False, "score": 0.0, "method": "ewma", "reason": "insufficient_history"}

    # Compute EWMA mean
    ewma_mean = values[0]
    for v in values[1:]:
        ewma_mean = alpha * v + (1 - alpha) * ewma_mean

    # Compute EWMA variance
    diffs = (values - ewma_mean) ** 2
    ewma_var = diffs[0]
    for d in diffs[1:]:
        ewma_var = alpha * d + (1 - alpha) * ewma_var
    ewma_std = float(np.sqrt(ewma_var))

    if ewma_std == 0:
        score = float("inf") if float(current) != ewma_mean else 0.0
    else:
        score = abs(float(current) - ewma_mean) / ewma_std

    return {
        "is_anomaly": bool(score > threshold),
        "score": float(score),
        "method": "ewma",
        "reason": f"ewma_mean={ewma_mean:.3f}, ewma_std={ewma_std:.3f}, threshold={threshold}",
    }


def detect_anomaly(
    current: float,
    history: Iterable[float],
    *,
    method: str = "auto",
    threshold: float = 3.0,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Context-aware anomaly detection interface.

    Supports:
    - 'zscore': basic Z-score detector.
    - 'mad': robust Median Absolute Deviation detector.
    - 'ewma': exponentially weighted moving average detector.
    - 'auto': context-aware hybrid detector incorporating seasonality, same_segment_history,
              and robust MAD/Z-score combination.
    """
    if method == "zscore":
        return zscore_detector(current, history, threshold=threshold)
    if method == "mad":
        return mad_detector(current, history, threshold=threshold if threshold != 3.0 else 3.5)
    if method == "ewma":
        return ewma_detector(current, history, threshold=threshold)

    if method == "auto":
        # Check context for segment or seasonality history
        effective_history = list(history)
        context_notes = []

        if context and isinstance(context, dict):
            if "same_segment_history" in context and context["same_segment_history"]:
                seg_hist = list(context["same_segment_history"])
                if len(seg_hist) >= 3:
                    effective_history = seg_hist
                    context_notes.append("used_same_segment_history")

            if context.get("known_event"):
                context_notes.append(f"event={context['known_event']}")

        if len(effective_history) >= 5:
            # Robust MAD with z-score cross check
            mad_thresh = 3.5 if threshold == 3.0 else threshold
            mad_res = mad_detector(current, effective_history, threshold=mad_thresh)
            z_res = zscore_detector(current, effective_history, threshold=threshold)

            # Flag anomaly if robust MAD flags or Z-score flags with high confidence
            is_anom = mad_res["is_anomaly"] or z_res["is_anomaly"]
            score = mad_res["score"] if np.isfinite(mad_res["score"]) else z_res["score"]
            method_desc = "auto:robust_mad"
            reason = f"mad_score={mad_res['score']:.2f}, z_score={z_res['score']:.2f}"
            if context_notes:
                reason += f" ({', '.join(context_notes)})"

            return {
                "is_anomaly": bool(is_anom),
                "score": float(score),
                "method": method_desc,
                "reason": reason,
            }
        else:
            # Fallback to standard zscore on available history
            res = zscore_detector(current, effective_history, threshold=threshold)
            res["method"] = "auto:zscore"
            if context_notes:
                res["reason"] += f" ({', '.join(context_notes)})"
            return res

    raise ValueError(f"Unsupported method: {method}")
