# KTL TestMate — backend + frontend

KTL 시험 신청 처리 데이터(`data/통합_시험접수_현황.csv`, 1.4M rows)를 활용한
**AI 처리기간 예측 / 추천 / 자연어 상담** 풀스택 서비스.

```
backend/
├─ train.py              # LightGBM 학습 + 카테고리 매핑/통계 산출
├─ artifacts/            # 학습 산출물 (모델·매핑·집계 csv)
├─ predictor.py          # LightGBM 예측 + SHAP 설명
├─ recommender.py        # 윈도우 내 최적 접수일 추천(점수식)
├─ agent.py              # 자연어 → 정보 추출 → 템플릿형 답변
├─ stats.py              # 관리자 통계 어그리게이션
├─ db.py                 # SQLite + SQLAlchemy ORM
├─ seed.py               # 데모 신청 3건 시드
├─ app.py                # FastAPI (REST + 정적 프런트엔드)
└─ static/
   ├─ index.html         # 랜딩
   ├─ admin/             # 관리자 모드(예측·통계·SHAP·완료처리)
   └─ applicant/         # 신청자 모드(접수·계산·추천·자연어 상담)
```

## 의존성
```bash
/data1/home/wngjs9155/miniconda3/bin/pip install lightgbm shap fastapi 'uvicorn[standard]' sqlalchemy pandas numpy pydantic
```

## 실행 (1회)
```bash
PY=/data1/home/wngjs9155/miniconda3/bin/python
cd /data1/home/wngjs9155/workspace/jinju
$PY backend/train.py     # 모델 학습(약 1~2분, MAE≈27일)
$PY -m backend.seed      # 데모 신청 3건 DB 시드
$PY -m uvicorn backend.app:app --host 0.0.0.0 --port 8765
```

브라우저:
- 랜딩 http://localhost:8765/
- 신청자 http://localhost:8765/applicant/
- 관리자 http://localhost:8765/admin/

## REST API 요약
| Method | Path | 설명 |
|---|---|---|
| GET  | `/api/catalog` | 사업구분→중분류→소분류 트리 |
| POST | `/api/predict` | LightGBM 처리일수·완료일·혼잡도·신뢰도 |
| POST | `/api/explain` | SHAP 기여도 (top features) |
| POST | `/api/recommend` | 우선순위 기반 접수일 추천 N개 |
| POST | `/api/chat` | 자연어 질문 → 추출+예측+답변 |
| GET  | `/api/stats/biz`, `/mid`, `/sub` | 분류별 평균/중앙값/표준편차 |
| GET  | `/api/stats/monthly`, `/yearly`, `/seasonality` | 시계열 통계 |
| GET/POST/DELETE | `/api/applications[/{id}[/complete]]` | 신청 CRUD |
| GET  | `/api/dashboard` | 오늘/이번달/대기/완료 카운터 |

요청 예:
```bash
curl -X POST localhost:8765/api/predict -H 'Content-Type: application/json' \
  -d '{"biz":"교정","mid":"KOLAS교정","sub":"압력","receive_on":"2026-05-05"}'
# {"predicted_days":5.91,"low_days":0.0,"high_days":13.91,"predicted_complete_at":"2026-05-13",...}
```

## AI 구성 요소
1. **처리일수 회귀** — LightGBM (cat: 사업구분/중·소분류/요일/월/분기, num: 연도/일/연중일/월총접수/사업구분별 월접수). target=log1p(처리일수). 시간 기반 split (마지막 12개월 holdout) MAE ≈ 27일·MedianAE ≈ 9일.
2. **불확실성 구간** — 소분류별 std 활용한 80% band + 표본수 기반 신뢰도 점수.
3. **혼잡도** — 월 총접수량을 전체 평균과 비교해 4단계(낮음/보통/높음/매우높음) 등급화.
4. **SHAP** — `TreeExplainer`로 단건 예측에 대한 피처 기여도 시각화 (관리자 사이드바).
5. **추천기** — `(예상소요/안정성/혼잡도/마감충족)` 가중합 점수로 윈도우 내 최적 접수일 N개 선정.
6. **자연어 에이전트** — 정규식 기반 한국어 추출(시험 종목/날짜/마감/우선순위) → 예측·추천 호출 → 템플릿 답변. 외부 LLM 불필요.

## 데이터베이스
SQLite (`backend/data/ktl.db`).
- `applications`: 신청 1건 (분류/시료/신청자/요청옵션/예측결과/상태/완료시각)
- `samples`: 신청에 묶인 기기·시료 N건

신청자 폼 전송 → `POST /api/applications` 시 자동으로 LightGBM 예측이 함께 저장되어
관리자 화면에서 **AI 예측 완료일** 컬럼으로 노출된다.
관리자가 `완료시험으로 변경` 버튼 → `POST /api/applications/{id}/complete` 로 `status=completed`, `completed_at=now()` 업데이트.
