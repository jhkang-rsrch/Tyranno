"""Retrain LightGBM with data from 2016+ only, validate on the most recent
12 months. Mirrors train.py settings, but writes to artifacts_v2/ so it does
not clobber the production model. Adds richer evaluation."""
from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "통합_시험접수_현황.csv"
ART = Path(__file__).resolve().parent / "artifacts_v2"
ART.mkdir(parents=True, exist_ok=True)

CAT_COLS = ["사업구분명", "단위사업중분류명", "단위사업소분류명", "요일", "월", "분기"]
NUM_COLS = ["연도", "월일", "연중일", "월총접수량", "사업구분_월접수량"]

MIN_YEAR = 2016
HOLDOUT_MONTHS = 12


def main() -> None:
    print("[1] load")
    df = pd.read_csv(DATA, encoding="utf-8-sig", dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df["접수일자"] = pd.to_datetime(df["접수일자"], errors="coerce")
    df["처리일수"] = pd.to_numeric(df["처리일수"], errors="coerce")

    mask = (
        df["처리일수"].notna()
        & df["접수일자"].notna()
        & (df["처리일수"] >= 0)
        & (df["처리일수"] <= 365)
        & (df["접수일자"].dt.year >= MIN_YEAR)
    )
    work = df.loc[mask].copy()
    print(f"  rows used (>= {MIN_YEAR}): {len(work):,}")
    print(f"  date range: {work['접수일자'].min().date()} ~ {work['접수일자'].max().date()}")

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

    cut = work["접수일자"].max() - pd.DateOffset(months=HOLDOUT_MONTHS)
    tr = (work["접수일자"] <= cut).values
    te = ~tr
    print(f"  train: {tr.sum():,}  test: {te.sum():,}")
    print(f"  train 평균 처리일수={y_raw[tr].mean():.2f}일, test 평균={y_raw[te].mean():.2f}일")

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
        num_threads=8,
        force_col_wise=True,
    )
    dtr = lgb.Dataset(X[tr], y[tr], categorical_feature=CAT_COLS)
    dte = lgb.Dataset(X[te], y[te], categorical_feature=CAT_COLS, reference=dtr)
    model = lgb.train(
        params,
        dtr,
        num_boost_round=1000,
        valid_sets=[dtr, dte],
        valid_names=["train", "valid"],
        callbacks=[lgb.early_stopping(40), lgb.log_evaluation(100)],
    )

    pred = np.clip(np.expm1(model.predict(X[te], num_iteration=model.best_iteration)), 0, 365)
    y_te = y_raw[te]
    err = pred - y_te
    abs_err = np.abs(err)
    mae = float(abs_err.mean())
    medae = float(np.median(abs_err))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    bias = float(err.mean())
    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((y_te - y_te.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot

    print(f"  best_iter={model.best_iteration}")
    print(f"  MAE={mae:.2f}  MedianAE={medae:.2f}  RMSE={rmse:.2f}  bias(pred-actual)={bias:+.2f}  R2={r2:.3f}")
    print("  hit rate:")
    for k in [1, 3, 5, 7, 14, 30]:
        print(f"    |err|<= {k:>2}일 : {(abs_err<=k).mean()*100:5.1f}%")

    # baseline: predict train median
    base = float(np.median(y_raw[tr]))
    base_err = np.abs(base - y_te)
    print(f"  baseline(median={base:.0f}일) MAE={base_err.mean():.2f}, ±7일 {(base_err<=7).mean()*100:.1f}%")

    # save model
    model.save_model(str(ART / "lgbm_proc_days.txt"))

    # save category maps
    with open(ART / "category_maps.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "cat": CAT_COLS,
                "num": NUM_COLS,
                "categories": cat_maps,
                "best_iteration": model.best_iteration,
                "test_mae": mae,
                "test_medae": medae,
                "test_rmse": rmse,
                "test_bias": bias,
                "test_r2": r2,
                "min_year": MIN_YEAR,
                "holdout_months": HOLDOUT_MONTHS,
                "n_train": int(tr.sum()),
                "n_test": int(te.sum()),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    # save predictions for downstream analysis
    out = work.loc[te, ["접수일자", "사업구분명", "단위사업중분류명", "단위사업소분류명"]].copy()
    out["실측_처리일수"] = y_te
    out["예측_처리일수"] = pred
    out["오차"] = pred - y_te
    out.to_csv(ART / "test_predictions.csv", index=False, encoding="utf-8-sig")

    # per-task summary
    per = (
        out.groupby("단위사업소분류명")
        .apply(
            lambda g: pd.Series(
                {
                    "n": len(g),
                    "실측_평균": g["실측_처리일수"].mean(),
                    "예측_평균": g["예측_처리일수"].mean(),
                    "MAE": g["오차"].abs().mean(),
                    "MedianAE": g["오차"].abs().median(),
                    "±7일_적중률(%)": (g["오차"].abs() <= 7).mean() * 100,
                    "±14일_적중률(%)": (g["오차"].abs() <= 14).mean() * 100,
                }
            )
        )
        .round(2)
        .sort_values("n", ascending=False)
    )
    per.to_csv(ART / "performance_by_task.csv", encoding="utf-8-sig")
    print(f"\n  saved: {ART}")


if __name__ == "__main__":
    main()
