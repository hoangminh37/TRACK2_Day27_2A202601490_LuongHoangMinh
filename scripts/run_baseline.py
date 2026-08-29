#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from observability.anomaly import detect_anomaly
from observability.lineage import get_column_downstream, get_downstream_assets
from observability.rag_metrics import detect_embedding_norm_shift, detect_text_length_shift
from observability.slo import calculate_slo, evaluate_multiwindow_burn
from src.contract_validator import determine_action, failed_issues, load_contract, validate_dataframe
from src.io_utils import load_jsonl


def main() -> None:
    orders_path = ROOT / "data" / "incoming" / "orders.csv"
    history_path = ROOT / "data" / "history" / "metrics_history.csv"
    kb_path = ROOT / "data" / "incoming" / "kb_documents.jsonl"
    
    orders = pd.read_csv(orders_path)
    history = pd.read_csv(history_path)
    
    # 1. Orders contract validation
    contract = load_contract(ROOT / "contracts" / "orders_contract.yaml")
    issues = validate_dataframe(orders, contract)
    failed = failed_issues(issues)
    critical_failed = failed_issues(issues, min_severity="critical")
    action = determine_action(issues)

    # 2. KB contract validation
    kb_docs = load_jsonl(kb_path)
    kb_df = pd.DataFrame(kb_docs)
    kb_contract = load_contract(ROOT / "contracts" / "kb_contract.yaml")
    kb_issues = validate_dataframe(kb_df, kb_contract)
    kb_failed = failed_issues(kb_issues)
    kb_critical_failed = failed_issues(kb_issues, min_severity="critical")
    kb_action = determine_action(kb_issues)

    # 3. Context-aware Anomaly Detection
    current_dow = datetime.now().weekday()
    segment = history.loc[history["day_of_week"] == current_dow, "row_count"].tail(8).tolist()
    row_result = detect_anomaly(
        len(orders),
        history["row_count"].tail(14).tolist(),
        method="auto",
        context={
            "metric_name": "row_count",
            "day_of_week": current_dow,
            "same_segment_history": segment,
        },
    )

    # 4. Freshness
    updated = pd.to_datetime(orders["updated_at"], utc=True, errors="coerce")
    orders_freshness_minutes = (
        pd.Timestamp(datetime.now(timezone.utc)) - updated.max()
    ).total_seconds() / 60.0

    kb_pub = pd.to_datetime(kb_df["published_at"], utc=True, errors="coerce")
    kb_freshness_minutes = (
        pd.Timestamp(datetime.now(timezone.utc)) - kb_pub.max()
    ).total_seconds() / 60.0

    # 5. RAG Observability
    text_result = detect_text_length_shift(
        [d["content"] for d in kb_docs], history["mean_text_length"].tail(14).tolist()
    )
    # Synthetic embedding norms for monitoring
    mock_current_norms = [float(len(d["content"].split())) * 0.1 for d in kb_docs]
    mock_base_norms = [float(l) * 0.1 for l in history["mean_text_length"].tail(14).tolist()]
    emb_result = detect_embedding_norm_shift(mock_current_norms, mock_base_norms)

    # 6. SLO & Error Budget
    bad_checks = len(critical_failed) + len(kb_critical_failed)
    total_checks = len(issues) + len(kb_issues)
    contract_slo = calculate_slo(0.999, bad_events=bad_checks, total_events=total_checks)
    burn_eval = evaluate_multiwindow_burn(
        short_window_burn=contract_slo["burn_rate"],
        long_window_burn=contract_slo["burn_rate"] * 0.8,
    )

    # 7. Lineage & Blast Radius
    with open(ROOT / "data" / "baseline" / "lineage_graph.json", "r", encoding="utf-8") as f:
        lineage_data = json.load(f)
    dataset_lineage = lineage_data.get("dataset_lineage", lineage_data)
    column_lineage = lineage_data.get("column_lineage", {})

    blast_radius = get_downstream_assets(dataset_lineage, "stg_orders")
    col_blast_radius = get_column_downstream(column_lineage, "raw_orders.amount")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "orders_rows": int(len(orders)),
        "orders_failed_checks": len(failed),
        "orders_critical_fails": len(critical_failed),
        "orders_action": action,
        "failed_contract_checks": len(failed),
        "critical_contract_failures": len(critical_failed),
        "kb_docs_count": len(kb_docs),
        "kb_failed_checks": len(kb_failed),
        "kb_critical_fails": len(kb_critical_failed),
        "kb_action": kb_action,
        "row_count_anomaly": row_result,
        "freshness_minutes": orders_freshness_minutes,
        "kb_freshness_minutes": kb_freshness_minutes,
        "kb_text_length_signal": text_result,
        "kb_embedding_signal": emb_result,
        "contract_slo": contract_slo,
        "burn_rate_alert": burn_eval,
        "sample_blast_radius_from_stg_orders": blast_radius,
        "sample_column_blast_radius": col_blast_radius,
        "all_issues": issues + kb_issues,
    }
    out = ROOT / "reports" / "latest_metrics.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("=== DATA RELIABILITY BASELINE ===")
    print(f"orders rows              : {len(orders)}")
    print(f"contract failed checks   : {len(failed)} (Action: {action})")
    print(f"critical contract fails  : {len(critical_failed)}")
    print(f"KB failed checks         : {len(kb_failed)} (Action: {kb_action})")
    print(f"row-count anomaly        : {row_result['is_anomaly']} ({row_result['method']}, score={row_result['score']:.2f})")
    print(f"orders freshness (min)   : {orders_freshness_minutes:.1f}")
    print(f"KB freshness (min)       : {kb_freshness_minutes:.1f}")
    print(f"KB length anomaly        : {text_result['is_anomaly']}")
    print(f"SLO Burn Rate            : {contract_slo['burn_rate']:.2f} (Page: {burn_eval['page']}, Severity: {burn_eval['severity']})")
    print(f"sample blast radius      : {', '.join(blast_radius)}")
    print(f"report                    : {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
