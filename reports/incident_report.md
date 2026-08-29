# Incident Report — Data Reliability Game Day

## 1. Incident Overview

| Incident ID | Incident Name | Severity | Detection Mechanism | Status |
|---|---|---|---|---|
| INC-2026-08-01 | Upstream Primary Key Duplication (`order_id`) | **P1 (Critical)** | Data Contract & GX Checkpoint | Resolved |
| INC-2026-08-02 | Silent Ingestion Pipeline Volume Drop (75% loss) | **P1 (Critical)** | Robust MAD Anomaly Detection | Resolved |
| INC-2026-08-03 | Knowledge Base Stale Publish Timestamp Drift (-3h) | **P2 (Major)** | Freshness Contract & RAG Signals | Resolved |

---

## 2. Deep-Dive RCA: Incident INC-2026-08-01 (Duplicate PK)

### Severity
**P1 — Critical** (Direct financial reporting corruption on CEO Revenue Dashboard).

### Summary
Upstream payment processing re-ingested duplicate order batches, introducing duplicate `order_id` values. Downstream joins between orders and active customers inflated daily revenue numbers without throwing any SQL runtime errors.

### Detection
- **Signal**: Contract validation `unique` check on `order_id` failed (`passed=False`, `duplicate_rows=6`).
- **SLO Impact**: Critical contract failure burned 37.04x error budget, triggering immediate on-call paging (`page=True, severity="critical"`).
- **First Observed Time**: 2026-08-29T08:19:00Z.

### Root Cause
Upstream retry logic lacked idempotent deduplication, causing identical order rows to be written multiple times to `orders.csv`.

### Evidence
1. Contract validator returned: `{"check": "unique", "column": "order_id", "severity": "critical", "passed": False, "details": "duplicate_rows=6"}`.
2. Great Expectations checkpoint failed with `ExpectColumnValuesToBeUnique(column='order_id')`.
3. dbt generic test `unique_stg_orders_order_id` failed in staging.

### Blast Radius
```text
raw_orders (orders.csv)
 └── stg_orders.order_id
      └── fct_daily_revenue (daily_revenue inflated)
           └── ceo_revenue_dashboard (incorrect executive revenue KPIs)
```

### Mitigation
- Automated contract validator triggered `block` action to halt downstream ETL execution immediately.

### Recovery
1. Enforced deduplication in `fct_daily_revenue.sql` (`select distinct customer_id`).
2. Re-ran ingestion with clean source data (`make reset && make baseline`).
3. Verified all dbt tests and GX expectations passed (`20/20 PASS`).

---

## 3. Deep-Dive RCA: Incident INC-2026-08-02 (Volume Drop Anomaly)

### Severity
**P1 — Critical** (Severe under-reporting of completed transactions across marts and dashboards).

### Summary
Ingestion pipeline experienced network truncation, receiving only 150 out of 600 expected orders (75% data loss). The data format was syntactically valid (all types/columns passed deterministic contracts), but total transaction volume dropped precipitously.

### Detection
- **Signal**: Context-aware `detect_anomaly(len(orders), history, method="auto")` flagged `is_anomaly=True` with a robust modified Z-score of 5.53.
- **Why Rules Failed**: Deterministic schema checks (not-null, types) passed because the 150 ingested rows were well-formed; statistical anomaly detection was required to catch the missing data volume.
- **First Observed Time**: 2026-08-29T08:19:53Z.

### Root Cause
Upstream API gateway timeout cut off bulk CSV streaming before full payload transmission completed.

### Evidence
1. `row_count_anomaly` output: `{"is_anomaly": True, "score": 5.53, "method": "auto:robust_mad"}`.
2. Ingested row count was 150 vs. historical median of 600 on weekdays.
3. Downstream `fct_daily_revenue` row count collapsed by ~75%.

### Blast Radius
```text
raw_orders
 └── stg_orders
      └── fct_daily_revenue (revenue dropped by ~75%)
           └── ceo_revenue_dashboard (artificial revenue cliff reported to leadership)
```

### Mitigation
- Flagged anomaly in ingestion monitor and quarantined truncated batch before mart calculation.

### Recovery
1. Re-triggered upstream pipeline batch extraction.
2. Validated row count returned to nominal range (600 rows).
3. Verified anomaly detector cleared (`is_anomaly=False`).

---

## 4. Deep-Dive RCA: Incident INC-2026-08-03 (Stale Knowledge Base)

### Severity
**P2 — Major** (Customer support agent serving obsolete refund policy to customers).

### Summary
Knowledge base document ingestion job stalled, leaving `published_at` timestamps delayed by over 3 hours (> 180 minutes vs. 60-minute SLA), causing support agent to index stale refund terms.

### Detection
- **Signal**: KB contract freshness check failed: `delay_minutes=190.0; max_delay_minutes=60.0` with action `quarantine`.
- **First Observed Time**: 2026-08-29T08:20:00Z.

### Root Cause
Sync worker crashed silently during document crawler execution, leaving old document versions active.

### Evidence
1. Contract validator returned: `{"check": "freshness", "column": "published_at", "severity": "warning", "passed": False, "details": "delay_minutes=190.0; max_delay_minutes=60.0"}`.
2. Document timestamp was 3 hours older than current UTC time.
3. RAG index embedding monitor reported outdated document hash.

### Blast Radius
```text
kb_documents.jsonl
 └── kb_active_docs
      └── rag_index.embedding
           └── support_agent.answer (outdated policies delivered to customers)
```

### Mitigation
- Quarantined stale documents to prevent vector store re-indexing.

### Recovery
1. Restarted KB document crawler with latest policies.
2. Verified `published_at` delay reduced to < 15 minutes.
3. Freshness check returned `passed=True` with action `pass`.

---

## 5. Verification Checklist

- [x] **Contract healthy**: All checks passing on clean incoming batches (`determine_action == "pass"`).
- [x] **dbt tests healthy**: 20/20 targets passed (models, data tests, singular tests, and unit tests).
- [x] **Anomaly returned to expected range**: Row count and text length signals within nominal bounds.
- [x] **SLO healthy**: Error budget intact (100% remaining), burn rate = 0.0x.
- [x] **Downstream output verified**: `fct_daily_revenue` correctly aggregates completed orders without inflation or drops.

---

## 6. Prevention & Action Items

| Action | Owner | Deadline | Why |
|---|---|---|---|
| Enforce Great Expectations Checkpoint in CI/CD pipeline | Data Platform | 2026-09-05 | Block unvalidated schema changes before reaching warehouse |
| Deploy Multi-Window Burn-Rate Alerting in PagerDuty | SRE Team | 2026-09-08 | Prevent alert fatigue from short spikes while catching fast burns |
| Add SCD Type 2 Customer Dimension deduplication | Analytics Eng | 2026-09-03 | Eliminate join fan-out risk in revenue marts |
| Implement Automated KB Freshness Heartbeat Monitor | AI/RAG Team | 2026-09-04 | Prevent stale policy indexing in RAG embeddings |
