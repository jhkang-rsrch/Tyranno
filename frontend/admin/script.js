// Admin dashboard wired to FastAPI backend.
const API = "";

const $ = (s) => document.querySelector(s);
const todayCountEl = $("#todayCount");
const monthCountEl = $("#monthCount");
const donutChart = $("#donutChart");
const donutPercent = $("#donutPercent");
const currentTime = $("#currentTime");
const pendingTab = $("#pendingTab");
const completedTab = $("#completedTab");
const testTableBody = $("#testTableBody");
const listSummary = $("#listSummary");
const statusColumn = $("#statusColumn");
const detailModal = $("#detailModal");
const modalStatus = $("#modalStatus");
const modalTitle = $("#modalTitle");
const modalContent = $("#modalContent");
const closeModalButton = $("#closeModalButton");
const editButton = $("#editButton");
const saveButton = $("#saveButton");
const cancelEditButton = $("#cancelEditButton");
const deleteButton = $("#deleteButton");
const bizSelect = $("#bizSelect");
const predictCategorySelect = $("#predictCategorySelect");
const predictSubcategorySelect = $("#predictSubcategorySelect");
const predictedCompletion = $("#predictedCompletion");
const predictionSummary = $("#predictionSummary");
const calendarGrid = $("#calendarGrid");
const calendarMonthLabel = $("#calendarMonthLabel");
const prevMonthButton = $("#prevMonthButton");
const nextMonthButton = $("#nextMonthButton");
const shapBox = $("#shapBox");
const shapList = $("#shapList");

let catalog = {}; // biz -> mid -> [subs]
let currentView = "pending";
let visibleCalendarDate = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
let selectedCalendarDate = new Date();
let cache = { applications: [] };
let currentApp = null;     // application currently in modal
let editing = false;

async function api(path, init) {
  const r = await fetch(API + path, init);
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

const fmtDateTime = (v) => new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(v));
const fmtDate = (v) => new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "long", day: "numeric", weekday: "long" }).format(new Date(v));
const fmtDur = (s, e) => {
  const ms = new Date(e) - new Date(s);
  const h = Math.max(1, Math.round(ms / 3600000));
  const d = Math.floor(h / 24); const r = h % 24;
  if (d === 0) return `${r}시간`; if (r === 0) return `${d}일`; return `${d}일 ${r}시간`;
};
const isSameDate = (a, b) => a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
const toISODate = (d) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;

function fillSelect(el, values) {
  el.innerHTML = values.map((v) => `<option value="${v}">${v}</option>`).join("");
}

function populatePredictSelects() {
  const bizes = Object.keys(catalog).sort();
  fillSelect(bizSelect, bizes);
  onBizChange();
}
function onBizChange() {
  const mids = Object.keys(catalog[bizSelect.value] || {}).sort();
  fillSelect(predictCategorySelect, mids);
  onMidChange();
}
function onMidChange() {
  const subs = (catalog[bizSelect.value]?.[predictCategorySelect.value] || []).slice().sort();
  fillSelect(predictSubcategorySelect, subs);
  refreshPrediction();
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

async function refreshPrediction() {
  if (!selectedCalendarDate || !bizSelect.value) return;
  const body = {
    biz: bizSelect.value,
    mid: predictCategorySelect.value,
    sub: predictSubcategorySelect.value,
    receive_on: toISODate(selectedCalendarDate),
  };
  try {
    const [pred, exp] = await Promise.all([
      api("/api/predict", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
      api("/api/explain", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
    ]);
    predictedCompletion.textContent = fmtDate(pred.predicted_complete_at);
    predictionSummary.textContent = `${fmtDate(selectedCalendarDate)} 접수 · ${body.biz} > ${body.mid} > ${body.sub} · 예상 ${pred.predicted_days}일 (${pred.low_days}~${pred.high_days}일, 신뢰도 ${Math.round(pred.confidence * 100)}%, 혼잡도 ${pred.congestion})`;
    renderShap(exp);
  } catch (e) {
    predictionSummary.textContent = "예측 실패: " + e.message;
  }
}

function renderShap(exp) {
  const top = exp.top_features.slice(0, 5);
  const max = Math.max(...top.map((t) => Math.abs(t.shap)));
  shapList.innerHTML = top.map((t) => {
    const w = Math.round((Math.abs(t.shap) / max) * 100);
    const cls = t.shap >= 0 ? "pos" : "neg";
    return `<div class="shap-bar"><span class="label">${t.feature}=${t.value}</span><div class="bar ${cls}" style="width:${w}%"></div><span class="val">${t.shap.toFixed(3)}</span></div>`;
  }).join("");
  shapBox.hidden = false;
}

function updateClock() {
  currentTime.textContent = new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "long", day: "numeric", weekday: "long", hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date());
}

async function refreshDashboard() {
  try {
    const d = await api("/api/dashboard");
    todayCountEl.textContent = d.today;
    monthCountEl.textContent = d.month;
    const pct = d.month === 0 ? 0 : Math.round((d.today / d.month) * 100);
    donutPercent.textContent = `${pct}%`;
    donutChart.style.background = `conic-gradient(var(--accent) ${pct * 3.6}deg, #e4ecef 0deg)`;
  } catch {}
}

async function refreshHotspots() {
  try {
    const d = await api("/api/forecast/hotspots?top_k=5");
    const banner = document.getElementById("hotspotBanner");
    const list = document.getElementById("hotspotList");
    if (!banner || !list || !d.rows?.length) return;
    const alerts = d.rows.filter(r => r.alert);
    if (alerts.length === 0) { banner.hidden = true; return; }
    banner.hidden = false;
    list.innerHTML = `다음달(${d.next_month}월) 평년 대비 몰릴 것으로 예상되는 분야 <b>${alerts.length}건</b>: ` +
      alerts.slice(0, 5).map(r => `<span style="display:inline-block; margin:2px 4px; padding:2px 8px; background:#ffe0b2; border-radius:10px;"><b>${r.mid}</b> (${r.next_ratio.toFixed(2)}×, ${r.next_count.toLocaleString()}건)</span>`).join("");
  } catch {}
}

async function refreshAlerts() {
  try {
    const d = await api("/api/alerts");
    const banner = document.getElementById("alertBanner");
    const list = document.getElementById("alertList");
    const counts = document.getElementById("alertCounts");
    if (!banner || !list) return;
    const total = d.counts.overdue + d.counts.due_soon + d.counts.outliers;
    if (total === 0) { banner.hidden = true; return; }
    banner.hidden = false;
    counts.textContent = `(지연 ${d.counts.overdue} · 임박 ${d.counts.due_soon} · 이상치 ${d.counts.outliers})`;
    const chip = (txt, bg) => `<span style="display:inline-block; margin:2px 4px; padding:2px 8px; background:${bg}; border-radius:10px;">${txt}</span>`;
    const parts = [];
    d.overdue.slice(0, 3).forEach(r => parts.push(chip(
      `⏰ #${r.id} ${r.category||""}/${r.sample||""} <b>${r.days_overdue}일 지연</b>`, "#ffcdd2")));
    d.due_soon.slice(0, 3).forEach(r => parts.push(chip(
      `📅 #${r.id} ${r.category||""}/${r.sample||""} <b>D-${r.days_left}</b>`, "#ffe0b2")));
    d.outliers.slice(0, 3).forEach(r => parts.push(chip(
      `📊 #${r.id} 예측 ${r.predicted_days}일 vs 실제 ${r.actual_days}일 (z=${r.z})`, "#e1bee7")));
    list.innerHTML = parts.join("") || "<span style='opacity:.7'>모두 정상</span>";
  } catch {}
}

async function refreshList() {
  pendingTab.classList.toggle("active", currentView === "pending");
  completedTab.classList.toggle("active", currentView === "completed");
  statusColumn.textContent = currentView === "pending" ? "처리" : "완료 소요시간";
  cache.applications = await api(`/api/applications?status=${currentView}`);
  listSummary.textContent = `${cache.applications.length}건`;
  if (cache.applications.length === 0) {
    testTableBody.innerHTML = `<tr><td colspan="4">표시할 시험이 없습니다.</td></tr>`;
    return;
  }
  testTableBody.innerHTML = cache.applications.map((a) => {
    const right = currentView === "pending"
      ? `<button class="complete-button" type="button" data-complete-id="${a.id}">완료시험으로 변경</button>`
      : `<span class="duration-badge">${a.completed_at ? fmtDur(a.received_at, a.completed_at) : "-"}</span>`;
    return `<tr data-test-id="${a.id}"><td>${a.category}</td><td>${a.subcategory}</td><td class="sample-cell">${a.sample_name || "-"}</td><td>${right}</td></tr>`;
  }).join("");
}

function detailSection(title, items) {
  return `<section class="detail-section"><h3>${title}</h3><div class="detail-grid">${items.map(([l,v])=>`<div class="detail-item"><span>${l}</span><strong>${v||"-"}</strong></div>`).join("")}</div></section>`;
}

function openDetail(a) {
  currentApp = a;
  editing = false;
  saveButton.hidden = true;
  cancelEditButton.hidden = true;
  editButton.hidden = false;
  modalStatus.textContent = a.status === "pending" ? "미완료된 시험" : "완료된 시험";
  modalTitle.textContent = `${a.sample_name || "(시료명 없음)"} 신청 양식 (#${a.id})`;
  renderViewMode();
  detailModal.classList.remove("hidden");
  loadExplain(a.id);
}

async function loadExplain(id) {
  const slot = document.getElementById("explainSlot");
  if (!slot) return;
  slot.innerHTML = '<span style="color:#789;">AI 분석 중…</span>';
  try {
    const d = await api(`/api/applications/${id}/explain`);
    const p = d.prediction || {};
    const top = (d.shap?.top_features || []).slice(0, 3);
    const conf = p.confidence != null ? `${Math.round(p.confidence*100)}%` : "-";
    const band = (p.low_days != null && p.high_days != null)
      ? `${p.low_days}일 ~ ${p.high_days}일` : "-";
    const cmp = (d.actual_days != null && p.predicted_days != null)
      ? `<div class="detail-item" style="grid-column:1/-1; background:${Math.abs(d.actual_days - p.predicted_days) > 2*(p.history_std||7) ? "#fdecea" : "#eef6ee"};">
           <span>예측 vs 실제</span>
           <strong>예측 ${p.predicted_days}일 / 실제 ${d.actual_days}일 (오차 ${(d.actual_days - p.predicted_days).toFixed(1)}일)</strong>
         </div>` : "";
    const shapHtml = top.length === 0 ? "<span style='color:#789;'>SHAP 데이터 없음</span>" :
      top.map(f => {
        const sign = f.shap >= 0 ? "+" : "";
        const color = f.shap >= 0 ? "#c62828" : "#2e7d32";
        return `<div style="display:flex; gap:8px; padding:4px 0; border-bottom:1px dotted #ddd;">
                  <span style="flex:0 0 130px; color:#345;">${f.feature}</span>
                  <span style="flex:1; color:#566; font-size:12px;">${f.value}</span>
                  <strong style="color:${color}; font-variant-numeric:tabular-nums;">${sign}${f.shap.toFixed(3)}</strong>
                </div>`;
      }).join("");
    slot.innerHTML = `
      <section class="detail-section"><h3>🧠 AI 예측 신뢰도 · 영향 요인</h3>
        <div class="detail-grid">
          <div class="detail-item"><span>예측 신뢰도</span><strong>${conf}</strong></div>
          <div class="detail-item"><span>80% 신뢰 구간</span><strong>${band}</strong></div>
          <div class="detail-item"><span>유사 사례</span><strong>${p.history_count?.toLocaleString() || 0}건 (평균 ${p.history_mean ?? "-"}일)</strong></div>
          <div class="detail-item"><span>접수월 혼잡도</span><strong>${p.congestion ?? "-"}</strong></div>
          ${cmp}
        </div>
        <div style="margin-top:10px; padding:10px; background:#f8fafb; border-radius:6px;">
          <div style="font-size:12px; color:#456; margin-bottom:6px;">상위 영향 요인 (SHAP, +는 소요일 증가 방향)</div>
          ${shapHtml}
        </div>
      </section>`;
  } catch (e) {
    slot.innerHTML = `<div style="color:#a55; font-size:12px;">분석 실패: ${e.message}</div>`;
  }
}

function renderViewMode() {
  const a = currentApp;
  modalContent.innerHTML = [
    detailSection("시험 정보", [
      ["사업구분", a.biz], ["중분류", a.category], ["소분류", a.subcategory],
      ["시료 이름", a.sample_name],
      ["접수 일시", fmtDateTime(a.received_at)],
      ["완료 일시", a.completed_at ? fmtDateTime(a.completed_at) : "미완료"],
      ["완료 소요시간", a.completed_at ? fmtDur(a.received_at, a.completed_at) : "진행중"],
      ["AI 예측 소요일", a.predicted_days != null ? `${a.predicted_days}일` : "-"],
      ["AI 예측 완료일", a.predicted_complete_at ? a.predicted_complete_at.slice(0,10) : "-"],
    ]),
    detailSection("신청자 정보", [
      ["회사명", a.applicant?.company], ["사업자등록번호", a.applicant?.business_no],
      ["회사주소", a.applicant?.address], ["대표자", PiiMask.maskName(a.applicant?.ceo)],
      ["신청인", PiiMask.maskName(a.applicant?.name)], ["전화번호", PiiMask.maskPhone(a.applicant?.phone)],
      ["휴대폰", PiiMask.maskPhone(a.applicant?.mobile)], ["E-mail", PiiMask.maskEmail(a.applicant?.email)],
      ["FAX", PiiMask.maskPhone(a.applicant?.fax)],
    ]),
    detailSection("접수 및 발급 정보", [
      ["결제방법", a.request?.payment], ["성적서 종류", a.request?.report],
      ["시료처리", a.request?.return_method], ["택배 주소", a.request?.return_address],
      ["특이사항", a.request?.notes],
    ]),
    `<div id="explainSlot"></div>`,
  ].join("");
}

const _editFields = [
  ["시험 정보", [
    ["status", "상태", "select", ["pending","completed"]],
    ["biz", "사업구분"],
    ["category", "중분류"],
    ["subcategory", "소분류"],
    ["sample_name", "시료 이름"],
    ["received_at", "접수 일시", "datetime-local"],
    ["completed_at", "완료 일시", "datetime-local"],
    ["predicted_days", "AI 예측 소요일", "number"],
    ["predicted_complete_at", "AI 예측 완료일", "datetime-local"],
  ]],
  ["신청자 정보", [
    ["company", "회사명"], ["business_no", "사업자등록번호"],
    ["address", "회사주소", "textarea"], ["ceo", "대표자"],
    ["applicant_name", "신청인"], ["phone", "전화번호"],
    ["mobile", "휴대폰"], ["email", "E-mail"], ["fax", "FAX"],
  ]],
  ["접수 및 발급 정보", [
    ["payment", "결제방법"], ["report", "성적서 종류"],
    ["return_method", "시료처리"], ["return_address", "택배 주소", "textarea"],
    ["notes", "특이사항", "textarea"],
  ]],
];

function _flatVal(a, k) {
  if (k in a) return a[k];
  if (a.applicant && k in a.applicant) return a.applicant[k];
  if (k === "name" && a.applicant) return a.applicant.name;
  if (a.request && k in a.request) return a.request[k];
  return null;
}

function _toLocalDT(v) {
  if (!v) return "";
  // input[type=datetime-local] expects YYYY-MM-DDTHH:MM
  return v.slice(0,16);
}

function renderEditMode() {
  const a = currentApp;
  const html = _editFields.map(([title, fields]) => {
    const rows = fields.map(([key, label, kind, options]) => {
      let raw = _flatVal(a, key);
      if (key === "applicant_name") raw = a.applicant?.name;
      let val = raw == null ? "" : String(raw);
      let input;
      if (kind === "select") {
        input = `<select name="${key}">${options.map(o => `<option value="${o}" ${o===val?"selected":""}>${o}</option>`).join("")}</select>`;
      } else if (kind === "textarea") {
        input = `<textarea name="${key}">${val}</textarea>`;
      } else if (kind === "number") {
        input = `<input type="number" name="${key}" value="${val}" />`;
      } else if (kind === "datetime-local") {
        input = `<input type="datetime-local" name="${key}" value="${_toLocalDT(val)}" />`;
      } else {
        input = `<input type="text" name="${key}" value="${val.replace(/"/g,"&quot;")}" />`;
      }
      return `<label>${label}</label>${input}`;
    }).join("");
    return `<section class="edit-section"><h3>${title}</h3><div class="edit-grid">${rows}</div></section>`;
  }).join("");
  modalContent.innerHTML = `<form id="editForm">${html}</form>`;
}

async function saveEdits() {
  const form = document.getElementById("editForm");
  if (!form) return;
  const fd = new FormData(form);
  const payload = {};
  for (const [k, v] of fd.entries()) {
    if (v === "" || v == null) continue;
    if (k === "predicted_days") payload[k] = parseInt(v, 10);
    else if (["received_at","completed_at","predicted_complete_at"].includes(k))
      payload[k] = new Date(v).toISOString();
    else payload[k] = v;
  }
  try {
    const updated = await api(`/api/applications/${currentApp.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    currentApp = updated;
    editing = false;
    saveButton.hidden = true;
    cancelEditButton.hidden = true;
    editButton.hidden = false;
    renderViewMode();
    await Promise.all([refreshList(), refreshDashboard()]);
  } catch (e) {
    alert("저장 실패: " + e.message);
  }
}

async function deleteCurrent() {
  if (!currentApp) return;
  if (!confirm(`#${currentApp.id} 신청을 정말 삭제하시겠습니까? (DB에서 영구 제거)`)) return;
  try {
    await api(`/api/applications/${currentApp.id}`, { method: "DELETE" });
    detailModal.classList.add("hidden");
    currentApp = null;
    await Promise.all([refreshList(), refreshDashboard()]);
  } catch (e) {
    alert("삭제 실패: " + e.message);
  }
}

async function completeApp(id) {
  await api(`/api/applications/${id}/complete`, { method: "POST" });
  await Promise.all([refreshList(), refreshDashboard()]);
}

function bind() {
  pendingTab.addEventListener("click", () => { currentView = "pending"; refreshList(); });
  completedTab.addEventListener("click", () => { currentView = "completed"; refreshList(); });
  testTableBody.addEventListener("click", (e) => {
    const cb = e.target.closest("[data-complete-id]");
    if (cb) { e.stopPropagation(); completeApp(Number(cb.dataset.completeId)); return; }
    const row = e.target.closest("[data-test-id]");
    if (!row) return;
    const a = cache.applications.find((x) => x.id === Number(row.dataset.testId));
    if (a) openDetail(a);
  });
  closeModalButton.addEventListener("click", () => detailModal.classList.add("hidden"));
  detailModal.addEventListener("click", (e) => { if (e.target === detailModal) detailModal.classList.add("hidden"); });
  PiiMask.bindToggle(document.getElementById("piiToggle"), () => {
    if (currentApp && !editing) renderViewMode();
  });
  editButton.addEventListener("click", () => {
    if (!currentApp) return;
    editing = true;
    editButton.hidden = true;
    saveButton.hidden = false;
    cancelEditButton.hidden = false;
    renderEditMode();
  });
  cancelEditButton.addEventListener("click", () => {
    editing = false;
    editButton.hidden = false;
    saveButton.hidden = true;
    cancelEditButton.hidden = true;
    renderViewMode();
  });
  saveButton.addEventListener("click", saveEdits);
  deleteButton.addEventListener("click", deleteCurrent);
  calendarGrid.addEventListener("click", (e) => {
    const b = e.target.closest("[data-calendar-day]"); if (!b) return;
    selectedCalendarDate = new Date(visibleCalendarDate.getFullYear(), visibleCalendarDate.getMonth(), Number(b.dataset.calendarDay));
    renderCalendar(); refreshPrediction();
  });
  prevMonthButton.addEventListener("click", () => { visibleCalendarDate = new Date(visibleCalendarDate.getFullYear(), visibleCalendarDate.getMonth() - 1, 1); renderCalendar(); });
  nextMonthButton.addEventListener("click", () => { visibleCalendarDate = new Date(visibleCalendarDate.getFullYear(), visibleCalendarDate.getMonth() + 1, 1); renderCalendar(); });
  bizSelect.addEventListener("input", onBizChange);
  predictCategorySelect.addEventListener("input", onMidChange);
  predictSubcategorySelect.addEventListener("input", refreshPrediction);
}

(async function init() {
  updateClock();
  catalog = await api("/api/catalog");
  populatePredictSelects();
  renderCalendar();
  await Promise.all([refreshDashboard(), refreshList()]);
  await refreshPrediction();
  await refreshHotspots();
  await refreshAlerts();
  bind();
  setInterval(() => { updateClock(); refreshDashboard(); }, 5000);
})();
