"""RAG and Knowledge Base observability signals.

Detects text length collapse/drift and embedding norm/similarity shifts in vector spaces.
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np

from observability.anomaly import mad_detector, zscore_detector


def approximate_token_lengths(texts: Iterable[str]) -> list[int]:
    """Token length approximation by whitespace splitting."""
    return [len(str(t).split()) for t in texts if t is not None]


def detect_text_length_shift(
    current_texts: Iterable[str],
    baseline_batch_means: Iterable[float],
    *,
    threshold: float = 3.0,
) -> dict[str, Any]:
    """Detect significant changes in document text lengths (collapse or ballooning)."""
    lengths = approximate_token_lengths(current_texts)
    current_mean = float(np.mean(lengths)) if lengths else 0.0
    result = zscore_detector(current_mean, baseline_batch_means, threshold=threshold)
    result["metric"] = "mean_text_length"
    result["current_mean"] = current_mean
    return result


def detect_embedding_norm_shift(
    current_norms: Iterable[float],
    baseline_norms: Iterable[float],
    *,
    threshold: float = 3.0,
) -> dict[str, Any]:
    """Detect embedding-space drift or norm distortion across batches."""
    cur = np.asarray(list(current_norms), dtype=float)
    base = np.asarray(list(baseline_norms), dtype=float)

    cur = cur[np.isfinite(cur)]
    base = base[np.isfinite(base)]

    if cur.size == 0 or base.size == 0:
        return {
            "is_anomaly": False,
            "score": 0.0,
            "method": "embedding_norm_zscore",
            "reason": "empty_input",
        }

    cur_mean = float(np.mean(cur))
    base_mean = float(np.mean(base))

    # Evaluate using both z-score on batch means and robust MAD
    if base.size >= 5:
        res = mad_detector(cur_mean, base, threshold=threshold)
        res["method"] = "embedding_norm_mad"
    else:
        res = zscore_detector(cur_mean, base, threshold=threshold)
        res["method"] = "embedding_norm_zscore"

    res["metric"] = "embedding_norm"
    res["current_mean"] = cur_mean
    res["baseline_mean"] = base_mean
    return res
