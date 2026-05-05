// Admin DB console — table view with inline cell edit + delete + CSV export.
const $ = (s) => document.querySelector(s);

// Column definitions: [key, label, kind, options?]
//   kind: text | number | datetime | select | textarea | readonly
const COLS_BASIC = [
  ["id", "ID", "readonly"],
  ["status", "상태", "select", ["pending","completed"]],
  ["biz", "사업구분", "text"],
  ["category", "중분류", "text"],
  ["subcategory", "소분류", "text"],
  ["sample_name", "시료명", "text"],
  ["received_at", "접수일시", "datetime"],
  ["completed_at", "완료일시", "datetime"],
  ["predicted_days", "예측일수", "number"],
  ["predicted_complete_at", "예측완료일", "datetime"],
  ["company", "회사명", "text"],
  ["applicant_name", "신청인", "text"],
  ["mobile", "휴대폰", "text"],
  ["__actions__", "관리", "actions"],
];

const COLS_RAW = [
  ["id", "ID", "readonly"],
  ["status", "상태", "select", ["pending","completed"]],
  ["biz", "사업구분", "text"],
  ["category", "중분류", "text"],
  ["subcategory", "소분류", "text"],
  ["sample_name", "시료명", "text"],
  ["received_at", "접수일시", "datetime"],
  ["completed_at", "완료일시", "datetime"],
  ["predicted_days", "예측일수", "number"],
  ["predicted_complete_at", "예측완료일", "datetime"],
  ["company", "회사명", "text"],
  ["business_no", "사업자번호", "text"],
  ["address", "회사주소", "textarea"],
  ["ceo", "대표자", "text"],
  ["applicant_name", "신청인", "text"],
  ["phone", "전화", "text"],
  ["mobile", "휴대폰", "text"],
  ["email", "이메일", "text"],
  ["fax", "FAX", "text"],
  ["payment", "결제", "text"],
  ["report", "성적서", "text"],
  ["return_method", "반환방법", "text"],
  ["return_address", "반환주소", "textarea"],
  ["notes", "특이사항", "textarea"],
  ["__actions__", "관리", "actions"],
];

let cols = COLS_BASIC;
let rows = [];
let editingCell = null; // { id, key, original }

async function api(path, init) {
  const r = await fetch(path, init);
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  if (r.status === 204) return null;
  return r.json();
}

function flat(a) {
  return {
    id: a.id, status: a.status,
    biz: a.biz, category: a.category, subcategory: a.subcategory,
    sample_name: a.sample_name,
    received_at: a.received_at, completed_at: a.completed_at,
    predicted_days: a.predicted_days,
    predicted_complete_at: a.predicted_complete_at,
    company: a.applicant?.company,
    business_no: a.applicant?.business_no,
    address: a.applicant?.address,
    ceo: a.applicant?.ceo,
    applicant_name: a.applicant?.name,
    phone: a.applicant?.phone,
    mobile: a.applicant?.mobile,
    email: a.applicant?.email,
    fax: a.applicant?.fax,
    payment: a.request?.payment,
    report: a.request?.report,
    return_method: a.request?.return_method,
    return_address: a.request?.return_address,
    notes: a.request?.notes,
  };
}

function fmtDT(v) {
  if (!v) return "";
  return v.replace("T", " ").slice(0, 16);
}
function fmtCell(key, v) {
  if (v == null || v === "") return "<span style='color:#aab'>-</span>";
  if (key === "status") {
    const cls = v === "completed" ? "pill-completed" : "pill-pending";
    return `<span class="pill ${cls}">${v}</span>`;
  }
  if (["received_at","completed_at","predicted_complete_at"].includes(key)) return fmtDT(v);
  // 개인정보 마스킹
  if (key === "applicant_name" || key === "ceo") v = PiiMask.maskName(v);
  else if (key === "phone" || key === "mobile" || key === "fax") v = PiiMask.maskPhone(v);
  else if (key === "email") v = PiiMask.maskEmail(v);
  if (typeof v === "string" && v.length > 40) return v.slice(0,40) + "…";
  return String(v);
}

function renderHead() {
  $("#dbHead").innerHTML = "<tr>" +
    cols.map(c => `<th>${c[1]}</th>`).join("") + "</tr>";
}

function applyFilter(all) {
  const status = $("#filterStatus").value;
  const q = $("#filterText").value.trim().toLowerCase();
  return all.filter(r => {
    if (status && r.status !== status) return false;
    if (!q) return true;
    return Object.values(r).some(v => v != null && String(v).toLowerCase().includes(q));
  });
}

function renderBody() {
  const filtered = applyFilter(rows);
  $("#dbSummary").textContent = `${filtered.length} / ${rows.length} 건`;
  if (filtered.length === 0) {
    $("#dbBody").innerHTML = `<tr><td colspan="${cols.length}" style="padding:30px; text-align:center; color:#789;">표시할 행이 없습니다.</td></tr>`;
    return;
  }
  $("#dbBody").innerHTML = filtered.map(r => {
    const tds = cols.map(c => {
      const [key, _label, kind] = c;
      if (kind === "actions") {
        return `<td><div class="row-actions">
          <button class="btn-danger" data-del="${r.id}" type="button">🗑 삭제</button>
        </div></td>`;
      }
      if (kind === "readonly") {
        return `<td>${r[key] ?? ""}</td>`;
      }
      return `<td class="editable" data-id="${r.id}" data-key="${key}" data-kind="${kind}">${fmtCell(key, r[key])}</td>`;
    });
    return `<tr data-row="${r.id}">${tds.join("")}</tr>`;
  }).join("");
}

function startEdit(td) {
  if (editingCell) commitEdit(true);
  const id = Number(td.dataset.id);
  const key = td.dataset.key;
  const kind = td.dataset.kind;
  const row = rows.find(r => r.id === id);
  if (!row) return;
  const original = row[key];
  editingCell = { id, key, original, td };
  td.classList.add("editing");
  let html;
  if (kind === "select") {
    const options = (cols.find(c => c[0] === key) || [])[3] || [];
    html = `<select autofocus>${options.map(o => `<option value="${o}" ${o===original?"selected":""}>${o}</option>`).join("")}</select>`;
  } else if (kind === "textarea") {
    html = `<input type="text" value="${(original??"").toString().replace(/"/g,"&quot;")}" autofocus />`;
  } else if (kind === "number") {
    html = `<input type="number" value="${original ?? ""}" autofocus />`;
  } else if (kind === "datetime") {
    html = `<input type="datetime-local" value="${original ? original.slice(0,16) : ""}" autofocus />`;
  } else {
    html = `<input type="text" value="${(original??"").toString().replace(/"/g,"&quot;")}" autofocus />`;
  }
  td.innerHTML = html;
  const ctrl = td.querySelector("input,select");
  ctrl.focus();
  if (ctrl.select) ctrl.select?.();
  ctrl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); commitEdit(false); }
    else if (e.key === "Escape") { e.preventDefault(); cancelEdit(); }
  });
  ctrl.addEventListener("blur", () => commitEdit(false));
}

function cancelEdit() {
  if (!editingCell) return;
  const { td, key, original } = editingCell;
  td.classList.remove("editing");
  td.innerHTML = fmtCell(key, original);
  editingCell = null;
}

async function commitEdit(silent) {
  if (!editingCell) return;
  const { id, key, original, td } = editingCell;
  const ctrl = td.querySelector("input,select");
  if (!ctrl) { editingCell = null; return; }
  let raw = ctrl.value;
  let value;
  if (raw === "") {
    value = null;
  } else if (key === "predicted_days") {
    value = parseInt(raw, 10);
  } else if (["received_at","completed_at","predicted_complete_at"].includes(key)) {
    value = new Date(raw).toISOString();
  } else {
    value = raw;
  }
  editingCell = null;
  td.classList.remove("editing");
  if (value === original) {
    td.innerHTML = fmtCell(key, original);
    return;
  }
  try {
    await api(`/api/applications/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [key]: value }),
    });
    const row = rows.find(r => r.id === id);
    if (row) row[key] = value;
    td.innerHTML = fmtCell(key, value);
    td.style.background = "#d4edda";
    setTimeout(() => td.style.background = "", 600);
  } catch (e) {
    if (!silent) alert(`저장 실패: ${e.message}`);
    td.innerHTML = fmtCell(key, original);
  }
}

async function deleteRow(id) {
  if (!confirm(`#${id} 행을 영구 삭제하시겠습니까?`)) return;
  try {
    await api(`/api/applications/${id}`, { method: "DELETE" });
    rows = rows.filter(r => r.id !== id);
    renderBody();
  } catch (e) {
    alert(`삭제 실패: ${e.message}`);
  }
}

async function reload() {
  const apps = await api("/api/applications");
  rows = apps.map(flat).sort((a,b) => b.id - a.id);
  renderBody();
}

function exportCSV() {
  const filtered = applyFilter(rows);
  const keys = cols.filter(c => c[2] !== "actions").map(c => c[0]);
  const header = keys.join(",");
  const lines = filtered.map(r => keys.map(k => {
    let v = r[k];
    if (v == null) return "";
    // CSV에도 마스킹 적용 (보안)
    if (k === "applicant_name" || k === "ceo") v = PiiMask.maskName(v);
    else if (k === "phone" || k === "mobile" || k === "fax") v = PiiMask.maskPhone(v);
    else if (k === "email") v = PiiMask.maskEmail(v);
    const s = String(v).replace(/"/g, '""');
    return /[",\n]/.test(s) ? `"${s}"` : s;
  }).join(","));
  const blob = new Blob(["\ufeff" + [header, ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `applications_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function exportXLSX() {
  if (typeof XLSX === "undefined") { alert("Excel 라이브러리(xlsx)를 불러오지 못했습니다."); return; }
  const filtered = applyFilter(rows);
  const keys = cols.filter(c => c[2] !== "actions").map(c => c[0]);
  const labels = cols.filter(c => c[2] !== "actions").map(c => c[1]);
  const data = filtered.map(r => {
    const o = {};
    keys.forEach((k, i) => {
      let v = r[k];
      if (v == null) v = "";
      if (k === "applicant_name" || k === "ceo") v = PiiMask.maskName(v);
      else if (k === "phone" || k === "mobile" || k === "fax") v = PiiMask.maskPhone(v);
      else if (k === "email") v = PiiMask.maskEmail(v);
      o[labels[i]] = v;
    });
    return o;
  });
  const ws = XLSX.utils.json_to_sheet(data, { header: labels });
  // 컬럼 너비 자동 추정
  ws["!cols"] = labels.map((l, i) => {
    const max = Math.max(l.length, ...data.map(d => String(d[l] ?? "").length));
    return { wch: Math.min(40, Math.max(8, max + 2)) };
  });
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "applications");
  const stamp = new Date().toISOString().slice(0, 10);
  XLSX.writeFile(wb, `applications_${stamp}.xlsx`);
}

function bind() {
  $("#dbBody").addEventListener("click", (e) => {
    const del = e.target.closest("[data-del]");
    if (del) { deleteRow(Number(del.dataset.del)); return; }
    const td = e.target.closest("td.editable");
    if (td && !td.classList.contains("editing")) startEdit(td);
  });
  $("#filterStatus").addEventListener("input", renderBody);
  $("#filterText").addEventListener("input", renderBody);
  $("#reloadBtn").addEventListener("click", reload);
  $("#exportBtn").addEventListener("click", exportCSV);
  $("#exportXlsxBtn").addEventListener("click", exportXLSX);
  $("#rawToggle").addEventListener("click", () => {
    cols = cols === COLS_BASIC ? COLS_RAW : COLS_BASIC;
    document.querySelector("table.db-table").classList.toggle("raw-mode", cols === COLS_RAW);
    $("#rawToggle").textContent = cols === COLS_RAW ? "기본 컬럼만" : "전체 컬럼 보기";
    renderHead(); renderBody();
  });
  PiiMask.bindToggle($("#piiToggle"), renderBody);
}

(async function init() {
  renderHead();
  bind();
  await reload();
})();
