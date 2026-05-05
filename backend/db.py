"""SQLAlchemy DB layer (SQLite)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import (Column, DateTime, ForeignKey, Integer, String, Text,
                        create_engine)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DB_PATH = Path(__file__).resolve().parent / "data" / "ktl.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
Base = declarative_base()


class Application(Base):
    """One test application (시험 신청)."""

    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(20), nullable=False, default="pending")  # pending / completed
    biz = Column(String(120))            # 사업구분명
    category = Column(String(120))       # 단위사업중분류명
    subcategory = Column(String(200))    # 단위사업소분류명
    sample_name = Column(String(200))

    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime)

    predicted_days = Column(Integer)
    predicted_complete_at = Column(DateTime)

    # applicant info
    company = Column(String(200))
    business_no = Column(String(50))
    address = Column(Text)
    ceo = Column(String(80))
    applicant_name = Column(String(80))
    phone = Column(String(50))
    mobile = Column(String(50))
    email = Column(String(120))
    fax = Column(String(50))

    # request info
    payment = Column(String(40))
    report = Column(String(120))
    return_method = Column(String(40))
    return_address = Column(Text)
    notes = Column(Text)

    samples = relationship("Sample", back_populates="application", cascade="all, delete-orphan")


class Sample(Base):
    __tablename__ = "samples"
    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(Integer, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200))
    maker = Column(String(200))
    model = Column(String(200))
    serial = Column(String(200))
    amount = Column(Integer, default=1)
    memo = Column(Text)

    application = relationship("Application", back_populates="samples")


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
