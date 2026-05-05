# KTL TestMate

> AI-powered processing-time prediction, recommendation, and natural-language consultation
> for **KTL (한국산업기술시험원)** test applications.

[![Python](https://img.shields.io/badge/python-3.11-blue.svg)](#)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](#)
[![LightGBM](https://img.shields.io/badge/LightGBM-4.5-brightgreen.svg)](#)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED.svg)](#)

KTL이 보유한 시험 신청·처리 이력 데이터(약 1.16M rows, 2006–2023)를 바탕으로
**예상 처리일수 / 완료일 / 혼잡도 / SHAP 기반 설명 / 우선순위 기반 신청일 추천 / 자연어 상담**을
제공하는 풀스택 서비스입니다.

---

## ⚡ 30초 재현 (Docker)

저장소를 클론한 직후 바로 실행 가능합니다. 학습된 LightGBM 모델 (`backend/artifacts/`) 이 포함되어
있으므로 **데이터셋 CSV 없이도 모든 예측·추천·상담 기능이 동작**합니다.

```bash
git clone https://github.com/jhkang-rsrch/Tyranno.git
cd Tyranno
docker compose up -d --build
# 완료되면:
open http://localhost:8765/
```

| URL | 용도 |
|---|---|
| http://localhost:8765/ | 랜딩 |
| http://localhost:8765/applicant/ | 신청자 모드 (접수 + 자연어 상담 + 추천) |
| http://localhost:8765/admin/ | 관리자 모드 (현황 + 통계 + SHAP 시각화) |
| http://localhost:8765/docs | Swagger UI (전체 REST API) |

### 모델을 직접 재학습하려면
```bash
mkdir -p data
cp /path/to/통합_시험접수_현황.csv data/
rm backend/artifacts/lgbm_proc_days.txt    # 학습 트리거
docker compose up --build
```
컨테이너 entrypoint가 `lgbm_proc_days.txt` 부재를 감지하면 `backend/train.py` 를 자동으로 실행합니다.

---

## 🐳 Docker 없이 (로컬 파이썬)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m backend.seed                # 데모 신청 3건 시드 (1회)
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8765
```

---

## 🧩 아키텍처

```
                ┌────────────────────────────────────────────────┐
                │                  Browser                       │
                │   /applicant/  ←→  /admin/                     │
                └──────────┬─────────────────────────┬──────────┘
                           │ REST (JSON)             │
            ┌──────────────▼──────────────┐  static  │
            │       FastAPI (app.py)      │──────────┘
            │  /api/predict /explain      │
            │  /api/recommend /chat       │
            │  /api/applications /stats   │
            └──┬─────────┬──────────┬─────┘
               │         │          │
   ┌───────────▼─┐  ┌────▼─────┐  ┌─▼─────────┐
   │ predictor   │  │ agent    │  │ stats     │
   │ LightGBM +  │  │ Regex    │  │ pandas    │
   │ SHAP        │  │ NL → cmd │  │           │
   └───────────┬─┘  └────┬─────┘  └─┬─────────┘
               │         │           │
        ┌──────▼─────────▼───────────▼─────┐
        │  artifacts/  (committed)         │
        │   lgbm_proc_days.txt             │
        │   category_maps.json             │
        │   global_stats.json              │
        │   {biz,mid,sub}_stats.csv        │
        │   {monthly,yearly,seasonality}.csv│
        └──────────────────────────────────┘
                   │
              ┌────▼────────────┐
              │  SQLite (db.py) │
              │  applications,  │
              │  samples        │
              └─────────────────┘
```

---

## 🤖 예측 모델이 어떻게 동작하는가

전체 파이프라인은 **5개의 협력 컴포넌트**로 구성됩니다. 각각 별도 모듈에 있고, 한 번의 사용자
요청에 여러 개가 함께 호출됩니다.

### 1️⃣ 처리일수 회귀 모델 — LightGBM ([backend/predictor.py](backend/predictor.py))

**문제 정의**: 시험 1건의 *처리일수* (= 완료일 − 접수일) 를 예측하는 회귀 문제.

**학습** ([backend/train.py](backend/train.py)) — 학습 데이터 1,166,203건 (0~365일 컷, log1p 변환).

| 구분 | 피처 |
|---|---|
| **categorical** | `사업구분명`, `단위사업중분류명`, `단위사업소분류명`, 요일, 월, 분기 |
| **numeric** | 연도, 월일, 연중일, 월총접수량, 사업구분별 월접수량 |

- **타겟**: `log1p(처리일수)` — 분포 왜도가 커서 로그변환
- **시간 기반 split**: 마지막 12개월 holdout → leakage 방지
- **하이퍼파라미터**: `learning_rate=0.05`, `num_leaves=128`, `min_data_in_leaf=200`, `feature_fraction=0.9`, `bagging_fraction=0.9`, early stopping(40 rounds)
- **결과**: best_iteration 146, **MAE ≈ 27.2일 / MedianAE ≈ 9.8일** (편차가 큰 일부 사업구분이 평균 MAE를 끌어올림)

**추론** — 단일 row 생성 시 학습 시점의 카테고리 매핑(`category_maps.json`)을 그대로 적용해
미관측 카테고리는 NaN 처리. 월별 접수량은 학습 데이터의 평균을 fallback으로 사용.

### 2️⃣ 불확실성 구간 + 신뢰도

LightGBM 단일 점추정 외에:

- **80% 구간**: `pred ± 0.8 × σ_sub` (해당 소분류 과거 처리일수의 표준편차)
- **신뢰도(0.4–0.95)**: `0.85 − σ_sub/80 + log10(N)/6 의 클램프`
  - σ가 작고 표본 N이 클수록 ↑

이렇게 하면 *"예상 24일, 범위 20~31일, 신뢰도 82%"* 같이 응답할 수 있어 사용자가 위험을 평가할 수 있습니다.

### 3️⃣ 혼잡도 등급화

해당 월의 총 접수량을 학습 데이터의 평균과 비교한 단순 등급:

| 비율 | 등급 |
|---|---|
| < 0.85 | 낮음 |
| 0.85–1.10 | 보통 |
| 1.10–1.30 | 높음 |
| ≥ 1.30 | 매우 높음 |

### 4️⃣ SHAP 설명 — 왜 그 날짜가 나왔는가

[`shap.TreeExplainer`](https://shap.readthedocs.io/) 로 LightGBM의 단건 예측을 분해.
각 피처의 SHAP 값 (log-domain 단위) Top-K를 반환하고, 관리자 사이드바에서 막대그래프로 시각화합니다.

```jsonc
// POST /api/explain 응답 예시
{
  "base_value_log": 2.3756,
  "base_value_days": 9.74,
  "top_features": [
    {"feature": "단위사업중분류명", "value": "KOLAS교정", "shap": -0.167},
    {"feature": "연도",            "value": "2026.0",     "shap": -0.116},
    {"feature": "월총접수량",       "value": "5661.18",    "shap":  0.068}
  ]
}
```
양의 SHAP은 *처리일수를 늘리는 방향*, 음은 *줄이는 방향*. 빨강/파랑 막대로 직관적으로 보여줍니다.

### 5️⃣ 추천기 ([backend/recommender.py](backend/recommender.py))

희망 시작일~+14일(또는 마감일까지) 범위의 영업일 후보들에 대해 LightGBM 예측을 반복 호출하고,
사용자가 고른 우선순위에 따라 다른 가중치로 점수를 매겨 정렬:

| priority | 점수 함수 |
|---|---|
| `fast` | `0.6·fast(short) + 0.2·congestion + 0.2·deadline_ok` |
| `stable` | `0.5·1/(1+span/5) + 0.2·congestion + 0.3·deadline_ok` |
| `avoid_congestion` | `0.6·congestion + 0.2·fast + 0.2·deadline_ok` |
| `meet_deadline` | `0.7·deadline_ok + 0.2·fast + 0.1·stable` |

상위 N개 후보의 `(접수일, 예상완료일, 혼잡도, 마감충족여부, 신뢰도)` 를 반환합니다.

### 6️⃣ 자연어 상담 에이전트 ([backend/agent.py](backend/agent.py))

**LLM 없이** 정규식만으로 한국어 질문에서 핵심 슬롯을 추출 → 위의 모델들을 호출 → 템플릿 답변.

**추출 슬롯**:
| 슬롯 | 패턴 예시 |
|---|---|
| 시험 종목 | `사업구분/중분류/소분류` 라벨이 텍스트에 포함되는지 longest-match |
| 신청 희망일 | `2026-04-15`, `4월 둘째 주`, `다음달`, `오늘` 등 |
| 목표 완료일 | `5월 말까지`, `2026-05-31 전까지` |
| 우선순위 | "빨리/빠르게" → `fast`, "안정/변동성" → `stable`, "혼잡/밀리" → `avoid_congestion`, "마감/맞춰" → `meet_deadline` |

**응답 예** (실제 출력):
> [표준 > KOLAS교정 > 압력] 2026-05-05 접수 기준 예상 소요 5.13일 (범위 1.12~9.14일,
> 신뢰도 94%). 예상 완료일은 2026-05-12이며, 해당 월 혼잡도는 '보통' 입니다.
> 목표 완료일 2026-05-31 이내 처리 가능성이 높습니다. 추천 신청일은 2026-05-05
> (예상 완료 2026-05-12, 우선순위 기준 'fast').

장점: **결정론적**, **외부 API 비용 없음**, **개인정보 외부 유출 없음**. 단점: 자유도가 낮으므로 학교/공모전 데모 용도에 적합.

---

## 🗂️ REST API

| Method | Path | 설명 |
|---|---|---|
| GET  | `/api/catalog` | `사업구분 → 중분류 → [소분류]` 트리 |
| POST | `/api/predict` | 점추정 + 80% 구간 + 신뢰도 + 혼잡도 |
| POST | `/api/explain` | SHAP top-K |
| POST | `/api/recommend` | 우선순위별 접수일 N개 |
| POST | `/api/chat` | 자연어 → 추출 + 예측 + 답변 |
| GET  | `/api/stats/{biz,mid,sub}` | 분류별 평균/중앙값/표준편차 |
| GET  | `/api/stats/{monthly,yearly,seasonality}` | 시계열 집계 |
| GET/POST/DELETE | `/api/applications[/{id}[/complete]]` | 신청 CRUD |
| GET  | `/api/dashboard` | 오늘/이번달/대기/완료 카운터 |

전체 스키마는 http://localhost:8765/docs (Swagger UI) 에서 확인.

---

## 📁 디렉터리 구조

```
.
├── Dockerfile, docker-compose.yml, entrypoint.sh
├── requirements.txt
├── frontend/                # Vanilla JS SPAs (정적 파일, 빌드 불필요)
│   ├── index.html
│   ├── admin/               # 관리자 + DB 콘솔 + 통계 콘솔
│   │   ├── index.html, script.js, styles.css
│   │   ├── db.html, db.js
│   │   └── stats.html, stats.js
│   └── applicant/           # 신청자 SPA
│       ├── index.html, script.js, styles.css
├── backend/
│   ├── app.py              # FastAPI 라우팅 (frontend/ 정적 마운트)
│   ├── db.py               # SQLite + SQLAlchemy
│   ├── predictor.py        # LightGBM + SHAP
│   ├── recommender.py      # 점수 기반 접수일 추천
│   ├── agent.py            # 한국어 NL 에이전트 (regex)
│   ├── stats.py            # 통계 집계
│   ├── train.py            # LightGBM 학습 스크립트
│   ├── seed.py             # DB 데모 데이터 시드
│   └── artifacts/          # 학습된 모델 + 매핑 + 통계 csv (커밋됨)
└── data/                   # (gitignored) 학습용 CSV 위치
```

---

## 📊 데이터셋

이 저장소는 다음 CSV를 학습에 사용합니다:

```
data/통합_시험접수_현황.csv      # ~120MB · UTF-8 BOM · 1,444,141 rows
```

| 컬럼 | 설명 |
|---|---|
| 개별접수번호 | 신청 ID |
| 사업구분명 / 단위사업중분류명 / 단위사업소분류명 | 시험 분류 3단계 |
| 접수일자 | 신청일 |
| 처리일수 | 회귀 타겟 (= 완료일 − 접수일) |

데이터는 KTL 내부에서 받은 자료로, 라이선스 사정상 저장소에 포함되지 않습니다.
**모델은 이미 학습되어 커밋되어 있으므로** 데이터 없이도 추론은 정상 동작합니다.

---

## 📝 라이선스 / 저작자
공모전 ("제5회 AI·공공데이터 활용 및 창업 경진대회") 출품작.
