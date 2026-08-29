"""Lineage and blast radius analysis engine.

Supports dataset-level and column-level transitive lineage traversal,
and parses dbt manifest artifacts to construct dependency graphs.
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any


def load_graph(path: str | Path) -> dict[str, list[str]]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload["dataset_lineage"] if "dataset_lineage" in payload else payload


def get_downstream_assets(graph: dict[str, list[str]], start: str) -> list[str]:
    """Return transitive downstream assets in BFS order, excluding start."""
    seen = {start}
    q: deque[str] = deque([start])
    out: list[str] = []
    while q:
        node = q.popleft()
        for child in graph.get(node, []):
            if child not in seen:
                seen.add(child)
                out.append(child)
                q.append(child)
    return out


def get_column_downstream(
    column_graph: dict[str, list[str]], start_column: str
) -> list[str]:
    """Return transitive downstream columns in BFS order, excluding start_column."""
    seen = {start_column}
    q: deque[str] = deque([start_column])
    out: list[str] = []
    while q:
        node = q.popleft()
        for child in column_graph.get(node, []):
            if child not in seen:
                seen.add(child)
                out.append(child)
                q.append(child)
    return out


def extract_dbt_dataset_graph(manifest_path: str | Path) -> dict[str, list[str]]:
    """Parse dbt manifest.json to extract dataset-level and model dependency graphs."""
    path = Path(manifest_path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    graph: dict[str, list[str]] = {}
    child_map = manifest.get("child_map", {})
    for parent, children in child_map.items():
        # Clean dbt unique_ids (e.g., 'model.dbt_project.stg_orders' -> 'stg_orders')
        clean_parent = parent.split(".")[-1] if "." in parent else parent
        clean_children = [c.split(".")[-1] if "." in c else c for c in children]
        if clean_parent not in graph:
            graph[clean_parent] = []
        for c in clean_children:
            if c not in graph[clean_parent]:
                graph[clean_parent].append(c)
    return graph
