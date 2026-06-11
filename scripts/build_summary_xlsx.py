"""Compile all jinju model analysis into a single xlsx report."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/data1/home/wngjs9155/workspace/jinju")
OUT = ROOT / "models" / "성능분석_종합.xlsx"

# ---------- 1. 데이터 로드 ----------
df = pd.read_csv(ROOT / "data/통합_시험접수_현황.csv", encoding="utf-8-sig", dtype=str)
df["처리일수"] = pd.to_numeric(df["처리일수"], errors="coerce")
df["접수일자"] = pd.to_datetime(df["접수일자"], errors="coerce")
mask = df["처리일수"].notna() & df["접수일자"].notna() & (df["처리일수"] >= 0) & (df["처리일수"] <= 365)
df = df.loc[mask].copy()
df["연도"] = df["접수일자"].dt.year

# 기존 모델 산출물
tp_v1 = pd.read_csv(ROOT / "models/02_proc_days_regression/csv/test_predictions.csv")
tp_v2 = pd.read_csv(ROOT / "backend/artifacts_v2/test_predictions.csv")
fc = pd.read_csv(ROOT / "models/01_forecast/csv/summary_metrics.csv")
cox = json.load(open(ROOT / "models/03_survival/csv/cox_meta.json"))
perf_biz_v1 = pd.read_csv(ROOT / "models/02_proc_days_regression/csv/performance_by_biz.csv")
perf_task_v2 = pd.read_csv(ROOT / "backend/artifacts_v2/performance_by_task.csv")
meta_v2 = json.load(open(ROOT / "backend/artifacts_v2/category_maps.json"))


def metrics(tp: pd.DataFrame) -> dict:
    y, p = tp["실측_처리일수"].values, tp["예측_처리일수"].values
    err = p - y
    abs_err = np.abs(err)
    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return {
        "n": len(tp),
        "MAE": float(abs_err.mean()),
        "MedianAE": float(np.median(abs_err)),
        "RMSE": float(np.sqrt((err ** 2).mean())),
        "편향(예측-실측)": float(err.mean()),
        "R2": 1 - ss_res / ss_tot,
        "±1일 적중률(%)": float((abs_err <= 1).mean() * 100),
        "±3일 적중률(%)": float((abs_err <= 3).mean() * 100),
        "±5일 적중률(%)": float((abs_err <= 5).mean() * 100),
        "±7일 적중률(%)": float((abs_err <= 7).mean() * 100),
        "±14일 적중률(%)": float((abs_err <= 14).mean() * 100),
        "±30일 적중률(%)": float((abs_err <= 30).mean() * 100),
    }


m_v1 = metrics(tp_v1)
m_v2 = metrics(tp_v2)

# baseline (test 중앙값으로 일정 예측)
y_test = tp_v1["실측_처리일수"].values
base_pred = float(np.median(y_test))
base_err = np.abs(y_test - base_pred)
m_base = {
    "n": len(y_test),
    "MAE": float(base_err.mean()),
    "MedianAE": float(np.median(base_err)),
    "RMSE": float(np.sqrt((base_err ** 2).mean())),
    "편향(예측-실측)": float((base_pred - y_test).mean()),
    "R2": 0.0,
    "±1일 적중률(%)": float((base_err <= 1).mean() * 100),
    "±3일 적중률(%)": float((base_err <= 3).mean() * 100),
    "±5일 적중률(%)": float((base_err <= 5).mean() * 100),
    "±7일 적중률(%)": float((base_err <= 7).mean() * 100),
    "±14일 적중률(%)": float((base_err <= 14).mean() * 100),
    "±30일 적중률(%)": float((base_err <= 30).mean() * 100),
}

# ---------- 시트 1. 핵심 요약 ----------
summary_rows = [
    ["프로젝트", "/data1/home/wngjs9155/workspace/jinju (GitHub: jhkang-rsrch/Tyranno)"],
    ["서빙 모델", "LightGBM 회귀 (외부 LLM 사용 안 함)"],
    ["기타 분석 모델", "SARIMA/Prophet (접수량 예측), Cox/Kaplan-Meier (생존분석)"],
    ["데이터 기간", f"{df['접수일자'].min().date()} ~ {df['접수일자'].max().date()} (N={len(df):,})"],
    ["검증(test) 기간", "2022-03-01 ~ 2023-02-28 (n=20,287)"],
    ["test 평균 처리일수", f"{y_test.mean():.2f}일"],
    ["test 중앙값", f"{np.median(y_test):.0f}일"],
    ["", ""],
    ["■ LightGBM v1 (전체기간 학습) MAE", f"{m_v1['MAE']:.2f}일, ±7일 적중률 {m_v1['±7일 적중률(%)']:.1f}%, 편향 {m_v1['편향(예측-실측)']:+.2f}일"],
    ["■ LightGBM v2 (2016+만 학습) MAE", f"{m_v2['MAE']:.2f}일, ±7일 적중률 {m_v2['±7일 적중률(%)']:.1f}%, 편향 {m_v2['편향(예측-실측)']:+.2f}일"],
    ["■ baseline (test 중앙값=16일 상수)", f"MAE {m_base['MAE']:.2f}일, ±7일 {m_base['±7일 적중률(%)']:.1f}%"],
    ["", ""],
    ["결론 1", "2016년 이전 데이터를 제거해도 거의 변화 없음 (MAE 27.20 → 27.30)"],
    ["결론 2", "체계적 -20일 과소예측 편향이 양 모델 공통 — 롱테일(사후관리 100일+) 흡수 실패"],
    ["결론 3", "태스크별 격차 극심: 짧은 시험은 A등급(±7일 80%+), 사후관리는 F등급(±7일 10%)"],
    ["결론 4", "통합 단일 회귀의 본질적 한계. 태스크 분리 + 분위수 회귀 필요"],
]
df_summary = pd.DataFrame(summary_rows, columns=["항목", "내용"])

# ---------- 시트 2. 모델 성능 비교 ----------
df_compare = pd.DataFrame([m_base, m_v1, m_v2], index=["baseline(중앙값=16)", "LightGBM v1 (전체기간)", "LightGBM v2 (2016+만)"])
df_compare = df_compare.round(3).reset_index().rename(columns={"index": "모델"})

# ---------- 시트 3. test 처리일수 분포 ----------
y_all = df["처리일수"]
quantiles = [0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]
dist_rows = [
    ["전체 N", len(y_all)],
    ["평균", y_all.mean()],
    ["중앙값", y_all.median()],
    ["표준편차", y_all.std()],
    ["min", y_all.min()],
    ["max", y_all.max()],
] + [[f"q{int(q*100):02d}", y_all.quantile(q)] for q in quantiles]
df_dist = pd.DataFrame(dist_rows, columns=["통계", "값(일)"]).round(2)

# test 분포
y_test_series = pd.Series(y_test)
dist_test = [
    ["test N", len(y_test_series)],
    ["test 평균", y_test_series.mean()],
    ["test 중앙값", y_test_series.median()],
    ["test 표준편차", y_test_series.std()],
] + [[f"test q{int(q*100):02d}", y_test_series.quantile(q)] for q in quantiles]
df_dist_test = pd.DataFrame(dist_test, columns=["통계", "값(일)"]).round(2)

# ---------- 시트 4. 연도별 처리일수 추세 ----------
year_trend = df.groupby("연도")["처리일수"].agg(["count", "mean", "median", "std"]).round(2)
year_trend.columns = ["건수", "평균(일)", "중앙값(일)", "표준편차(일)"]
year_trend = year_trend.reset_index()

# ---------- 시트 5. 사업구분별 (v1) ----------
perf_biz_v1["MAE/실측평균(%)"] = (perf_biz_v1["MAE"] / perf_biz_v1["실측_평균"] * 100).round(1)
perf_biz_v1["편향(예측-실측)"] = (perf_biz_v1["예측_평균"] - perf_biz_v1["실측_평균"]).round(2)
perf_biz_v1 = perf_biz_v1.sort_values("n", ascending=False)

# ---------- 시트 6. 태스크별 (v2) ----------
# 등급 부여
def grade(r):
    if r["±7일_적중률(%)"] >= 75 and r["MAE"] <= 10:
        return "A (양호)"
    if r["±7일_적중률(%)"] >= 50:
        return "B"
    if r["±7일_적중률(%)"] >= 30:
        return "C"
    if r["±7일_적중률(%)"] >= 20:
        return "D"
    return "F (사용 불가)"


perf_task_v2["등급"] = perf_task_v2.apply(grade, axis=1)
perf_task_v2 = perf_task_v2.sort_values(["등급", "n"], ascending=[True, False])

# ---------- 시트 7. 시계열·생존분석 ----------
fc_clean = fc.copy()
cox_df = pd.DataFrame([
    ["샘플 수", cox["n_sample"]],
    ["이벤트 수", cox["n_events"]],
    ["Concordance Index", round(cox["concordance_index"], 4)],
    ["AIC (partial)", round(cox["AIC_partial"], 2)],
    ["Log-likelihood", round(cox["log_likelihood"], 2)],
    ["해석", "C-index 0.5=랜덤 / 0.7+=양호 / 0.666은 보통 수준"],
], columns=["항목", "값"])

# ---------- 시트 8. 권장 개선 방향 ----------
reco_rows = [
    ["1", "태스크 분리 학습", "단위사업소분류명 기준으로 '일반시험' vs '사후관리' 분리. 사후관리는 별도 모델 또는 별도 트랙."],
    ["2", "분위수 회귀(Quantile Regression)", "점추정 대신 q50/q90 제공 → '15~80일 구간' 형태. 롱테일 태스크에도 의미 있음."],
    ["3", "체계적 편향 보정", "전 모델 -20일 과소예측. log1p+clip(365) 조합 재설계 또는 Tweedie/Gamma 분포 회귀 검토."],
    ["4", "태스크별 등급 공개", "A등급 태스크만 자동 예측, F등급은 '평균 120일+, 예측 불확실' 형태로 운영."],
    ["5", "feature 추가", "현재 시간 + 사업구분 카테고리만 사용. 신청 항목 수/시험 종목/장비 가용성 등 도메인 변수 보강."],
    ["6", "Cox PH 가정 검정", "C-index 0.666 보고 전에 PH 가정·calibration 점검 필요. events/n=98% 이라 사실상 회귀."],
    ["7", "Prophet 재검토", "MAPE 72% — clip/이상치 처리 누락 의심. 사용한다면 SARIMA로 일원화 권장."],
]
df_reco = pd.DataFrame(reco_rows, columns=["우선순위", "조치", "상세"])

# ---------- xlsx 저장 ----------
with pd.ExcelWriter(OUT, engine="openpyxl") as xw:
    df_summary.to_excel(xw, sheet_name="0. 핵심요약", index=False)
    df_compare.to_excel(xw, sheet_name="1. 모델성능비교", index=False)
    df_dist.to_excel(xw, sheet_name="2. 처리일수분포_전체", index=False)
    df_dist_test.to_excel(xw, sheet_name="2. 처리일수분포_test", index=False)
    year_trend.to_excel(xw, sheet_name="3. 연도별추세", index=False)
    perf_biz_v1.to_excel(xw, sheet_name="4. 사업구분별_v1", index=False)
    perf_task_v2.to_excel(xw, sheet_name="5. 태스크별_v2", index=False)
    fc_clean.to_excel(xw, sheet_name="6. 시계열_forecast", index=False)
    cox_df.to_excel(xw, sheet_name="7. 생존분석_cox", index=False)
    df_reco.to_excel(xw, sheet_name="8. 개선권장사항", index=False)

    # 열 너비 자동 조정
    for sh in xw.sheets.values():
        for col in sh.columns:
            try:
                max_len = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                sh.column_dimensions[col[0].column_letter].width = min(max(max_len * 1.2 + 2, 12), 60)
            except Exception:
                pass

print(f"saved: {OUT}")
