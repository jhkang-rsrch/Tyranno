// Admin stats console. Uses Chart.js (loaded via CDN in stats.html).
const $ = (s) => document.querySelector(s);
const api = async (p) => {
  const r = await fetch(p);
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
};

const TEAL = "#103e3a";
const ACCENT = "#cf563e";
const BLUE = "#3067a6";
const GREEN = "#2e7d32";
const YELLOW = "#ffb300";

let charts = {};
let catalog = {};
let allBiz = [], allMid = [], allSub = [];

function destroy(name) {
  if (charts[name]) { charts[name].destroy(); delete charts[name]; }
}

function makeBar(canvasId, labels, data, label, color, horizontal=false) {
  destroy(canvasId);
  const ctx = document.getElementById(canvasId);
  charts[canvasId] = new Chart(ctx, {
    type: "bar",
    data: { labels, datasets: [{ label, data, backgroundColor: color, borderRadius: 4 }] },
    options: {
      indexAxis: horizontal ? "y" : "x",
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#456", autoSkip: false, maxRotation: 60, minRotation: 30, font: { size: 10 } } },
        y: { ticks: { color: "#456" }, beginAtZero: true },
      },
    },
  });
}

function makeLine(canvasId, labels, data, label, color) {
  destroy(canvasId);
  const ctx = document.getElementById(canvasId);
  charts[canvasId] = new Chart(ctx, {
    type: "line",
    data: { labels, datasets: [{ label, data, borderColor: color, backgroundColor: color + "33",
      fill: true, tension: 0.3, pointRadius: 1.5, borderWidth: 2 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: { ticks: { color: "#456", autoSkip: true, maxTicksLimit: 14 } }, y: { beginAtZero: true } },
    },
  });
}

async function loadCatalog() {
  catalog = await api("/api/catalog");
  allBiz = Object.keys(catalog).sort();
  $("#bizFilter").innerHTML = `<option value="">전체</option>` +
    allBiz.map(b => `<option>${b}</option>`).join("");
  $("#midFilter").innerHTML = `<option value="">전체</option>`;
}

function refreshMidOptions() {
  const biz = $("#bizFilter").value;
  const mids = biz ? Object.keys(catalog[biz] || {}).sort() : [];
  $("#midFilter").innerHTML = `<option value="">전체</option>` +
    mids.map(m => `<option>${m}</option>`).join("");
}

async function loadKPI() {
  const d = await api("/api/dashboard");
  $("#kpiTotal").textContent = d.total;
  $("#kpiToday").textContent = d.today;
  $("#kpiMonth").textContent = d.month;
  $("#kpiPending").textContent = d.pending;
  $("#kpiCompleted").textContent = d.completed;
}

async function loadBizChart() {
  const arr = await api("/api/stats/biz");
  arr.sort((a,b) => (b.avg_days ?? 0) - (a.avg_days ?? 0));
  makeBar("bizChart", arr.map(x => x.biz), arr.map(x => +(x.avg_days ?? 0).toFixed(1)),
    "평균 처리일수(일)", TEAL);
}

async function loadMidChart() {
  const biz = $("#bizFilter").value;
  const url = biz ? `/api/stats/mid?biz=${encodeURIComponent(biz)}` : "/api/stats/mid";
  const arr = await api(url);
  arr.sort((a,b) => (b.avg_days ?? 0) - (a.avg_days ?? 0));
  const top = arr.slice(0, 15);
  makeBar("midChart", top.map(x => x.mid), top.map(x => +(x.avg_days ?? 0).toFixed(1)),
    "평균 처리일수(일)", BLUE, true);
}

async function loadSubTable() {
  const biz = $("#bizFilter").value;
  const mid = $("#midFilter").value;
  const params = new URLSearchParams();
  if (biz) params.set("biz", biz);
  if (mid) params.set("mid", mid);
  const arr = await api(`/api/stats/sub${params.toString() ? "?"+params : ""}`);
  arr.sort((a,b) => (b.avg_days ?? 0) - (a.avg_days ?? 0));
  const tbody = document.querySelector("#subTable tbody");
  tbody.innerHTML = arr.slice(0, 80).map(x => `<tr>
    <td>${x.sub}</td>
    <td class="num">${x.avg_days?.toFixed(1) ?? "-"}</td>
    <td class="num">${x.median_days?.toFixed(1) ?? "-"}</td>
    <td class="num">${x.std_days?.toFixed(1) ?? "-"}</td>
    <td class="num">${x.n ?? "-"}</td>
  </tr>`).join("");
}

async function loadMonthly() {
  const arr = await api("/api/stats/monthly");
  // arr: [{ month: "2020-01", count: 1234 }, ...]
  makeLine("monthlyChart", arr.map(x => x.month), arr.map(x => x.count), "월 접수량", TEAL);
}

async function loadYearly() {
  const arr = await api("/api/stats/yearly");
  makeBar("yearlyChart", arr.map(x => x.year), arr.map(x => x.count), "연 접수량", ACCENT);
}

async function loadSeasonality() {
  const arr = await api("/api/stats/seasonality");
  // arr: [{ month: 1, count: ... }, ...] — normalize against mean
  if (!arr.length) return;
  const mean = arr.reduce((s,x) => s + x.count, 0) / arr.length;
  const labels = arr.map(x => `${x.month}월`);
  const data = arr.map(x => +(x.count / mean).toFixed(3));
  destroy("seasonalityChart");
  const ctx = document.getElementById("seasonalityChart");
  charts.seasonalityChart = new Chart(ctx, {
    type: "bar",
    data: { labels, datasets: [{ label: "혼잡 비율", data,
      backgroundColor: data.map(v => v >= 1.1 ? ACCENT : v >= 0.9 ? YELLOW : BLUE),
      borderRadius: 4 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, suggestedMax: 1.5,
        ticks: { callback: v => v.toFixed(2) } } },
    },
  });
}

async function loadOpsCharts() {
  const apps = await api("/api/applications");
  // ops bar — biz × status
  const byBiz = {};
  for (const a of apps) {
    if (!a.biz) continue;
    byBiz[a.biz] = byBiz[a.biz] || { pending: 0, completed: 0 };
    byBiz[a.biz][a.status] = (byBiz[a.biz][a.status] || 0) + 1;
  }
  const labels = Object.keys(byBiz);
  destroy("opsChart");
  const ctx = document.getElementById("opsChart");
  charts.opsChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "pending", data: labels.map(l => byBiz[l].pending), backgroundColor: YELLOW, borderRadius: 4 },
        { label: "completed", data: labels.map(l => byBiz[l].completed), backgroundColor: GREEN, borderRadius: 4 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: true, position: "top" } },
      scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } },
    },
  });

  // scatter — predicted vs actual
  const completed = apps.filter(a => a.completed_at && a.received_at && a.predicted_days != null);
  const points = completed.map(a => {
    const actual = (new Date(a.completed_at) - new Date(a.received_at)) / 86400000;
    return { x: a.predicted_days, y: +actual.toFixed(2), label: a.subcategory };
  });
  const maxV = Math.max(10, ...points.map(p => Math.max(p.x, p.y)));
  destroy("scatterChart");
  const ctx2 = document.getElementById("scatterChart");
  charts.scatterChart = new Chart(ctx2, {
    type: "scatter",
    data: {
      datasets: [
        { label: "실제 vs 예측", data: points, backgroundColor: ACCENT, pointRadius: 5 },
        { label: "perfect", type: "line", data: [{x:0,y:0},{x:maxV,y:maxV}],
          borderColor: "#aab", borderDash: [4,4], pointRadius: 0, fill: false },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: true },
        tooltip: { callbacks: { label: c => `${c.raw.label || ""} pred=${c.raw.x}일 actual=${c.raw.y}일` } },
      },
      scales: {
        x: { title: { display: true, text: "예측 처리일수" }, beginAtZero: true, max: maxV },
        y: { title: { display: true, text: "실제 처리일수" }, beginAtZero: true, max: maxV },
      },
    },
  });
}

async function refreshAll() {
  await Promise.all([
    loadKPI(),
    loadBizChart(),
    loadMidChart(),
    loadSubTable(),
    loadMonthly(),
    loadYearly(),
    loadSeasonality(),
    loadOpsCharts(),
  ]);
}

function bind() {
  $("#bizFilter").addEventListener("input", () => {
    refreshMidOptions();
    Promise.all([loadMidChart(), loadSubTable()]);
  });
  $("#midFilter").addEventListener("input", () => loadSubTable());
}

(async function init() {
  await loadCatalog();
  bind();
  await refreshAll();
})();
