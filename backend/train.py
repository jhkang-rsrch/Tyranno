"""Train LightGBM model for processing-days regression and persist
category mappings so the backend can replay the same encoding at inference.

Output:
  backend/artifacts/lgbm_proc_days.txt
  backend/artifacts/category_maps.json
  backend/artifacts/global_stats.json
"""
from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "통합_시험접수_현황.csv"
ART = Path(__file__).resolve().parent / "artifacts"
ART.mkdir(parents=True, exist_ok=True)

CAT_COLS = ["사업구분명", "단위사업중분류명", "단위사업소분류명", "요일", "월", "분기"]
NUM_COLS = ["연도", "월일", "연중일", "월총접수량", "사업구분_월접수량"]


def main() -> None:
    print("[1] load")
    df = pd.read_csv(DATA, encoding="utf-8-sig", dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df["접수일자"] = pd.to_datetime(df["접수일자"], errors="coerce")
    df["처리일수"] = pd.to_numeric(df["처리일수"], errors="coerce")

    mask = df["처리일수"].notna() & df["접수일자"].notna() & (df["처리일수"] >= 0) & (df["처리일수"] <= 365)
    work = df.loc[mask].copy()
    print(f"  rows used: {len(work):,}")

    # time features
    work["연도"] = work["접수일자"].dt.year
    work["월"] = work["접수일자"].dt.month
    work["요일"] = work["접수일자"].dt.dayofweek
    work["분기"] = work["접수일자"].dt.quarter
    work["월일"] = work["접수일자"].dt.day
    work["연중일"] = work["접수일자"].dt.dayofyear

    ym = work["접수일자"].dt.to_period("M").astype(str)
    monthly = work.groupby(ym).size()
    work["월총접수량"] = ym.map(monthly).astype(float)

    biz_vol = (
        work.assign(_ym=ym.values)
        .groupby(["_ym", "사업구분명"], observed=True)
        .size()
        .rename("사업구분_월접수량")
        .reset_index()
    )
    work["_ym"] = ym.values
    work = work.merge(biz_vol, on=["_ym", "사업구분명"], how="left")
    work.drop(columns=["_ym"], inplace=True)
    work["사업구분_월접수량"] = work["사업구분_월접수량"].astype(float)

    # explicit category mappings
    cat_maps: dict[str, list] = {}
    for c in CAT_COLS:
        vals = pd.Index(work[c].astype(str).unique()).sort_values().tolist()
        cat_maps[c] = vals
        work[c] = pd.Categorical(work[c].astype(str), categories=vals)

    X = work[CAT_COLS + NUM_COLS]
    y_raw = work["처리일수"].astype(float).values
    y = np.log1p(y_raw)

    cut = work["접수일자"].max() - pd.DateOffset(months=12)
    tr = work["접수일자"] <= cut
    te = ~tr

    print("[2] train")
    params = dict(
        objective="regression",
        metric="rmse",
        learning_rate=0.05,
        num_leaves=128,
        min_data_in_leaf=200,
        feature_fraction=0.9,
        bagging_fraction=0.9,
        bagging_freq=5,
        verbose=-1,
    )
    dtr = lgb.Dataset(X[tr], y[tr], categorical_feature=CAT_COLS)
    dte = lgb.Dataset(X[te], y[te], categorical_feature=CAT_COLS, reference=dtr)
    model = lgb.train(
        params,
        dtr,
        num_boost_round=600,
        valid_sets=[dtr, dte],
        valid_names=["train", "valid"],
        callbacks=[lgb.early_stopping(40), lgb.log_evaluation(100)],
    )

    pred = np.clip(np.expm1(model.predict(X[te], num_iteration=model.best_iteration)), 0, 365)
    mae = float(np.mean(np.abs(pred - y_raw[te])))
    print(f"  MAE={mae:.2f}일  best_iter={model.best_iteration}")

    # save model
    model.save_model(str(ART / "lgbm_proc_days.txt"))

    # save category maps
    with open(ART / "category_maps.json", "w", encoding="utf-8") as f:
        json.dump({"cat": CAT_COLS, "num": NUM_COLS, "categories": cat_maps,
                   "best_iteration": model.best_iteration, "test_mae": mae},
                  f, ensure_ascii=False, indent=2)

    # save global stats used at inference time
    monthly_full = monthly.to_dict()
    biz_full = (
        biz_vol.set_index(["_ym", "사업구분명"])["사업구분_월접수량"].to_dict()
    )
    biz_full = {f"{k[0]}|{k[1]}": int(v) for k, v in biz_full.items()}
    monthly_avg = float(monthly.mean())
    sub_stats = (
        work.groupby(["사업구분명", "단위사업중분류명", "단위사업소분류명"], observed=True)["처리일수"]
        .agg(["count", "mean", "median", "std"]).round(2)
        .reset_index()
    )
    sub_stats.to_csv(ART / "sub_stats.csv", index=False, encoding="utf-8-sig")
    mid_stats = (
        work.groupby(["사업구분명", "단위사업중분류명"], observed=True)["처리일수"]
        .agg(["count", "mean", "median", "std"]).round(2)
        .reset_index()
    )
    mid_stats.to_csv(ART / "mid_stats.csv", index=False, encoding="utf-8-sig")
    biz_stats = (
        work.groupby(["사업구분명"], observed=True)["처리일수"]
        .agg(["count", "mean", "median", "std"]).round(2)
        .reset_index()
    )
    biz_stats.to_csv(ART / "biz_stats.csv", index=False, encoding="utf-8-sig")

    with open(ART / "global_stats.json", "w", encoding="utf-8") as f:
        json.dump({"monthly_volume": {k: int(v) for k, v in monthly_full.items()},
                   "biz_monthly_volume": biz_full,
                   "monthly_avg": monthly_avg,
                   "overall_mean_proc": float(np.mean(y_raw)),
                   "overall_median_proc": float(np.median(y_raw))},
                  f, ensure_ascii=False)
    print("[done]")


if __name__ == "__main__":
    main()
