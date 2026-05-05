"""Predictor wrapper around LightGBM proc-days model with SHAP support."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap

ART = Path(__file__).resolve().parent / "artifacts"


class ProcDaysPredictor:
    def __init__(self) -> None:
        self.booster = lgb.Booster(model_file=str(ART / "lgbm_proc_days.txt"))
        with open(ART / "category_maps.json", encoding="utf-8") as f:
            spec = json.load(f)
        self.cat_cols: list[str] = spec["cat"]
        self.num_cols: list[str] = spec["num"]
        self.categories: dict[str, list[str]] = spec["categories"]
        self.best_iteration: int = int(spec["best_iteration"])
        with open(ART / "global_stats.json", encoding="utf-8") as f:
            g = json.load(f)
        self.monthly_volume: dict[str, int] = g["monthly_volume"]
        self.biz_monthly_volume: dict[str, int] = g["biz_monthly_volume"]
        self.monthly_avg: float = g["monthly_avg"]
        self.overall_mean: float = g["overall_mean_proc"]
        self.overall_median: float = g["overall_median_proc"]
        self._explainer: Optional[shap.TreeExplainer] = None

        # quick lookup tables
        self.sub_stats = pd.read_csv(ART / "sub_stats.csv", encoding="utf-8-sig")
        self.mid_stats = pd.read_csv(ART / "mid_stats.csv", encoding="utf-8-sig")
        self.biz_stats = pd.read_csv(ART / "biz_stats.csv", encoding="utf-8-sig")

    # ------------------------------------------------------------------
    def _coerce_cat(self, name: str, value: str) -> str:
        cats = self.categories[name]
        s = str(value)
        if s in cats:
            return s
        # fall back to most-frequent (the booster will treat unknown as NaN)
        return cats[0] if cats else s

    def build_row(self, *, biz: str, mid: str, sub: str, received_on: date) -> pd.DataFrame:
        ym = received_on.strftime("%Y-%m")
        m_vol = self.monthly_volume.get(ym, self.monthly_avg)
        b_vol = self.biz_monthly_volume.get(f"{ym}|{biz}", m_vol * 0.05)
        row = {
            "사업구분명": self._coerce_cat("사업구분명", biz),
            "단위사업중분류명": self._coerce_cat("단위사업중분류명", mid),
            "단위사업소분류명": self._coerce_cat("단위사업소분류명", sub),
            "요일": str(received_on.weekday()),
            "월": str(received_on.month),
            "분기": str((received_on.month - 1) // 3 + 1),
            "연도": float(received_on.year),
            "월일": float(received_on.day),
            "연중일": float(received_on.timetuple().tm_yday),
            "월총접수량": float(m_vol),
            "사업구분_월접수량": float(b_vol),
        }
        df = pd.DataFrame([row])
        for c in self.cat_cols:
            df[c] = pd.Categorical(df[c], categories=self.categories[c])
        return df[self.cat_cols + self.num_cols]

    # ------------------------------------------------------------------
    def predict(self, *, biz: str, mid: str, sub: str, received_on: date) -> dict:
        df = self.build_row(biz=biz, mid=mid, sub=sub, received_on=received_on)
        log_pred = float(self.booster.predict(df, num_iteration=self.best_iteration)[0])
        days = float(np.clip(np.expm1(log_pred), 0, 365))

        # historical baseline for the same subcategory (uncertainty band)
        sub_row = self.sub_stats[
            (self.sub_stats["사업구분명"] == biz)
            & (self.sub_stats["단위사업중분류명"] == mid)
            & (self.sub_stats["단위사업소분류명"] == sub)
        ]
        if len(sub_row):
            std = float(sub_row.iloc[0].get("std") or 0) or 7.0
            n = int(sub_row.iloc[0].get("count") or 0)
            hist_mean = float(sub_row.iloc[0]["mean"])
            hist_median = float(sub_row.iloc[0]["median"])
        else:
            mid_row = self.mid_stats[
                (self.mid_stats["사업구분명"] == biz)
                & (self.mid_stats["단위사업중분류명"] == mid)
            ]
            if len(mid_row):
                std = float(mid_row.iloc[0].get("std") or 0) or 7.0
                n = int(mid_row.iloc[0]["count"])
                hist_mean = float(mid_row.iloc[0]["mean"])
                hist_median = float(mid_row.iloc[0]["median"])
            else:
                std, n = 10.0, 0
                hist_mean = self.overall_mean
                hist_median = self.overall_median

        # 80% band from std
        low = max(0.0, days - 0.8 * std)
        high = days + 0.8 * std

        # confidence: more samples & lower std → higher
        conf = max(0.4, min(0.95, 0.85 - min(std, 30) / 80 + min(np.log10(max(n, 1)) / 6, 0.15)))

        # congestion grade based on monthly volume vs avg
        ym = received_on.strftime("%Y-%m")
        m_vol = self.monthly_volume.get(ym, self.monthly_avg)
        ratio = m_vol / max(self.monthly_avg, 1.0)
        if ratio < 0.85:
            congestion = "낮음"
        elif ratio < 1.1:
            congestion = "보통"
        elif ratio < 1.3:
            congestion = "높음"
        else:
            congestion = "매우 높음"

        complete_on = add_business_days(received_on, int(round(days)))

        return {
            "predicted_days": round(days, 2),
            "low_days": round(low, 2),
            "high_days": round(high, 2),
            "predicted_complete_at": complete_on.isoformat(),
            "history_mean": round(hist_mean, 2),
            "history_median": round(hist_median, 2),
            "history_std": round(std, 2),
            "history_count": n,
            "congestion": congestion,
            "monthly_volume": int(m_vol),
            "monthly_avg": round(self.monthly_avg, 1),
            "confidence": round(float(conf), 2),
        }

    # ------------------------------------------------------------------
    def explain(self, *, biz: str, mid: str, sub: str, received_on: date, top_k: int = 6) -> dict:
        df = self.build_row(biz=biz, mid=mid, sub=sub, received_on=received_on)
        if self._explainer is None:
            self._explainer = shap.TreeExplainer(self.booster)
        sv = self._explainer.shap_values(df)
        if isinstance(sv, list):
            sv = sv[0]
        sv = np.asarray(sv).reshape(-1)
        feats = self.cat_cols + self.num_cols
        contrib = []
        for f, v in zip(feats, sv):
            contrib.append({"feature": f, "value": str(df.iloc[0][f]),
                             "shap": float(v)})
        contrib.sort(key=lambda x: abs(x["shap"]), reverse=True)
        base = float(self._explainer.expected_value if np.ndim(self._explainer.expected_value) == 0
                     else self._explainer.expected_value[0])
        return {
            "base_value_log": round(base, 4),
            "base_value_days": round(float(np.expm1(base)), 2),
            "top_features": contrib[:top_k],
            "all_features": contrib,
        }


def add_business_days(start: date, days: int) -> date:
    """Skip Sat/Sun. start itself is the receipt day, completion is +days."""
    d = start
    remaining = max(0, int(days))
    while remaining > 0:
        d = d + timedelta(days=1)
        if d.weekday() < 5:
            remaining -= 1
    return d


# singleton
_predictor: Optional[ProcDaysPredictor] = None


def get_predictor() -> ProcDaysPredictor:
    global _predictor
    if _predictor is None:
        _predictor = ProcDaysPredictor()
    return _predictor
