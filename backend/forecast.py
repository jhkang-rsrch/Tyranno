"""Workload forecasting from historical seasonality + recent trend.

The admin uses these to anticipate spikes and prepare capacity.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ART = Path(__file__).resolve().parent / "artifacts"


def _read(name: str) -> pd.DataFrame:
    p = ART / name
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p, encoding="utf-8-sig")


def _safe(d: pd.DataFrame) -> list[dict]:
    return d.replace({np.nan: None, np.inf: None, -np.inf: None}).to_dict(orient="records")


# ----------------------------------------------------------- forecast: overall
def overall_forecast(horizon: int = 6) -> dict:
    """Project the next `horizon` months using level (recent 12-month avg) ×
    month-of-year seasonality factor. Also back-test on last 12 months."""
    monthly = _read("05_monthly_count.csv")           # ym, count
    season = _read("08_seasonality_month.csv")        # month, count
    if monthly.empty or season.empty:
        return {"history": [], "forecast": [], "backtest_mae": None}

    monthly["ym"] = pd.to_datetime(monthly["월"] if "월" in monthly.columns else monthly["연월"], errors="coerce") if False else pd.to_datetime(monthly.iloc[:,0], errors="coerce")
    monthly = monthly.dropna(subset=["ym"]).sort_values("ym").reset_index(drop=True)
    monthly["count"] = monthly.iloc[:,1].astype(float)

    # Seasonality factor (mean = 1.0)
    season["m"] = season.iloc[:,0].astype(int)
    season["c"] = season.iloc[:,1].astype(float)
    smean = season["c"].mean() or 1.0
    factor = {int(r["m"]): float(r["c"]) / smean for _, r in season.iterrows()}

    # Recent level: deseasonalized mean of last 12 months
    last12 = monthly.tail(12).copy()
    last12["m"] = last12["ym"].dt.month
    last12["deseason"] = last12.apply(lambda r: r["count"] / factor.get(int(r["m"]), 1.0), axis=1)
    level = last12["deseason"].mean()

    # Backtest: predict each of last 12 from level computed without it (rolling)
    bt = []
    for i in range(12, 0, -1):
        train = monthly.iloc[:-i] if i > 0 else monthly
        if len(train) < 13: continue
        tail = train.tail(12).copy()
        tail["m"] = tail["ym"].dt.month
        tail["des"] = tail.apply(lambda r: r["count"] / factor.get(int(r["m"]), 1.0), axis=1)
        lvl = tail["des"].mean()
        target_row = monthly.iloc[-i]
        m = int(target_row["ym"].month)
        pred = lvl * factor.get(m, 1.0)
        bt.append({"ym": target_row["ym"].strftime("%Y-%m"),
                    "actual": float(target_row["count"]),
                    "pred": float(pred)})
    mae = float(np.mean([abs(b["actual"] - b["pred"]) for b in bt])) if bt else None

    # Forecast horizon
    last_ym = monthly["ym"].iloc[-1]
    fc = []
    for k in range(1, horizon + 1):
        nxt = (last_ym + pd.offsets.MonthBegin(k)).to_pydatetime().date()
        m = nxt.month
        f = factor.get(m, 1.0)
        pred = level * f
        # 80% band: ±1.28 σ of recent residuals
        resid = last12["count"] - last12.apply(lambda r: level * factor.get(int(r["m"]), 1.0), axis=1)
        sigma = float(resid.std() or 0)
        fc.append({
            "ym": nxt.strftime("%Y-%m"),
            "month": int(m),
            "predicted": float(round(pred)),
            "low": float(round(max(0, pred - 1.28 * sigma))),
            "high": float(round(pred + 1.28 * sigma)),
            "factor": round(float(f), 3),
            "is_peak": bool(f >= 1.10),
        })

    history = [{"ym": r["ym"].strftime("%Y-%m"), "count": float(r["count"])} for _, r in monthly.iterrows()]
    return {"history": history, "forecast": fc, "backtest_mae": round(mae, 1) if mae else None,
             "level": round(float(level), 1)}


# ----------------------------------------------------------- per-biz seasonal heat
def biz_seasonal_heat() -> list[dict]:
    """For each 사업구분, return month-of-year share (%). Hot months stand out."""
    df = _read("09_biz_month.csv")
    if df.empty: return []
    out = []
    for biz, g in df.groupby("사업구분명"):
        total = g["count"].sum() or 1
        row = {"biz": biz, "total": int(total), "months": {}}
        for _, r in g.iterrows():
            row["months"][int(r["m"])] = round(float(r["count"]) / total * 100, 2)
        out.append(row)
    out.sort(key=lambda x: -x["total"])
    return out


# ----------------------------------------------------------- expected hot categories next month
def upcoming_hotspots(target: date | None = None, top_k: int = 10) -> dict:
    """For the (next) month, return top categories whose seasonal share is
    above their own annual average — i.e. seasonally surging right now.

    Score = (share_of_target_month / annual_avg_share) × log(1 + total)
    """
    today = target or date.today()
    nxt_month = today.month % 12 + 1   # next month's number
    cur_month = today.month

    df = _read("10_mid_month.csv")
    if df.empty:
        return {"target_month": nxt_month, "rows": []}

    rows = []
    for (biz, mid), g in df.groupby(["사업구분명","단위사업중분류명"]):
        total = float(g["count"].sum())
        if total < 50: continue
        avg = total / 12.0
        cur = float(g.loc[g["m"] == cur_month, "count"].sum())
        nxt = float(g.loc[g["m"] == nxt_month, "count"].sum())
        cur_ratio = cur / avg if avg > 0 else 0
        nxt_ratio = nxt / avg if avg > 0 else 0
        score = nxt_ratio * np.log1p(total)
        rows.append({
            "biz": biz, "mid": mid, "total": int(total),
            "current_count": int(cur), "current_ratio": round(float(cur_ratio), 2),
            "next_count": int(nxt), "next_ratio": round(float(nxt_ratio), 2),
            "score": round(float(score), 3),
            "alert": bool(nxt_ratio >= 1.20),
        })
    rows.sort(key=lambda r: -r["score"])
    return {"current_month": cur_month, "next_month": nxt_month,
             "rows": rows[:top_k]}


# ----------------------------------------------------------- yoy growth
def biz_yoy_growth(min_count: int = 100) -> list[dict]:
    """Last-vs-prior year growth rate per 사업구분."""
    df = _read("12_biz_yearly.csv")
    if df.empty: return []
    out = []
    for biz, g in df.groupby("사업구분명"):
        g = g.sort_values("y")
        if len(g) < 2: continue
        last2 = g.tail(2)
        prev = float(last2["count"].iloc[0]); curr = float(last2["count"].iloc[1])
        if curr + prev < min_count: continue
        growth = (curr - prev) / prev if prev > 0 else None
        out.append({
            "biz": biz,
            "prev_year": int(last2["y"].iloc[0]),
            "curr_year": int(last2["y"].iloc[1]),
            "prev": int(prev), "curr": int(curr),
            "growth": round(growth, 3) if growth is not None else None,
        })
    out.sort(key=lambda r: -(r["growth"] or -1))
    return out


# ----------------------------------------------------------- per-biz monthly time-series
def biz_monthly_series(biz: str) -> list[dict]:
    df = _read("11_biz_monthly.csv")
    if df.empty: return []
    g = df[df["사업구분명"] == biz].sort_values("ym")
    return [{"ym": r["ym"], "count": int(r["count"])} for _, r in g.iterrows()]
