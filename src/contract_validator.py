"""Comprehensive contract validator for dataset quality, type safety, and freshness.

Supports deterministic checks, type drift detection, freshness verification,
and severity-aware operational actions (block, quarantine, warn).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


def _issue(
    check: str,
    *,
    column: str | None,
    severity: str,
    passed: bool,
    details: str,
) -> dict[str, Any]:
    return {
        "check": check,
        "column": column,
        "severity": severity,
        "passed": bool(passed),
        "details": details,
    }


def load_contract(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _check_integer_type(series: pd.Series) -> tuple[bool, int]:
    valid_series = series.dropna()
    if valid_series.empty:
        return True, 0
    invalid_count = 0
    for val in valid_series:
        if isinstance(val, (int, np.integer)):
            continue
        if isinstance(val, (float, np.floating)):
            if float(val).is_integer():
                continue
            invalid_count += 1
            continue
        # String or other
        try:
            val_str = str(val).strip()
            # Try float first to detect 12.34 formatted string
            f = float(val_str)
            if not f.is_integer():
                invalid_count += 1
        except (ValueError, TypeError):
            invalid_count += 1
    return invalid_count == 0, invalid_count


def _check_number_type(series: pd.Series) -> tuple[bool, int]:
    valid_series = series.dropna()
    if valid_series.empty:
        return True, 0
    coerced = pd.to_numeric(valid_series, errors="coerce")
    invalid_count = int(coerced.isna().sum())
    return invalid_count == 0, invalid_count


def _check_datetime_type(series: pd.Series) -> tuple[bool, int]:
    valid_series = series.dropna()
    if valid_series.empty:
        return True, 0
    coerced = pd.to_datetime(valid_series, errors="coerce", utc=True)
    invalid_count = int(coerced.isna().sum())
    return invalid_count == 0, invalid_count


def _check_boolean_type(series: pd.Series) -> tuple[bool, int]:
    valid_series = series.dropna()
    if valid_series.empty:
        return True, 0
    allowed = {True, False, 1, 0, "1", "0", "true", "false", "True", "False", "TRUE", "FALSE"}
    invalid_count = int((~valid_series.isin(allowed)).sum())
    return invalid_count == 0, invalid_count


def validate_dataframe(
    df: pd.DataFrame,
    contract: dict[str, Any],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    # Support both 'columns' (orders) and 'fields' (kb_documents) in contract YAML
    columns = contract.get("columns") or contract.get("fields") or {}

    for column, rules in columns.items():
        severity = rules.get("severity", "critical" if rules.get("required") else "warning")
        required = bool(rules.get("required", False))

        if column not in df.columns:
            if required:
                issues.append(
                    _issue(
                        "required_column",
                        column=column,
                        severity=severity,
                        passed=False,
                        details=f"Missing required column: {column}",
                    )
                )
            continue

        series = df[column]

        # 1. Not-null check
        if required:
            null_count = int(series.isna().sum())
            issues.append(
                _issue(
                    "not_null",
                    column=column,
                    severity=severity,
                    passed=(null_count == 0),
                    details=f"null_count={null_count}",
                )
            )

        # 2. Unique check
        if rules.get("unique"):
            duplicate_count = int(series.duplicated(keep=False).sum())
            issues.append(
                _issue(
                    "unique",
                    column=column,
                    severity=severity,
                    passed=(duplicate_count == 0),
                    details=f"duplicate_rows={duplicate_count}",
                )
            )

        # 3. Accepted values check
        accepted = rules.get("accepted_values")
        if accepted is not None:
            invalid_mask = series.notna() & ~series.isin(accepted)
            invalid_count = int(invalid_mask.sum())
            issues.append(
                _issue(
                    "accepted_values",
                    column=column,
                    severity=severity,
                    passed=(invalid_count == 0),
                    details=f"invalid_count={invalid_count}; accepted={accepted}",
                )
            )

        # 4. Strict Type validation
        declared_type = str(rules.get("type", "")).lower()
        if declared_type in {"integer", "int"}:
            is_valid, invalid_count = _check_integer_type(series)
            issues.append(
                _issue(
                    "type",
                    column=column,
                    severity=severity,
                    passed=is_valid,
                    details=f"expected=integer; invalid_count={invalid_count}",
                )
            )
        elif declared_type in {"number", "float", "numeric", "double"}:
            is_valid, invalid_count = _check_number_type(series)
            issues.append(
                _issue(
                    "type",
                    column=column,
                    severity=severity,
                    passed=is_valid,
                    details=f"expected=number; invalid_count={invalid_count}",
                )
            )
        elif declared_type in {"datetime", "timestamp"}:
            is_valid, invalid_count = _check_datetime_type(series)
            issues.append(
                _issue(
                    "type",
                    column=column,
                    severity=severity,
                    passed=is_valid,
                    details=f"expected=datetime; invalid_count={invalid_count}",
                )
            )
        elif declared_type in {"boolean", "bool"}:
            is_valid, invalid_count = _check_boolean_type(series)
            issues.append(
                _issue(
                    "type",
                    column=column,
                    severity=severity,
                    passed=is_valid,
                    details=f"expected=boolean; invalid_count={invalid_count}",
                )
            )

        # 5. Numeric Range check
        if "min" in rules or "max" in rules:
            numeric = pd.to_numeric(series, errors="coerce")
            invalid = pd.Series(False, index=series.index)
            if "min" in rules:
                invalid |= numeric < rules["min"]
            if "max" in rules:
                invalid |= numeric > rules["max"]
            invalid_count = int(invalid.fillna(False).sum())
            issues.append(
                _issue(
                    "range",
                    column=column,
                    severity=severity,
                    passed=(invalid_count == 0),
                    details=f"invalid_count={invalid_count}",
                )
            )

        # 6. String length checks (e.g. min_length, max_length)
        if "min_length" in rules:
            min_len = int(rules["min_length"])
            str_series = series.dropna().astype(str)
            short_count = int((str_series.str.len() < min_len).sum())
            issues.append(
                _issue(
                    "min_length",
                    column=column,
                    severity=severity,
                    passed=(short_count == 0),
                    details=f"expected_min_length={min_len}; short_count={short_count}",
                )
            )
        if "max_length" in rules:
            max_len = int(rules["max_length"])
            str_series = series.dropna().astype(str)
            long_count = int((str_series.str.len() > max_len).sum())
            issues.append(
                _issue(
                    "max_length",
                    column=column,
                    severity=severity,
                    passed=(long_count == 0),
                    details=f"expected_max_length={max_len}; long_count={long_count}",
                )
            )

    # 7. Freshness check at contract level
    freshness = contract.get("freshness")
    if freshness and isinstance(freshness, dict):
        fresh_col = freshness.get("column")
        max_delay = float(freshness.get("max_delay_minutes", 60))
        fresh_severity = freshness.get("severity", "warning")

        if not fresh_col or fresh_col not in df.columns:
            issues.append(
                _issue(
                    "freshness",
                    column=fresh_col,
                    severity=fresh_severity,
                    passed=False,
                    details=f"Freshness column '{fresh_col}' not found in dataframe",
                )
            )
        else:
            ts_series = pd.to_datetime(df[fresh_col], utc=True, errors="coerce")
            if ts_series.notna().any():
                latest_ts = ts_series.max()
                if now is None:
                    current_time = pd.Timestamp.now(tz="UTC")
                elif isinstance(now, pd.Timestamp):
                    current_time = now.tz_convert("UTC") if now.tz is not None else now.tz_localize("UTC")
                elif isinstance(now, datetime):
                    current_time = pd.Timestamp(now).tz_convert("UTC") if now.tzinfo is not None else pd.Timestamp(now, tz="UTC")
                else:
                    current_time = pd.to_datetime(now, utc=True)
                delay_minutes = max(0.0, (current_time - latest_ts).total_seconds() / 60.0)
                passed = delay_minutes <= max_delay
                issues.append(
                    _issue(
                        "freshness",
                        column=fresh_col,
                        severity=fresh_severity,
                        passed=passed,
                        details=f"delay_minutes={delay_minutes:.1f}; max_delay_minutes={max_delay}",
                    )
                )
            else:
                issues.append(
                    _issue(
                        "freshness",
                        column=fresh_col,
                        severity=fresh_severity,
                        passed=False,
                        details=f"All values in freshness column '{fresh_col}' are null or invalid timestamps",
                    )
                )

    return issues


def failed_issues(issues: list[dict[str, Any]], min_severity: str | None = None) -> list[dict[str, Any]]:
    failed = [i for i in issues if not i.get("passed", False)]
    if min_severity is None:
        return failed
    order = {"info": 0, "warning": 1, "critical": 2}
    threshold = order.get(min_severity, 1)
    return [i for i in failed if order.get(i.get("severity", "warning"), 1) >= threshold]


def determine_action(issues: list[dict[str, Any]]) -> str:
    """Determine operational pipeline action based on issue severity:
    - 'block': at least one critical check failed
    - 'quarantine': warning checks failed (can isolate bad rows or alert)
    - 'warn': only info checks failed
    - 'pass': all checks passed
    """
    failed = [i for i in issues if not i.get("passed", False)]
    if not failed:
        return "pass"
    if any(i.get("severity") == "critical" for i in failed):
        return "block"
    if any(i.get("severity") == "warning" for i in failed):
        return "quarantine"
    return "warn"
