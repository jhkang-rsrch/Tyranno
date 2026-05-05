// Applicant view wired to FastAPI backend.
const API = "";

const $ = (s) => document.querySelector(s);

const todayLabel = $("#todayLabel");
const durationChart = $("#durationChart");
const fastestLabel = $("#fastestLabel");
const toggleChartButton = $("#toggleChartButton");
const receiptButton = $("#receiptButton");
const calcButton = $("#calcButton");
const receiptView = $("#receiptView");
const calcView = $("#calcView");

const formBiz = $("#formBiz");
const formMid = $("#formMid");
const formSub = $("#formSub");
const draftStatus = $("#draftStatus");
const submitMessage = $("#submitMessage");
const receiptForm = $("#receiptForm");
const draftKey = "ktl-applicant-draft-v2";

const calcBiz = $("#calcBiz");
const categorySelect = $("#categorySelect");
const subcategorySelect = $("#subcategorySelect");
const calcDate = $("#calcDate");
const calculatedDays = $("#calculatedDays");
const calculatedDate = $("#calculatedDate");
const calculateButton = $("#calculateButton");

const recBiz = $("#recBiz"), recMid = $("#recMid"), recSub = $("#recSub");
const recEarliest = $("#recEarliest"), recDeadline = $("#recDeadline");
const recPriority = $("#recPriority"), recButton = $("#recButton");
const recommendationList = $("#recommendationList");
const recommendationMessage = $("#recommendationMessage");

const chatLog = $("#chatLog"), chatInput = $("#chatInput"), chatSend = $("#chatSend");

const calendarGrid = $("#calendarGrid");
const calendarMonthLabel = $("#calendarMonthLabel");
const prevMonthButton = $("#prevMonthButton"), nextMonthButton = $("#nextMonthButton");
const calendarBizSelect = $("#calendarBizSelect");
const calendarCategorySelect = $("#calendarCategorySelect");
const calendarSubcategorySelect = $("#calendarSubcategorySelect");
const calendarCompletionDate = $("#calendarCompletionDate");
const calendarSelectionSummary = $("#calendarSelectionSummary");

let catalog = {};
let bizStats = [];
let visibleCalendarDate = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
let selectedCalendarDate = null;
let isChartExpanded = false;

async function api(p, init) {
  const r = await fetch(API + p, init);
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}
const fmtDate = (v) => new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "long", day: "numeric", weekday: "long" }).format(new Date(v));
const isSameDate = (a, b) => a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
const toISO = (d) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;

function fillSel(el, items) {
  el.innerHTML = items.map((v) => `<option value="${v}">${v}</option>`).join("");
}

function bindLinkedSelects(bizEl, midEl, subEl, onChange) {
  const refresh = () => {
    const mids = Object.keys(catalog[bizEl.value] || {}).sort();
    fillSel(midEl, mids);
    refreshMid();
  };
  const refreshMid = () => {
    const subs = (catalog[bizEl.value]?.[midEl.value] || []).slice().sort();
    fillSel(subEl, subs);
    onChange && onChange();
  };
  bizEl.addEventListener("input", refresh);
  midEl.addEventListener("input", refreshMid);
  subEl.addEventListener("input", () => onChange && onChange());
  return { refresh, refreshMid };
}

function renderChart() {
  const items = bizStats.slice().sort((a, b) => a.avg_days - b.avg_days);
  const max = Math.max(...items.map((c) => c.avg_days || 0));
  const fastest = items[0];
  fastestLabel.textContent = `가장 빠른 사업구분: ${fastest.biz} ${Math.round(fastest.avg_days)}일`;
  const palette = ["#126b67", "#3067a6", "#b9821a", "#cf563e", "#4f7d45", "#6b5b95"];
  const visible = isChartExpanded ? items : items.slice(0, 8);
  durationChart.classList.toggle("collapsed", !isChartExpanded);
  durationChart.innerHTML = visible.map((c, i) => {
    const w = Math.round(((c.avg_days || 0) / max) * 100);
    const color = palette[i % palette.length];
    return `<div class="chart-row"><span>${c.biz}</span><div class="bar-track"><div class="bar-fill" style="width:${w}%;background:${color}"></div></div><strong>${(c.avg_days||0).toFixed(1)}일</strong></div>`;
  }).join("");
  toggleChartButton.textContent = isChartExpanded ? "접기" : `펼치기 (${items.length}개 전체 보기)`;
}

function renderCalendar() {
  const y = visibleCalendarDate.getFullYear(), m = visibleCalendarDate.getMonth();
  const first = new Date(y, m, 1).getDay();
  const last = new Date(y, m + 1, 0).getDate();
  const today = new Date();
  calendarMonthLabel.textContent = `${y}년 ${m + 1}월`;
  const blanks = Array.from({ length: first }, () => '<button class="calendar-day empty" type="button" tabindex="-1"></button>');
  const days = Array.from({ length: last }, (_, i) => {
    const day = i + 1;
    const dt = new Date(y, m, day);
    const cls = ["calendar-day", isSameDate(dt, today) ? "today" : "", isSameDate(dt, selectedCalendarDate) ? "selected" : ""].filter(Boolean).join(" ");
    return `<button class="${cls}" type="button" data-calendar-day="${day}">${day}</button>`;
  });
  calendarGrid.innerHTML = [...blanks, ...days].join("");
}

async function refreshCalendarPrediction() {
  if (!selectedCalendarDate) {
    calendarCompletionDate.textContent = "날짜를 선택하세요";
    calendarSelectionSummary.textContent = "분류와 접수일을 선택하면 LightGBM 예측 완료일이 표시됩니다.";
    return;
  }
  try {
    const p = await api("/api/predict", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ biz: calendarBizSelect.value, mid: calendarCategorySelect.value,
        sub: calendarSubcategorySelect.value, receive_on: toISO(selectedCalendarDate) }),
    });
    calendarCompletionDate.textContent = fmtDate(p.predicted_complete_at);
    calendarSelectionSummary.textContent = `${fmtDate(selectedCalendarDate)} 접수 · ${calendarBizSelect.value} > ${calendarCategorySelect.value} > ${calendarSubcategorySelect.value} · 예상 ${p.predicted_days}일 (${p.low_days}~${p.high_days}일, 신뢰도 ${Math.round(p.confidence*100)}%, 혼잡도 ${p.congestion})`;
  } catch (e) {
    calendarSelectionSummary.textContent = "예측 실패: " + e.message;
  }
}

async function calculateDuration() {
  if (!calcDate.value) {
    calculatedDays.textContent = "-";
    calculatedDate.textContent = "접수일을 선택하세요";
    return;
  }
  const p = await api("/api/predict", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ biz: calcBiz.value, mid: categorySelect.value, sub: subcategorySelect.value, receive_on: calcDate.value }),
  });
  calculatedDays.textContent = `${p.predicted_days}일 (${p.low_days}~${p.high_days})`;
  calculatedDate.textContent = `예상 완료일 ${fmtDate(p.predicted_complete_at)} · 신뢰도 ${Math.round(p.confidence*100)}% · 혼잡도 ${p.congestion}`;
}

async function fetchRecommend() {
  if (!recEarliest.value) { recommendationMessage.textContent = "희망 시작일을 선택해주세요."; return; }
  recommendationMessage.textContent = "추천 계산 중...";
  try {
    const recs = await api("/api/recommend", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        biz: recBiz.value, mid: recMid.value, sub: recSub.value,
        earliest: recEarliest.value,
        deadline: recDeadline.value || null,
        priority: recPriority.value, n: 5,
      }),
    });
    if (!recs.length) { recommendationList.innerHTML = ""; recommendationMessage.textContent = "추천 결과가 없습니다."; return; }
    recommendationList.innerHTML = recs.map((r, i) => `<div class="recommend-card"><strong>${i+1}순위 · 접수 ${r.receive_on}</strong>예상 완료 ${r.predicted_complete_at} · 소요 ${r.predicted_days}일 · 혼잡도 ${r.congestion}${r.meets_deadline?" · ✅ 마감 충족":" · ⚠ 마감 초과"}</div>`).join("");
    recommendationMessage.textContent = "AI 추천 결과 (점수순)";
  } catch (e) {
    recommendationMessage.textContent = "추천 실패: " + e.message;
  }
}

async function chatAsk() {
  const text = chatInput.value.trim();
  if (!text) return;
  appendChat("user", text);
  chatInput.value = "";
  appendChat("bot", "분석 중...");
  try {
    const r = await api("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: text }) });
    chatLog.lastElementChild.querySelector(".bubble").textContent = r.message;
  } catch (e) {
    chatLog.lastElementChild.querySelector(".bubble").textContent = "에러: " + e.message;
  }
  chatLog.scrollTop = chatLog.scrollHeight;
}
function appendChat(role, text) {
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.innerHTML = `<span class="bubble"></span>`;
  div.querySelector(".bubble").textContent = text;
  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function setActiveView(name) {
  const isReceipt = name === "receipt";
  receiptButton.classList.toggle("active", isReceipt);
  calcButton.classList.toggle("active", !isReceipt);
  receiptView.classList.toggle("active", isReceipt);
  calcView.classList.toggle("active", !isReceipt);
}

function serializeForm() {
  const fd = new FormData(receiptForm);
  const obj = {};
  for (const [k, v] of fd.entries()) obj[k] = v;
  return obj;
}

async function submitForm(ev) {
  ev.preventDefault();
  const obj = serializeForm();
  const payload = {
    biz: obj.biz, category: obj.category, subcategory: obj.subcategory,
    sample_name: obj.sample_name,
    company: obj.company, business_no: obj.business_no, address: obj.address,
    ceo: obj.ceo, applicant_name: obj.applicant_name, phone: obj.phone,
    mobile: obj.mobile, email: obj.email, fax: obj.fax,
    payment: obj.payment, report: obj.report,
    return_method: obj.return_method, return_address: obj.return_address,
    notes: obj.notes, samples: [],
  };
  try {
    const r = await api("/api/applications", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const p = r.prediction || {};
    submitMessage.textContent = `전송완료! 신청번호 ${r.id} · 예상 완료 ${p.predicted_complete_at || "-"} (${p.predicted_days || "-"}일, 혼잡도 ${p.congestion || "-"})`;
    receiptForm.reset();
    localStorage.removeItem(draftKey);
  } catch (e) {
    submitMessage.textContent = "전송 실패: " + e.message;
  }
}

function bind() {
  receiptButton.addEventListener("click", () => setActiveView("receipt"));
  calcButton.addEventListener("click", () => setActiveView("calc"));
  toggleChartButton.addEventListener("click", () => { isChartExpanded = !isChartExpanded; renderChart(); });
  calculateButton.addEventListener("click", calculateDuration);
  recButton.addEventListener("click", fetchRecommend);
  chatSend.addEventListener("click", chatAsk);
  chatInput.addEventListener("keydown", (e) => { if (e.key === "Enter") chatAsk(); });
  receiptForm.addEventListener("submit", submitForm);
  $("#saveDraftButton").addEventListener("click", () => {
    localStorage.setItem(draftKey, JSON.stringify(serializeForm()));
    draftStatus.textContent = `임시저장됨 ${new Date().toLocaleTimeString("ko-KR", { hour:"2-digit", minute:"2-digit" })}`;
  });
  calendarGrid.addEventListener("click", (e) => {
    const b = e.target.closest("[data-calendar-day]"); if (!b) return;
    selectedCalendarDate = new Date(visibleCalendarDate.getFullYear(), visibleCalendarDate.getMonth(), Number(b.dataset.calendarDay));
    renderCalendar(); refreshCalendarPrediction();
  });
  prevMonthButton.addEventListener("click", () => { visibleCalendarDate = new Date(visibleCalendarDate.getFullYear(), visibleCalendarDate.getMonth() - 1, 1); renderCalendar(); });
  nextMonthButton.addEventListener("click", () => { visibleCalendarDate = new Date(visibleCalendarDate.getFullYear(), visibleCalendarDate.getMonth() + 1, 1); renderCalendar(); });
}

function loadDraft() {
  const d = localStorage.getItem(draftKey); if (!d) return;
  try {
    const obj = JSON.parse(d);
    Object.entries(obj).forEach(([k, v]) => {
      const el = receiptForm.querySelector(`[name="${k}"]`); if (el) el.value = v;
    });
    draftStatus.textContent = "임시저장된 양식을 불러왔습니다.";
  } catch {}
}

(async function init() {
  todayLabel.textContent = fmtDate(new Date());
  catalog = await api("/api/catalog");
  bizStats = await api("/api/stats/biz");

  const bizes = Object.keys(catalog).sort();
  fillSel(formBiz, bizes); fillSel(calcBiz, bizes); fillSel(recBiz, bizes); fillSel(calendarBizSelect, bizes);

  bindLinkedSelects(formBiz, formMid, formSub);
  bindLinkedSelects(calcBiz, categorySelect, subcategorySelect);
  bindLinkedSelects(recBiz, recMid, recSub);
  bindLinkedSelects(calendarBizSelect, calendarCategorySelect, calendarSubcategorySelect, refreshCalendarPrediction);

  // initialize cascades
  formBiz.dispatchEvent(new Event("input"));
  calcBiz.dispatchEvent(new Event("input"));
  recBiz.dispatchEvent(new Event("input"));
  calendarBizSelect.dispatchEvent(new Event("input"));

  calcDate.value = toISO(new Date());
  recEarliest.value = toISO(new Date());

  renderChart();
  renderCalendar();
  bind();
  loadDraft();
  appendChat("bot", "안녕하세요! 시험 종목과 시기, 마감일, 우선순위(빨리/안정/혼잡회피/마감)를 자연어로 입력하시면 추천을 드립니다.");
})();
