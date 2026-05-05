"""FastAPI app — REST API + static frontend."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import stats as stats_mod
from .agent import answer as agent_answer
from .db import Application, Sample, get_session, init_db
from .predictor import ProcDaysPredictor, add_business_days, get_predictor
from .recommender import recommend as do_recommend

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"

app = FastAPI(title="KTL TestMate API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                    allow_headers=["*"])


@app.on_event("startup")
def _startup() -> None:
    init_db()
    get_predictor()  # warm up


# ------------------------------------------------------------ schemas
class PredictRequest(BaseModel):
    biz: str
    mid: str
    sub: str
    receive_on: date


class RecommendRequest(BaseModel):
    biz: str
    mid: str
    sub: str
    earliest: date
    latest: Optional[date] = None
    deadline: Optional[date] = None
    priority: str = "fast"
    n: int = 5


class ChatRequest(BaseModel):
    message: str


class SampleIn(BaseModel):
    name: Optional[str] = None
    maker: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    amount: Optional[int] = 1
    memo: Optional[str] = None


class ApplicationIn(BaseModel):
    biz: str
    category: str
    subcategory: str
    sample_name: Optional[str] = None
    company: Optional[str] = None
    business_no: Optional[str] = None
    address: Optional[str] = None
    ceo: Optional[str] = None
    applicant_name: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    fax: Optional[str] = None
    payment: Optional[str] = None
    report: Optional[str] = None
    return_method: Optional[str] = None
    return_address: Optional[str] = None
    notes: Optional[str] = None
    samples: list[SampleIn] = Field(default_factory=list)


class ApplicationPatch(BaseModel):
    """Partial update — every field is optional. Admin DB editor uses this."""
    status: Optional[str] = None
    biz: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    sample_name: Optional[str] = None
    received_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    predicted_days: Optional[int] = None
    predicted_complete_at: Optional[datetime] = None
    company: Optional[str] = None
    business_no: Optional[str] = None
    address: Optional[str] = None
    ceo: Optional[str] = None
    applicant_name: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    fax: Optional[str] = None
    payment: Optional[str] = None
    report: Optional[str] = None
    return_method: Optional[str] = None
    return_address: Optional[str] = None
    notes: Optional[str] = None
    samples: Optional[list[SampleIn]] = None


# ------------------------------------------------------------ helpers
def _to_dict(a: Application) -> dict:
    return {
        "id": a.id,
        "status": a.status,
        "biz": a.biz,
        "category": a.category,
        "subcategory": a.subcategory,
        "sample_name": a.sample_name,
        "received_at": a.received_at.isoformat() if a.received_at else None,
        "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        "predicted_days": a.predicted_days,
        "predicted_complete_at": a.predicted_complete_at.isoformat() if a.predicted_complete_at else None,
        "applicant": {
            "company": a.company, "business_no": a.business_no,
            "address": a.address, "ceo": a.ceo,
            "name": a.applicant_name, "phone": a.phone,
            "mobile": a.mobile, "email": a.email, "fax": a.fax,
        },
        "request": {
            "payment": a.payment, "report": a.report,
            "return_method": a.return_method,
            "return_address": a.return_address,
            "notes": a.notes,
        },
        "samples": [{"name": s.name, "maker": s.maker, "model": s.model,
                       "serial": s.serial, "amount": s.amount, "memo": s.memo}
                       for s in a.samples],
    }


# ------------------------------------------------------------ catalog
@app.get("/api/catalog")
def catalog(predictor: ProcDaysPredictor = Depends(get_predictor)):
    """biz → mid → [subs] hierarchy."""
    return stats_mod.category_tree(predictor)


# ------------------------------------------------------------ predictions
@app.post("/api/predict")
def predict(req: PredictRequest, predictor: ProcDaysPredictor = Depends(get_predictor)):
    return predictor.predict(biz=req.biz, mid=req.mid, sub=req.sub,
                              received_on=req.receive_on)


@app.post("/api/explain")
def explain(req: PredictRequest, predictor: ProcDaysPredictor = Depends(get_predictor)):
    return predictor.explain(biz=req.biz, mid=req.mid, sub=req.sub,
                              received_on=req.receive_on)


@app.post("/api/recommend")
def recommend_dates(req: RecommendRequest, predictor: ProcDaysPredictor = Depends(get_predictor)):
    return do_recommend(predictor, biz=req.biz, mid=req.mid, sub=req.sub,
                          earliest=req.earliest, latest=req.latest,
                          deadline=req.deadline, priority=req.priority, n=req.n)


@app.post("/api/chat")
def chat(req: ChatRequest, predictor: ProcDaysPredictor = Depends(get_predictor)):
    return agent_answer(req.message, predictor)


# ------------------------------------------------------------ stats
@app.get("/api/stats/biz")
def stats_biz(predictor: ProcDaysPredictor = Depends(get_predictor)):
    return stats_mod.biz_avg_days(predictor)


@app.get("/api/stats/mid")
def stats_mid(biz: Optional[str] = None,
              predictor: ProcDaysPredictor = Depends(get_predictor)):
    return stats_mod.mid_avg_days(predictor, biz)


@app.get("/api/stats/sub")
def stats_sub(biz: Optional[str] = None, mid: Optional[str] = None,
              predictor: ProcDaysPredictor = Depends(get_predictor)):
    return stats_mod.sub_avg_days(predictor, biz, mid)


@app.get("/api/stats/monthly")
def stats_monthly():
    return stats_mod.monthly_volume()


@app.get("/api/stats/yearly")
def stats_yearly():
    return stats_mod.yearly_volume()


@app.get("/api/stats/seasonality")
def stats_seasonality():
    return stats_mod.congestion_heat()


# ------------------------------------------------------------ applications CRUD
@app.get("/api/applications")
def list_apps(status: Optional[str] = None, db: Session = Depends(get_session)):
    q = db.query(Application).order_by(Application.received_at.desc())
    if status:
        q = q.filter(Application.status == status)
    return [_to_dict(a) for a in q.all()]


@app.get("/api/applications/{app_id}")
def get_app(app_id: int, db: Session = Depends(get_session)):
    a = db.get(Application, app_id)
    if not a:
        raise HTTPException(404, "not found")
    return _to_dict(a)


@app.post("/api/applications")
def create_app(payload: ApplicationIn, db: Session = Depends(get_session),
                predictor: ProcDaysPredictor = Depends(get_predictor)):
    today = date.today()
    pred = predictor.predict(biz=payload.biz, mid=payload.category,
                              sub=payload.subcategory, received_on=today)
    a = Application(
        status="pending",
        biz=payload.biz,
        category=payload.category,
        subcategory=payload.subcategory,
        sample_name=payload.sample_name,
        received_at=datetime.utcnow(),
        predicted_days=int(round(pred["predicted_days"])),
        predicted_complete_at=datetime.fromisoformat(pred["predicted_complete_at"]),
        company=payload.company, business_no=payload.business_no,
        address=payload.address, ceo=payload.ceo,
        applicant_name=payload.applicant_name, phone=payload.phone,
        mobile=payload.mobile, email=payload.email, fax=payload.fax,
        payment=payload.payment, report=payload.report,
        return_method=payload.return_method, return_address=payload.return_address,
        notes=payload.notes,
    )
    for s in payload.samples:
        a.samples.append(Sample(**s.model_dump()))
    db.add(a); db.commit(); db.refresh(a)
    res = _to_dict(a)
    res["prediction"] = pred
    return res


@app.post("/api/applications/{app_id}/complete")
def complete_app(app_id: int, db: Session = Depends(get_session)):
    a = db.get(Application, app_id)
    if not a:
        raise HTTPException(404, "not found")
    a.status = "completed"
    a.completed_at = datetime.utcnow()
    db.commit(); db.refresh(a)
    return _to_dict(a)


@app.delete("/api/applications/{app_id}")
def delete_app(app_id: int, db: Session = Depends(get_session)):
    a = db.get(Application, app_id)
    if not a:
        raise HTTPException(404, "not found")
    db.delete(a); db.commit()
    return {"ok": True}


@app.patch("/api/applications/{app_id}")
def patch_app(app_id: int, payload: ApplicationPatch,
               db: Session = Depends(get_session)):
    """Admin DB editor — update any column directly."""
    a = db.get(Application, app_id)
    if not a:
        raise HTTPException(404, "not found")
    data = payload.model_dump(exclude_unset=True)
    samples = data.pop("samples", None)
    for k, v in data.items():
        setattr(a, k, v)
    if samples is not None:
        a.samples.clear()
        for s in samples:
            a.samples.append(Sample(**s))
    db.commit(); db.refresh(a)
    return _to_dict(a)


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_session)):
    """Quick admin counters."""
    today = date.today()
    apps = db.query(Application).all()
    today_n = sum(1 for a in apps if a.received_at and a.received_at.date() == today)
    month_n = sum(1 for a in apps if a.received_at
                   and a.received_at.year == today.year
                   and a.received_at.month == today.month)
    pending_n = sum(1 for a in apps if a.status == "pending")
    completed_n = sum(1 for a in apps if a.status == "completed")
    return {"today": today_n, "month": month_n,
             "pending": pending_n, "completed": completed_n,
             "total": len(apps)}


# ------------------------------------------------------------ static
if STATIC.exists():
    app.mount("/admin", StaticFiles(directory=str(STATIC / "admin"), html=True), name="admin")
    app.mount("/applicant", StaticFiles(directory=str(STATIC / "applicant"), html=True), name="applicant")
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/")
def index():
    return RedirectResponse("/static/index.html")
