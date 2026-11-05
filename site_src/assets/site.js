// Theme toggle (persisted per viewer) + re-theming Plotly charts and Mermaid diagrams.
(function () {
  const root = document.documentElement;
  try { const t = localStorage.getItem("theme"); if (t) root.setAttribute("data-theme", t); } catch (e) {}
  const DARK = {"#2a78d6": "#3987e5", "#eb6834": "#d95926", "#1baf7a": "#199e70", "#eda100": "#c98500",
                "#e87ba4": "#d55181", "#008300": "#008300", "#6250d6": "#9085e9"};
  const LIGHT = Object.fromEntries(Object.entries(DARK).map(([k, v]) => [v, k]));
  function isDark() {
    const t = root.getAttribute("data-theme");
    if (t) return t === "dark";
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function css(v) { return getComputedStyle(root).getPropertyValue(v).trim(); }
  function themeCharts() {
    if (!window.Plotly) return;
    const dark = isDark(), map = dark ? DARK : LIGHT, text = css("--text"), text2 = css("--text-2");
    const grid = dark ? "rgba(195,194,183,0.16)" : "rgba(82,81,78,0.18)";
    const conn = dark ? "rgba(195,194,183,0.38)" : "rgba(82,81,78,0.35)";  // dumbbell connectors
    document.querySelectorAll(".js-plotly-plot").forEach(function (gd) {
      const colors = gd.data.map(function (tr) {
        const c = (tr.marker && tr.marker.color) || (tr.line && tr.line.color);
        return typeof c === "string" ? (map[c.toLowerCase()] || c) : c;
      });
      gd.data.forEach(function (tr, i) {
        if (typeof colors[i] !== "string") return;
        if (tr.hoverinfo === "skip" && tr.line) { window.Plotly.restyle(gd, {"line.color": conn}, [i]); return; }
        const upd = {};
        if (tr.marker) {
          upd["marker.color"] = colors[i];
          const open = String(tr.marker.symbol || "").indexOf("open") !== -1;
          upd["marker.line.color"] = open ? colors[i] : css("--surface");  // open symbols draw with their line
        }
        if (tr.line) upd["line.color"] = colors[i];
        if (tr.textfont) upd["textfont.color"] = text2;
        window.Plotly.restyle(gd, upd, [i]);
      });
      const lay = { "title.font.color": text, "font.color": text2, "legend.font.color": text2 };
      Object.keys(gd.layout).filter(function (k) { return /^[xy]axis\d*$/.test(k); }).forEach(function (k) {
        lay[k + ".gridcolor"] = grid; lay[k + ".linecolor"] = grid;
        lay[k + ".tickfont.color"] = text2; lay[k + ".title.font.color"] = text2;
      });
      (gd.layout.annotations || []).forEach(function (a, j) { lay["annotations[" + j + "].font.color"] = text2; });
      window.Plotly.relayout(gd, lay);
    });
  }
  window.__themeCharts = themeCharts;
  document.addEventListener("DOMContentLoaded", function () {
    const btn = document.getElementById("theme-btn");
    function label() { if (btn) btn.textContent = isDark() ? "Light mode" : "Dark mode"; }
    label();
    if (btn) btn.addEventListener("click", function () {
      const next = isDark() ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("theme", next); } catch (e) {}
      label(); themeCharts();
      if (window.__renderMermaid) window.__renderMermaid();
    });
    themeCharts();
    if (window.matchMedia) window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () { label(); themeCharts(); });
  });
})();
