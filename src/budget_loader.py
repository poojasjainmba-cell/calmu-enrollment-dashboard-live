from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

import pandas as pd

from .goal_loader import GoalParseResult, load_goal_workbook


def load_budget_reference(source: str | Path | BinaryIO | None) -> GoalParseResult:
    return load_goal_workbook(source)


def summarize_budget(goals: pd.DataFrame) -> pd.DataFrame:
    if goals.empty:
        return pd.DataFrame()
    grouped = (
        goals.groupby(["entity_type", "term_label"], dropna=False)
        .agg(actual=("actual", "sum"), goal=("goal", "sum"), rows=("entity", "count"))
        .reset_index()
    )
    grouped["variance"] = grouped["actual"] - grouped["goal"]
    grouped["pct_to_goal"] = grouped.apply(lambda row: row["actual"] / row["goal"] if row["goal"] else pd.NA, axis=1)
    return grouped
