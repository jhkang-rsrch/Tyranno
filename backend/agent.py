"""Lightweight rule-based 'agent': extract structured fields from a Korean
natural-language question, call the predictor/recommender, and produce a
templated NL response. No external LLM required."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional

from .predictor import ProcDaysPredictor
from .recommender import recommend

_PRIORITY_PATTERNS = [
    (re.compile(r"빨리|빠르게|빠른|급하|최단|단축"), "fast"),
    (re.compile(r"안정|편차|변동성|믿을"), "stable"),
    (re.compile(r"혼잡|밀리|몰리|피하"), "avoid_congestion"),
    (re.compile(r"맞춰|마감|기한|까지"), "meet_deadline"),
]

_MONTH_PAT = re.compile(r"(\d{1,2})\s*월\s*(?:(말|초|중순|중|첫째|둘째|셋째|넷째|마지막)\s*주?)?")
_DATE_PAT = re.compile(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})")
_REL_PAT = re.compile(r"(다음달|이번달|이달|다음주|이번주|오늘|내일|모레)")


def _parse_dates(text: str, today: date) -> tuple[Optional[date], Optional[date]]:
    """Return (target_receive, deadline)."""
    receive: Optional[date] = None
    deadline: Optional[date] = None

    for m in _DATE_PAT.finditer(text):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dt = date(y, mo, d)
        except ValueError:
            continue
        if receive is None:
            receive = dt
        else:
            deadline = dt

    # 'X월 말까지' → deadline = end of month X
    for m in _MONTH_PAT.finditer(text):
        mo = int(m.group(1))
        qual = m.group(2) or ""
        y = today.year if mo >= today.month else today.year + 1
        if "말" in qual or "마지막" in qual:
            nxt = date(y, mo, 28) + timedelta(days=4)
            day = (nxt - timedelta(days=nxt.day)).day
        elif "초" in qual or "첫째" in qual:
            day = 3
        elif "둘째" in qual:
            day = 10
        elif "셋째" in qual or "중순" in qual or qual == "중":
            day = 17
        elif "넷째" in qual:
            day = 24
        else:
            day = 15
        dt = date(y, mo, day)
        if "까지" in text[m.end():m.end() + 4] or "전까지" in text[m.end():m.end() + 6]:
            deadline = dt
        elif receive is None:
            receive = dt

    for m in _REL_PAT.finditer(text):
        kw = m.group(1)
        if kw in ("오늘",):
            dt = today
        elif kw == "내일":
            dt = today + timedelta(days=1)
        elif kw == "모레":
            dt = today + timedelta(days=2)
        elif kw == "이번주":
            dt = today + timedelta(days=(0 - today.weekday()) % 7)
        elif kw == "다음주":
            dt = today + timedelta(days=(0 - today.weekday()) % 7 + 7)
        elif kw in ("이번달", "이달"):
            dt = today.replace(day=15)
        elif kw == "다음달":
            mo = today.month + 1
            y = today.year + (mo - 1) // 12
            mo = (mo - 1) % 12 + 1
            dt = date(y, mo, 15)
        else:
            continue
        if receive is None:
            receive = dt
    return receive, deadline


def _detect_priority(text: str) -> str:
    for pat, key in _PRIORITY_PATTERNS:
        if pat.search(text):
            return key
    return "fast"


def _resolve_category(text: str, pred: ProcDaysPredictor) -> Optional[tuple[str, str, str]]:
    """Try to find (biz, mid, sub) triple by substring in text. Subcategory
    has priority since it's more specific."""
    sub_df = pred.sub_stats
    # match longest sub label first
    best = None
    for _, r in sub_df.sort_values("count", ascending=False).iterrows():
        sub = str(r["단위사업소분류명"])
        if sub and sub in text:
            return (str(r["사업구분명"]), str(r["단위사업중분류명"]), sub)
    mid_df = pred.mid_stats
    for _, r in mid_df.sort_values("count", ascending=False).iterrows():
        mid = str(r["단위사업중분류명"])
        if mid and mid in text:
            top = sub_df[sub_df["단위사업중분류명"] == mid].sort_values("count", ascending=False)
            if len(top):
                top0 = top.iloc[0]
                return (str(top0["사업구분명"]), mid, str(top0["단위사업소분류명"]))
    biz_df = pred.biz_stats
    for _, r in biz_df.sort_values("count", ascending=False).iterrows():
        biz = str(r["사업구분명"])
        if biz and biz in text:
            top = sub_df[sub_df["사업구분명"] == biz].sort_values("count", ascending=False)
            if len(top):
                top0 = top.iloc[0]
                return (biz, str(top0["단위사업중분류명"]), str(top0["단위사업소분류명"]))
    return best


def answer(text: str, pred: ProcDaysPredictor, today: Optional[date] = None) -> dict:
    today = today or date.today()
    receive, deadline = _parse_dates(text, today)
    priority = _detect_priority(text)
    triple = _resolve_category(text, pred)

    if triple is None:
        return {
            "ok": False,
            "message": "시험 종목을 인식하지 못했습니다. 사업구분/중분류/소분류 명칭 중 하나 이상을 포함해 다시 질문해 주세요.",
            "extracted": {"receive_on": receive.isoformat() if receive else None,
                            "deadline": deadline.isoformat() if deadline else None,
                            "priority": priority},
        }
    biz, mid, sub = triple
    base_receive = receive or today

    point = pred.predict(biz=biz, mid=mid, sub=sub, received_on=base_receive)

    rec_window_end = (deadline or (base_receive + timedelta(days=14)))
    recs = recommend(pred, biz=biz, mid=mid, sub=sub,
                      earliest=base_receive, latest=base_receive + timedelta(days=14),
                      deadline=deadline, priority=priority, n=3)

    parts = []
    parts.append(
        f"[{biz} > {mid} > {sub}] {base_receive.isoformat()} 접수 기준 "
        f"예상 소요 {point['predicted_days']}일 (범위 {point['low_days']}~{point['high_days']}일, "
        f"신뢰도 {int(point['confidence']*100)}%)."
    )
    parts.append(
        f"예상 완료일은 {point['predicted_complete_at']}이며, 해당 월 혼잡도는 '{point['congestion']}' 입니다."
    )
    if deadline:
        complete = date.fromisoformat(point["predicted_complete_at"])
        if complete <= deadline:
            parts.append(f"목표 완료일 {deadline.isoformat()} 이내 처리 가능성이 높습니다.")
        else:
            parts.append(f"현재 조건으로는 목표 완료일 {deadline.isoformat()}을 맞추기 어려울 수 있어 더 이른 신청을 권장합니다.")
    if recs:
        top = recs[0]
        parts.append(
            f"추천 신청일은 {top['receive_on']} (예상 완료 {top['predicted_complete_at']}, "
            f"우선순위 기준 '{priority}')."
        )

    return {
        "ok": True,
        "message": " ".join(parts),
        "extracted": {
            "biz": biz, "mid": mid, "sub": sub,
            "receive_on": base_receive.isoformat(),
            "deadline": deadline.isoformat() if deadline else None,
            "priority": priority,
        },
        "prediction": point,
        "recommendations": recs,
    }
