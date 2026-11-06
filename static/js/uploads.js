(() => {
  const period = document.getElementById('period');
  async function load() {
    const status = document.getElementById('uploads-status');
    if (status) status.textContent = 'Loading…';
    try {
      const response = await fetch(`/api/uploads/summary?period=${encodeURIComponent(period?.value || '30')}`, { credentials: 'same-origin' });
      if (!response.ok) throw new Error('Upload data is currently unavailable.');
      const data = await response.json();
      const set = (id, value) => { const element = document.getElementById(id); if (element) element.textContent = value; };
      set('overview-files', data.total_files.toLocaleString());
      set('overview-size', `${data.total_size_gb.toLocaleString()} GB`);
      set('overview-scope', data.top_scope_files?.name || '—');
      document.querySelectorAll('[data-stat]').forEach((element) => {
        const value = data[element.dataset.stat];
        element.textContent = value && typeof value === 'object' ? (value.name || value.date || '—') : (value ?? '—').toLocaleString();
      });
      const history = document.getElementById('uploads-history');
      if (history) {
        history.replaceChildren();
        const maximum = Math.max(1, ...data.history.map(item => item.count));
        for (const item of data.history) {
          const row = document.createElement('div');
          row.className = 'upload-history-row';
          const label = document.createElement('span');
          label.textContent = item.date;
          const track = document.createElement('span');
          track.className = 'upload-history-track';
          const bar = document.createElement('span');
          bar.className = 'upload-history-bar';
          bar.style.width = `${item.count / maximum * 100}%`;
          track.append(bar);
          const count = document.createElement('span');
          count.textContent = item.count.toLocaleString();
          row.append(label, track, count);
          history.append(row);
        }
        status.textContent = data.history.length ? 'Daily totals for the selected period.' : 'No uploads in this period.';
      }
    } catch (error) {
      if (status) status.textContent = error.message;
    }
  }
  period?.addEventListener('change', load);
  load();
})();
