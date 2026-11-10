(() => {
  const key = 'cci-dashboard-theme';
  const system = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  let preference = null;
  try {const saved = localStorage.getItem(key); if (saved === 'light' || saved === 'dark') preference = saved;} catch (_) {}
  const mode = () => preference || (system?.matches ? 'dark' : 'light');
  const colors = () => mode() === 'dark' ? {text: '#cbd5e1', grid: '#39485d'} : {text: '#475569', grid: '#e2e8f0'};
  const plotlyLayout = () => {const palette = colors(); return {paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: {color: palette.text}, xaxis: {gridcolor: palette.grid, zerolinecolor: palette.grid}, yaxis: {gridcolor: palette.grid, zerolinecolor: palette.grid}};};
  function apply() {
    const active = mode(); document.documentElement.dataset.theme = active;
    const button = document.getElementById('theme-toggle');
    if (button) {button.textContent = active === 'dark' ? '☀ Light mode' : '☾ Dark mode'; button.setAttribute('aria-label', active === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'); button.setAttribute('aria-pressed', String(active === 'dark'));}
    if (window.Plotly?.relayout) {const palette = colors(); document.querySelectorAll('.js-plotly-plot').forEach(chart => {if (chart.data) window.Plotly.relayout(chart, {'paper_bgcolor': 'transparent', 'plot_bgcolor': 'transparent', 'font.color': palette.text, 'xaxis.gridcolor': palette.grid, 'xaxis.zerolinecolor': palette.grid, 'yaxis.gridcolor': palette.grid, 'yaxis.zerolinecolor': palette.grid});});}
  }
  window.dashboardTheme = {plotlyLayout};
  apply();
  document.addEventListener('DOMContentLoaded', () => {apply(); document.getElementById('theme-toggle')?.addEventListener('click', () => {preference = mode() === 'dark' ? 'light' : 'dark'; try {localStorage.setItem(key, preference);} catch (_) {} apply();});});
  system?.addEventListener?.('change', () => {if (!preference) apply();});
  window.addEventListener('storage', event => {if (event.key === key) {preference = event.newValue === 'light' || event.newValue === 'dark' ? event.newValue : null; apply();}});
})();
