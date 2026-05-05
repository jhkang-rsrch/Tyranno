"""Seed DB with the demo applications previously hardcoded in the frontend."""
from __future__ import annotations

from datetime import datetime, timedelta

from .db import Application, Sample, SessionLocal, init_db
from .predictor import get_predictor

DEMO = [
    {
        "biz": "교정", "category": "KOLAS교정", "subcategory": "압력",
        "sample_name": "디지털 압력계 A-102",
        "received_at": datetime.utcnow() - timedelta(hours=4),
        "company": "성진계측", "business_no": "123-45-67890",
        "address": "경기도 안산시 상록구 해안로 723", "ceo": "김성진",
        "applicant_name": "박민수", "phone": "031-500-0123",
        "mobile": "010-4567-8910", "email": "minsu@sample.co.kr",
        "fax": "031-500-0371", "payment": "웹결제",
        "report": "국문 성적서, KOLAS", "return_method": "택배회수",
        "return_address": "경기도 안산시 상록구 해안로 723",
        "notes": "성적서에 교정주기 표시 요청",
        "status": "pending",
    },
    {
        "biz": "안전인증", "category": "전기용품안전인증(KC)시험",
        "subcategory": "전기안전시험", "sample_name": "어댑터 KC-240",
        "received_at": datetime.utcnow() - timedelta(hours=2),
        "company": "한빛전자", "business_no": "211-88-10452",
        "address": "서울특별시 금천구 가산디지털1로 45",
        "ceo": "이정훈", "applicant_name": "최유나",
        "phone": "02-3440-1200", "mobile": "010-6621-3345",
        "email": "yuna@hanbit.example", "fax": "02-3440-1201",
        "payment": "방문결제", "report": "국문 성적서, 일반",
        "return_method": "방문회수",
        "return_address": "서울특별시 금천구 가산디지털1로 45",
        "notes": "미승인 부품 포함 여부 확인 필요",
        "status": "pending",
    },
    {
        "biz": "기업지원", "category": "재료시험", "subcategory": "역학시험",
        "sample_name": "알루미늄 시편 AL-7",
        "received_at": datetime.utcnow() - timedelta(days=4),
        "completed_at": datetime.utcnow() - timedelta(days=1),
        "company": "대원소재", "business_no": "317-07-22117",
        "address": "충청북도 청주시 흥덕구 공단로 25",
        "ceo": "문정우", "applicant_name": "서하린",
        "phone": "043-210-7788", "mobile": "010-7788-4412",
        "email": "harin@dwmaterial.example", "fax": "043-210-7789",
        "payment": "웹결제", "report": "국문 성적서",
        "return_method": "택배회수",
        "return_address": "충청북도 청주시 흥덕구 공단로 25",
        "notes": "파단면 사진 포함",
        "status": "completed",
    },
]


def main() -> None:
    init_db()
    pred = get_predictor()
    db = SessionLocal()
    try:
        if db.query(Application).count() > 0:
            print("DB already seeded; skipping.")
            return
        for d in DEMO:
            recv = d["received_at"].date()
            p = pred.predict(biz=d["biz"], mid=d["category"], sub=d["subcategory"],
                              received_on=recv)
            a = Application(
                **d,
                predicted_days=int(round(p["predicted_days"])),
                predicted_complete_at=datetime.fromisoformat(p["predicted_complete_at"]),
            )
            db.add(a)
        db.commit()
        print(f"seeded {len(DEMO)} applications")
    finally:
        db.close()


if __name__ == "__main__":
    main()
