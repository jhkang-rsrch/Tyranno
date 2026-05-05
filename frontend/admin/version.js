// Footer version label
(async function () {
  try {
    const r = await fetch("/api/version");
    if (!r.ok) return;
    const d = await r.json();
    const el = document.getElementById("versionLabel");
    if (!el) return;
    const sha = (d.git || "").slice(0, 7) || "dev";
    const built = (d.built_at || "").slice(0, 10) || "?";
    el.textContent = `v${d.version || "0"} · ${sha} · ${built}`;
  } catch {}
})();
