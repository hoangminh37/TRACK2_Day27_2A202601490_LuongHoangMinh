from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "latest_metrics.json"
HISTORY = ROOT / "data" / "history" / "metrics_history.csv"
LINEAGE_FILE = ROOT / "data" / "baseline" / "lineage_graph.json"

st.set_page_config(
    page_title="Data Reliability Control Center",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for styling
st.markdown("""
<style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 16px;
        border-left: 5px solid #0d6efd;
    }
    .badge-critical {
        background-color: #dc3545;
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
    .badge-warning {
        background-color: #ffc107;
        color: black;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
    .badge-pass {
        background-color: #198754;
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

st.title("🛡️ Data Reliability & Observability Control Center")
st.caption("Real-time Data Observability, Multi-Window SLOs, Contract Enforcement & Blast Radius Triage")

if not REPORT.exists():
    st.warning("⚠️ Baseline report not found. Run `make baseline` in terminal to generate metrics.")
    st.stop()

report = json.loads(REPORT.read_text(encoding="utf-8"))
history = pd.read_csv(HISTORY) if HISTORY.exists() else pd.DataFrame()

# Top-level Health Banner
orders_action = report.get("orders_action", "pass")
kb_action = report.get("kb_action", "pass")
is_incident = (orders_action == "block") or report.get("critical_contract_failures", 0) > 0

if is_incident:
    st.error("🚨 **CRITICAL INCIDENT ACTIVE**: Contract failure detected. Downstream pipelines blocked to prevent corrupt data propagation.")
elif orders_action == "quarantine" or kb_action == "quarantine":
    st.warning("⚠️ **DEGRADED HEALTH**: Non-critical contract issues or stale KB documents detected. Data quarantined.")
else:
    st.success("✅ **SYSTEM HEALTHY**: All contract checks, freshness SLAs, and pipeline models are within nominal boundaries.")

# Top KPIs Row
kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
with kpi1:
    st.metric("Orders Ingested", f"{report.get('orders_rows', 0):,} rows")
with kpi2:
    fresh_min = report.get("freshness_minutes", 0.0)
    st.metric("Orders Freshness", f"{fresh_min:.1f} min", delta="SLA: < 30m", delta_color="inverse" if fresh_min > 30 else "normal")
with kpi3:
    kb_fresh_min = report.get("kb_freshness_minutes", 0.0)
    st.metric("KB Freshness", f"{kb_fresh_min:.1f} min", delta="SLA: < 60m", delta_color="inverse" if kb_fresh_min > 60 else "normal")
with kpi4:
    slo_info = report.get("contract_slo", {})
    budget_pct = slo_info.get("remaining_error_budget_fraction", 1.0) * 100
    st.metric("Error Budget Remaining", f"{budget_pct:.1f}%", delta=f"Burn: {slo_info.get('burn_rate', 0.0):.1f}x", delta_color="inverse" if budget_pct < 50 else "normal")
with kpi5:
    alert_info = report.get("burn_rate_alert", {})
    st.metric("Burn Alert Status", alert_info.get("severity", "info").upper(), delta="Paging" if alert_info.get("page") else "No Page")

# Navigation Tabs
tab_overview, tab_contracts, tab_anomaly, tab_lineage, tab_slo, tab_incident = st.tabs([
    "📊 Executive Overview",
    "📋 Data Contracts & Quality",
    "📈 Anomaly & Drift Engine",
    "🕸️ Lineage & Blast Radius",
    "🎯 SLO & Error Budget",
    "🚨 Incident Response & RCA",
])

# 1. Executive Overview Tab
with tab_overview:
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("Signal Status Matrix")
        signal_data = [
            {"Signal": "Orders Row Count Anomaly", "Status": "ANOMALY" if report.get("row_count_anomaly", {}).get("is_anomaly") else "NOMINAL", "Method": report.get("row_count_anomaly", {}).get("method", "N/A"), "Score": f"{report.get('row_count_anomaly', {}).get('score', 0):.2f}"},
            {"Signal": "KB Text Length Drift", "Status": "ANOMALY" if report.get("kb_text_length_signal", {}).get("is_anomaly") else "NOMINAL", "Method": report.get("kb_text_length_signal", {}).get("method", "N/A"), "Score": f"{report.get('kb_text_length_signal', {}).get('score', 0):.2f}"},
            {"Signal": "KB Vector Embedding Shift", "Status": "ANOMALY" if report.get("kb_embedding_signal", {}).get("is_anomaly") else "NOMINAL", "Method": report.get("kb_embedding_signal", {}).get("method", "N/A"), "Score": f"{report.get('kb_embedding_signal', {}).get('score', 0):.2f}"},
            {"Signal": "Contract Integrity SLO", "Status": "BREACH" if slo_info.get("breached") else "NOMINAL", "Method": "SLI/SLO Ratio", "Score": f"{slo_info.get('actual_bad_rate', 0):.4f}"},
            {"Signal": "Multi-Window Burn-Rate Alert", "Status": "PAGING" if alert_info.get("page") else "NORMAL", "Method": "SRE Standard 2-Window", "Score": f"Short={alert_info.get('short_window_burn', 0):.1f}x"},
        ]
        st.dataframe(pd.DataFrame(signal_data), use_container_width=True, hide_index=True)

    with col_right:
        st.subheader("Quick Blast Radius Summary")
        blast = report.get("sample_blast_radius_from_stg_orders", [])
        st.write(f"**Root Asset:** `stg_orders`")
        st.write(f"**Impacted Assets ({len(blast)}):**")
        for idx, asset in enumerate(blast, start=1):
            st.markdown(f"{idx}. `{asset}`")

# 2. Data Contracts & Quality Tab
with tab_contracts:
    st.subheader("Contract Validation Results")
    all_issues = report.get("all_issues", [])
    if all_issues:
        issues_df = pd.DataFrame(all_issues)
        st.dataframe(issues_df, use_container_width=True, hide_index=True)
    else:
        st.info("No contract issues detected. All checks passed.")

# 3. Anomaly & Drift Engine Tab
with tab_anomaly:
    st.subheader("Volume & Metric History")
    if not history.empty and "date" in history.columns:
        c1, c2 = st.columns(2)
        with c1:
            st.write("#### Ingestion Volume Trend")
            st.line_chart(history.set_index("date")[["row_count"]])
        with c2:
            st.write("#### Average Order Value & Text Length Trend")
            chart_cols = [c for c in ["avg_amount", "mean_text_length"] if c in history.columns]
            st.line_chart(history.set_index("date")[chart_cols])

# 4. Lineage & Blast Radius Tab
with tab_lineage:
    st.subheader("Data Lineage Graph")
    if LINEAGE_FILE.exists():
        with open(LINEAGE_FILE, "r", encoding="utf-8") as f:
            lineage_graph = json.load(f)
        
        col_ds, col_col = st.columns(2)
        with col_ds:
            st.write("#### Dataset-Level Dependencies")
            st.json(lineage_graph.get("dataset_lineage", {}))
        with col_col:
            st.write("#### Column-Level Dependencies")
            st.json(lineage_graph.get("column_lineage", {}))

# 5. SLO & Error Budget Tab
with tab_slo:
    st.subheader("Service Level Objectives (SLO)")
    st.write(f"**Target Reliability:** {slo_info.get('target', 0.999) * 100:.2f}%")
    st.write(f"**Allowed Bad Event Rate:** {slo_info.get('allowed_bad_rate', 0.001):.4f}")
    st.write(f"**Actual Bad Event Rate:** {slo_info.get('actual_bad_rate', 0.0):.4f}")
    st.write(f"**Normalized Burn Rate:** {slo_info.get('burn_rate', 0.0):.2f}x")
    st.progress(float(min(1.0, max(0.0, slo_info.get("remaining_error_budget_fraction", 1.0)))))

# 6. Incident Response Tab
with tab_incident:
    st.subheader("Incident Triage & Runbook")
    st.markdown("""
    ### Standard Operating Procedure (SOP)
    1. **Triage Signal:** Identify if the failure is deterministic (Contract / dbt test) or statistical (Anomaly / KS drift).
    2. **Check Severity:** If `critical`, ensure pipeline gate has blocked downstream jobs (`orders_action == 'block'`).
    3. **Evaluate Blast Radius:** Trace downstream assets via Lineage to alert affected stakeholders (e.g., CEO Revenue Dashboard, Support AI Agent).
    4. **Mitigate & Quarantine:** Isolate corrupt batch, revert schema/data drift, and restore healthy upstream source.
    5. **Verify Recovery:** Run `make baseline` and `make dbt` to ensure all tests pass and burn rate returns to 0.
    """)
