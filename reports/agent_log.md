# AI Agent Decision Log — Data Reliability Lab

## Decision 1: Python Environment & Great Expectations Compatibility
- **Hypothesis**: Great Expectations 1.21.0 requires Python `>=3.10,<3.14`. Python 3.14 (system default) fails wheel installation.
- **Prompt / Request to Agent**: Initialize virtual environment and install project dependencies.
- **Agent Proposal**: Create a dedicated virtual environment with Python 3.11 (`/opt/homebrew/bin/python3.11 -m venv .venv`) and install `requirements.txt`.
- **Evidence / Test**: Successfully installed all packages including `great_expectations==1.21.0`, `duckdb==1.5.5`, and `dbt-duckdb==1.11.0`.
- **Accept / Reject / Revise**: **Accept**.
- **Why**: Ensures 100% compatibility with GX Core 1.21 modern API and dbt-duckdb adapter.

---

## Decision 2: Strict Type Validation without Silent Coercion
- **Hypothesis**: Starter code used `pd.to_numeric(series, errors='coerce')` which converts unparseable strings to `NaN`, hiding type drift if not checked explicitly.
- **Prompt / Request to Agent**: Upgrade `src/contract_validator.py` with type checking, freshness, field lengths, and action routing.
- **Agent Proposal**: Implement explicit type checkers (`_check_integer_type`, `_check_number_type`, `_check_datetime_type`, `_check_boolean_type`) that verify raw values before coercion and issue descriptive failure messages.
- **Evidence / Test**: Unit test `test_type_drift_is_detected` passed when `order_id` contained non-integer strings.
- **Accept / Reject / Revise**: **Accept**.
- **Why**: Eliminates silent type coercion vulnerabilities in ingestion pipelines.

---

## Decision 3: Robust Anomaly Detection & Zero-MAD Edge Case
- **Hypothesis**: Standard MAD detector crashes or returns zero score when >50% of history is identical (MAD = 0), and Z-score produces false positives on weekend seasonality.
- **Prompt / Request to Agent**: Implement context-aware seasonality in `detect_anomaly` and fix zero-MAD edge case.
- **Agent Proposal**: Fallback to Mean Absolute Deviation / sample standard deviation when MAD is zero; in `auto` mode, inspect `context` for `same_segment_history` and `day_of_week`.
- **Evidence / Test**: `test_mad_zero_handling` and `test_auto_context_seasonality` passed cleanly; 75% volume drop detected with modified Z-score of 5.53.
- **Accept / Reject / Revise**: **Accept**.
- **Why**: Handles both zero-variance history and weekend traffic patterns without false positive paging.

---

## Decision 4: dbt Mart Hardening & SCD Type 2 Fan-out Protection
- **Hypothesis**: Joining `completed_orders` to `stg_customers` where a customer has multiple active records inflates revenue without throwing SQL syntax errors.
- **Prompt / Request to Agent**: Hardened `fct_daily_revenue.sql`, write singular tests, and dbt native unit tests.
- **Agent Proposal**:
  1. Deduplicate active customers via `select distinct customer_id from {{ ref('stg_customers') }} where is_active = true`.
  2. Create `unit_tests.yml` with test case `duplicate_active_customers_do_not_inflate_revenue`.
  3. Add `assert_daily_revenue_consistency.sql` singular test.
- **Evidence / Test**: `dbt build` completed with 20/20 PASS (3 models, 12 data tests, 3 unit tests, 2 seeds).
- **Accept / Reject / Revise**: **Accept**.
- **Why**: Guarantees idempotent aggregation in downstream financial marts.

---

## Decision 5: Multi-Window Multi-Burn-Rate Alerting
- **Hypothesis**: Single-window burn rate alerts trigger noisy pages on short transient spikes. Multi-window alerting (short window + long window) ensures paging only on sustained fast budget consumption.
- **Prompt / Request to Agent**: Implement Google SRE multi-window burn rate policy in `observability/slo.py`.
- **Agent Proposal**: Implement `evaluate_multiwindow_burn()` checking both short window (1h / 14.4x) and long window (6h / 6.0x) conditions. Transient spikes with low long-window burn are suppressed from paging.
- **Evidence / Test**: `test_multiwindow_sustained_fast_burn_pages` and `test_multiwindow_transient_spike_does_not_page` passed.
- **Accept / Reject / Revise**: **Accept**.
- **Why**: Complies with Google SRE alerting standards, reducing on-call fatigue while ensuring rapid MTTA for true incidents.

---

## Decision 6: Transitive Column Lineage Traversal
- **Hypothesis**: Column lineage requires full multi-hop traversal to determine upstream impact on downstream KPI fields (e.g. `raw_orders.amount` -> `ceo_revenue_dashboard.revenue`).
- **Prompt / Request to Agent**: Implement `get_column_downstream` using transitive BFS traversal.
- **Agent Proposal**: Implement BFS queue with visited cycle prevention in `observability/lineage.py`.
- **Evidence / Test**: `test_transitive_column_downstream` successfully returned all 3 downstream column hops.
- **Accept / Reject / Revise**: **Accept**.
- **Why**: Provides automated blast-radius identification for column-level schema migrations and anomalies.
