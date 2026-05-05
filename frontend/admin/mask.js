// PII masking utilities (개인정보 비식별화)
// 이름: 가운데 글자 → '*' (예: 홍길동 → 홍*동, 김철 → 김*, 이몽룡 → 이*룡, 4자: 남궁민수 → 남*수* 처리: 가운데 모두 마스킹)
// 휴대폰/전화: 가운데 4자리 → '****'
window.PiiMask = (function () {
  let on = localStorage.getItem("piiMask") !== "0"; // 기본 ON

  function isOn() { return on; }
  function setOn(v) { on = !!v; localStorage.setItem("piiMask", on ? "1" : "0"); }

  function maskName(s) {
    if (!on || !s) return s ?? "";
    s = String(s).trim();
    if (s.length <= 1) return s;
    if (s.length === 2) return s[0] + "*";
    // 가운데 모든 글자를 *로 (3자: 1자, 4자: 2자, 5자: 3자 ...)
    const stars = "*".repeat(s.length - 2);
    return s[0] + stars + s[s.length - 1];
  }

  function maskPhone(s) {
    if (!on || !s) return s ?? "";
    s = String(s).trim();
    // 숫자만 추출해서 길이 확인
    const digits = s.replace(/\D/g, "");
    if (digits.length < 7) return s;
    // 한국 휴대폰: 010-1234-5678 → 010-****-5678
    // 일반: 02-123-4567 / 02-1234-5678 / 031-123-4567 → 가운데 자리(국번) 마스킹
    const parts = s.split(/[-\s.]/);
    if (parts.length === 3) {
      return `${parts[0]}-${"*".repeat(parts[1].length)}-${parts[2]}`;
    }
    // 구분자 없음 — 11자리(010xxxxxxxx) 또는 10자리 처리
    if (digits.length === 11) return `${digits.slice(0,3)}-****-${digits.slice(7)}`;
    if (digits.length === 10) return `${digits.slice(0,3)}-***-${digits.slice(6)}`;
    // fallback: 가운데 절반 마스킹
    const head = Math.floor(digits.length / 3);
    const tail = head;
    return digits.slice(0, head) + "*".repeat(digits.length - head - tail) + digits.slice(-tail);
  }

  function maskEmail(s) {
    if (!on || !s) return s ?? "";
    const [u, d] = String(s).split("@");
    if (!d) return s;
    if (u.length <= 2) return u[0] + "*@" + d;
    return u.slice(0, 2) + "*".repeat(u.length - 2) + "@" + d;
  }

  // 단축 (체크박스 등에 바인딩)
  function bindToggle(el, onChange) {
    if (!el) return;
    el.checked = on;
    el.addEventListener("change", () => {
      setOn(el.checked);
      if (onChange) onChange();
    });
  }

  return { isOn, setOn, maskName, maskPhone, maskEmail, bindToggle };
})();
