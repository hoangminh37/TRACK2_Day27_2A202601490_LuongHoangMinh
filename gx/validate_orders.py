#!/usr/bin/env python3
"""Great Expectations Core 1.21 Checkpoint and Suite Validation Flow.

Encapsulates complete dataset validation into an Expectation Suite, Validation Definition,
and Checkpoint with severity-aware actions (block pipeline on critical failure).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import great_expectations as gx
except ImportError as exc:
    raise SystemExit("great_expectations is not installed. Run: pip install -r requirements.txt") from exc


def build_orders_suite(context: gx.DataContext) -> gx.ExpectationSuite:
    suite = context.suites.add(gx.ExpectationSuite(name="orders_contract_suite"))
    
    # 1. Primary identifier checks
    suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column="order_id"))
    suite.add_expectation(gx.expectations.ExpectColumnValuesToBeUnique(column="order_id"))
    
    # 2. Foreign key / customer check
    suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column="customer_id"))
    
    # 3. Numeric constraints
    suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column="amount"))
    suite.add_expectation(gx.expectations.ExpectColumnValuesToBeBetween(column="amount", min_value=0))
    
    # 4. Enumeration / accepted values
    suite.add_expectation(gx.expectations.ExpectColumnValuesToBeInSet(column="currency", value_set=["USD", "VND"]))
    suite.add_expectation(gx.expectations.ExpectColumnValuesToBeInSet(
        column="status",
        value_set=["pending", "completed", "refunded", "cancelled"]
    ))
    
    # 5. Timestamp existence
    suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column="created_at"))
    suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column="updated_at"))

    return suite


def run_orders_validation(df: pd.DataFrame) -> tuple[bool, dict[str, Any]]:
    context = gx.get_context(mode="ephemeral")
    
    # Register data source and asset
    data_source = context.data_sources.add_pandas("orders_source")
    asset = data_source.add_dataframe_asset(name="orders_asset")
    batch_definition = asset.add_batch_definition_whole_dataframe("orders_batch_def")
    
    # Build Suite
    suite = build_orders_suite(context)
    
    # Create Validation Definition
    validation_def = context.validation_definitions.add(
        gx.ValidationDefinition(
            name="orders_validation_definition",
            data=batch_definition,
            suite=suite,
        )
    )
    
    # Configure Checkpoint
    checkpoint = context.checkpoints.add(
        gx.Checkpoint(
            name="orders_checkpoint",
            validation_definitions=[validation_def],
            result_format={"result_format": "SUMMARY"},
        )
    )
    
    # Execute Checkpoint
    checkpoint_result = checkpoint.run(batch_parameters={"dataframe": df})
    
    summary = {
        "success": bool(checkpoint_result.success),
        "validation_results_count": len(checkpoint_result.run_results),
    }
    return checkpoint_result.success, summary


def main() -> None:
    data_path = ROOT / "data" / "incoming" / "orders.csv"
    if not data_path.exists():
        print(f"Data file not found at {data_path}. Run `make reset` first.")
        sys.exit(1)
        
    df = pd.read_csv(data_path)
    print(f"Running Great Expectations 1.21 Checkpoint on {len(df)} orders...")
    
    success, summary = run_orders_validation(df)
    
    print("\n=== GREAT EXPECTATIONS SUMMARY ===")
    print(f"Checkpoint Status: {'PASS' if success else 'FAIL'}")
    print(f"Details          : {summary}")
    
    if not success:
        print("\n[ACTION REQUIRED] Critical expectation failed! Blocking downstream pipeline.")
        sys.exit(1)
    else:
        print("\n[ACTION] All expectations passed. Proceeding to dbt transformations.")


if __name__ == "__main__":
    main()
