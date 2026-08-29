#!/usr/bin/env python3
"""Automated Incident Triage & Evidence Bundle Generator.

Analyzes incoming datasets against contracts, historical metrics, anomaly detectors,
distribution shift models, SLOs, and lineage graphs to produce a comprehensive
7-question RCA evidence bundle for mystery incidents.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from observability.anomaly import detect_anomaly
from observability.distribution import detect_distribution_shift
from observability.lineage import get_column_downstream, get_downstream_assets
from observability.rag_metrics import detect_embedding_norm_shift, detect_text_length_shift
from observability.slo import calculate_slo, evaluate_multiwindow_burn
from src.contract_validator import determine_action, failed_issues, load_contract, validate_dataframe
from src.io_utils import load_jsonl


def run_triage() -> dict[str, Any]:
    orders_path = ROOT / "data" / "incoming" / "orders.csv"
    history_path = ROOT / "data" / "history" / "metrics_history.csv"
    kb_path = ROOT / "data" / "incoming" / "kb_documents.jsonl"
    lineage_path = ROOT / "data" / "baseline" / "lineage_graph.json"

    evidence: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signals_detected": [],
        "root_cause_hypotheses": [],
    }

    # 1. Inspect Orders Contract
    orders = pd.read_csv(orders_path) if orders_path.exists() else pd.DataFrame()
    orders_contract = load_contract(ROOT / "contracts" / "orders_contract.yaml")
    orders_issues = validate_dataframe(orders, orders_contract) if not orders.empty else []
    orders_failed = failed_issues(orders_issues)
    orders_critical = failed_issues(orders_issues, min_severity="critical")
    orders_action = determine_action(orders_issues)

    # 2. Inspect KB Contract
    kb_docs = load_jsonl(kb_path) if kb_path.exists() else []
    kb_df = pd.DataFrame(kb_docs) if kb_docs else pd.DataFrame()
    kb_contract = load_contract(ROOT / "contracts" / "kb_contract.yaml")
    kb_issues = validate_dataframe(kb_df, kb_contract) if not kb_df.empty else []
    kb_failed = failed_issues(kb_issues)
    kb_action = determine_action(kb_issues)

    # 3. Statistical Anomaly & History
    history = pd.read_csv(history_path) if history_path.exists() else pd.DataFrame()
    current_dow = datetime.now().weekday()
    seg_hist = (
        history.loc[history["day_of_week"] == current_dow, "row_count"].tail(8).tolist()
        if not history.empty and "day_of_week" in history.columns
        else []
    )
    row_anomaly = detect_anomaly(
        len(orders),
        history["row_count"].tail(14).tolist() if not history.empty else [],
        method="auto",
        context={"metric_name": "row_count", "day_of_week": current_dow, "same_segment_history": seg_hist},
    )

    # 4. Distribution Drift
    dist_anomaly = {"is_anomaly": False, "score": 0.0}
    if not orders.empty and not history.empty and "avg_amount" in history.columns and "amount" in orders.columns:
        dist_anomaly = detect_distribution_shift(
            orders["amount"].dropna(),
            history["avg_amount"].tail(14),
        )

    # 5. RAG Observability
    text_anomaly = {"is_anomaly": False, "score": 0.0}
    if kb_docs and not history.empty and "mean_text_length" in history.columns:
        text_anomaly = detect_text_length_shift(
            [d["content"] for d in kb_docs if "content" in d],
            history["mean_text_length"].tail(14),
        )

    # 6. SLO & Burn Rate
    bad_count = len(orders_critical) + len(failed_issues(kb_issues, min_severity="critical"))
    total_count = max(1, len(orders_issues) + len(kb_issues))
    slo_res = calculate_slo(0.999, bad_events=bad_count, total_events=total_count)
    burn_res = evaluate_multiwindow_burn(
        short_window_burn=slo_res["burn_rate"],
        long_window_burn=slo_res["burn_rate"] * 0.8,
    )

    # 7. Lineage & Blast Radius
    with open(lineage_path, "r", encoding="utf-8") as f:
        lineage_data = json.load(f)
    ds_lineage = lineage_data.get("dataset_lineage", lineage_data)
    col_lineage = lineage_data.get("column_lineage", {})

    blast_radius = []
    affected_root = "stg_orders"
    if orders_failed or row_anomaly["is_anomaly"]:
        blast_radius = get_downstream_assets(ds_lineage, "stg_orders")
        affected_root = "stg_orders"
    elif kb_failed or text_anomaly["is_anomaly"]:
        blast_radius = get_downstream_assets(ds_lineage, "kb_documents")
        affected_root = "kb_documents"

    # Synthesis of 7 RCA Answers
    what_happened = []
    if orders_critical:
        what_happened.append(f"Critical contract violation in orders ({len(orders_critical)} failures: {[i['check'] for i in orders_critical]})")
    if row_anomaly["is_anomaly"]:
        what_happened.append(f"Volume anomaly detected (ingested {len(orders)} rows, method={row_anomaly['method']}, score={row_anomaly['score']:.2f})")
    if kb_failed:
        what_happened.append(f"Knowledge base contract violation ({len(kb_failed)} failures, action={kb_action})")
    if text_anomaly["is_anomaly"]:
        what_happened.append(f"KB document text length collapse/drift detected (score={text_anomaly['score']:.2f})")
    if not what_happened:
        what_happened.append("All signals nominal. No active incident detected.")

    triage_report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "triage_summary": {
            "orders_rows": len(orders),
            "orders_action": orders_action,
            "orders_failed_checks": orders_failed,
            "kb_action": kb_action,
            "kb_failed_checks": kb_failed,
            "row_count_anomaly": row_anomaly,
            "distribution_drift": dist_anomaly,
            "rag_text_length_anomaly": text_anomaly,
            "slo_status": slo_res,
            "burn_rate_alert": burn_res,
            "blast_radius": blast_radius,
        },
        "rca_7_questions": {
            "1_what_happened": "; ".join(what_happened),
            "2_when_did_it_start": datetime.now(timezone.utc).isoformat(),
            "3_root_cause_evidence": {
                "contract_failures": [f"{i['column']}: {i['check']} ({i['details']})" for i in (orders_failed + kb_failed)],
                "anomaly_score": row_anomaly.get("score"),
                "burn_rate": slo_res.get("burn_rate"),
            },
            "4_blast_radius": f"{affected_root} -> " + " -> ".join(blast_radius),
            "5_mitigation": f"Trigger automated action: orders='{orders_action}', kb='{kb_action}'. Isolate corrupt batch.",
            "6_recovery_verification": "Run 'make baseline && make dbt && make tests' to confirm clean status.",
            "7_prevention": "Enforce strict pre-ingestion contracts and multi-window burn rate alerts in CI/CD.",
        },
    }

    out_file = ROOT / "reports" / "mystery_incident_evidence.json"
    out_file.write_text(json.dumps(triage_report, indent=2, default=str), encoding="utf-8")

    print("\n==================================================")
    print("🚨 MYSTERY INCIDENT TRIAGE & EVIDENCE BUNDLE")
    print("==================================================")
    print(f"1. What happened?        : {triage_report['rca_7_questions']['1_what_happened']}")
    print(f"2. Detection Time        : {triage_report['rca_7_questions']['2_when_did_it_start']}")
    print(f"3. Action / Severity     : Orders={orders_action.upper()}, KB={kb_action.upper()}, Paging={burn_res['page']}")
    print(f"4. Blast Radius          : {triage_report['rca_7_questions']['4_blast_radius']}")
    print(f"5. Mitigation            : {triage_report['rca_7_questions']['5_mitigation']}")
    print(f"6. Evidence Bundle File  : reports/mystery_incident_evidence.json")
    print("==================================================\n")

    return triage_report


if __name__ == "__main__":
    run_triage()
