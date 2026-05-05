"""Recommend best receipt date within a window, considering predicted days
and goal completion deadline."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .predictor import ProcDaysPredictor, add_business_days


def recommend(
    pred: ProcDaysPredictor,
    *,
    biz: str,
    mid: str,
    sub: str,
    earliest: date,
    latest: Optional[date] = None,
    deadline: Optional[date] = None,
    priority: str = "fast",  # fast / stable / avoid_congestion / meet_deadline
    n: int = 5,
) -> list[dict]:
    if latest is None:
        latest = earliest + timedelta(days=21)
    candidates: list[dict] = []
    d = earliest
    while d <= latest:
        if d.weekday() < 5:
            r = pred.predict(biz=biz, mid=mid, sub=sub, received_on=d)
            r["receive_on"] = d.isoformat()
            r["meets_deadline"] = (
                deadline is None or date.fromisoformat(r["predicted_complete_at"]) <= deadline
            )
            r["score"] = _score(r, priority, deadline)
            candidates.append(r)
        d += timedelta(days=1)

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:n]


def _score(r: dict, priority: str, deadline: Optional[date]) -> float:
    days = r["predicted_days"]
    span = max(1.0, r["high_days"] - r["low_days"])
    cong = {"낮음": 1.0, "보통": 0.6, "높음": 0.3, "매우 높음": 0.1}.get(r["congestion"], 0.5)
    deadline_ok = 1.0 if r["meets_deadline"] else 0.0
    if deadline:
        complete = date.fromisoformat(r["predicted_complete_at"])
        slack = (deadline - complete).days
        deadline_ok = 1.0 if slack >= 0 else 0.0
    fast = 1.0 / (1.0 + days / 10.0)
    stable = 1.0 / (1.0 + span / 5.0)
    if priority == "fast":
        return 0.6 * fast + 0.2 * cong + 0.2 * deadline_ok
    if priority == "stable":
        return 0.5 * stable + 0.2 * cong + 0.3 * deadline_ok
    if priority == "avoid_congestion":
        return 0.6 * cong + 0.2 * fast + 0.2 * deadline_ok
    if priority == "meet_deadline":
        return 0.7 * deadline_ok + 0.2 * fast + 0.1 * stable
    return fast
