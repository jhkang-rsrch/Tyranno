"""Aggregated stats for the admin dashboard."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ART = Path(__file__).resolve().parent / "artifacts"


def _read(name: str) -> pd.DataFrame:
    """Read a vendored stats csv from artifacts/. Returns empty df if missing."""
    p = ART / name
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p, encoding="utf-8-sig")


def _records(df: pd.DataFrame) -> list[dict]:
    """JSON-safe records: NaN/inf -> None."""
    return df.replace({np.nan: None, np.inf: None, -np.inf: None}).to_dict(orient="records")


def category_tree(predictor) -> dict:
    """Hierarchy of biz → mid → sub built from sub_stats."""
    df = predictor.sub_stats
    tree: dict[str, dict[str, list[str]]] = {}
    for _, r in df.iterrows():
        biz = str(r["사업구분명"])
        mid = str(r["단위사업중분류명"])
        sub = str(r["단위사업소분류명"])
        tree.setdefault(biz, {}).setdefault(mid, [])
        if sub not in tree[biz][mid]:
            tree[biz][mid].append(sub)
    return tree


def biz_avg_days(predictor) -> list[dict]:
    df = predictor.biz_stats.sort_values("mean")
    df = df[["사업구분명", "count", "mean", "median", "std"]].rename(
        columns={"사업구분명": "biz", "count": "n", "mean": "avg_days",
                  "median": "median_days", "std": "std_days"}
    )
    return _records(df)


def mid_avg_days(predictor, biz: str | None = None) -> list[dict]:
    df = predictor.mid_stats
    if biz:
        df = df[df["사업구분명"] == biz]
    df = df.rename(columns={"사업구분명": "biz", "단위사업중분류명": "mid",
                              "count": "n", "mean": "avg_days",
                              "median": "median_days", "std": "std_days"})
    return _records(df)


def sub_avg_days(predictor, biz: str | None = None, mid: str | None = None) -> list[dict]:
    df = predictor.sub_stats
    if biz:
        df = df[df["사업구분명"] == biz]
    if mid:
        df = df[df["단위사업중분류명"] == mid]
    df = df.rename(columns={"사업구분명": "biz", "단위사업중분류명": "mid",
                              "단위사업소분류명": "sub", "count": "n",
                              "mean": "avg_days", "median": "median_days",
                              "std": "std_days"})
    return _records(df)


def monthly_volume() -> list[dict]:
    df = _read("05_monthly_count.csv")
    if df.empty:
        return []
    cols = list(df.columns)
    df = df.rename(columns={cols[0]: "month", cols[1]: "count"})
    return _records(df)


def yearly_volume() -> list[dict]:
    df = _read("07_yearly_count.csv")
    if df.empty:
        return []
    cols = list(df.columns)
    df = df.rename(columns={cols[0]: "year", cols[1]: "count"})
    return _records(df)


def congestion_heat() -> list[dict]:
    df = _read("08_seasonality_month.csv")
    if df.empty:
        return []
    cols = list(df.columns)
    df = df.rename(columns={cols[0]: "month", cols[1]: "count"})
    return _records(df)
