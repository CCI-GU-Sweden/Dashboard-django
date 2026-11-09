(() => {
  const status = document.getElementById('overview-omero-status');
  const entries = [['filesets', 'filesets', 0, ''], ['storage_gb', 'storage', 2, ' GB'], ['daily_sek', 'billable', 2, ' SEK/day']];
  const format = (value, digits) => Number(value).toLocaleString(undefined, {minimumFractionDigits: digits, maximumFractionDigits: digits});
  fetch('/api/omero/overview-card', {credentials: 'same-origin'}).then(async response => {
    if (response.status === 403) throw new Error('An administrator must verify your OMERO group access.');
    if (!response.ok) throw new Error('Storage summary is currently unavailable.');
    return response.json();
  }).then(data => {
    if (!data.snapshot_date) {status.textContent = 'No storage snapshots are available.'; return;}
    status.textContent = `Snapshot: ${data.snapshot_date}`;
    for (const [key, id, digits, suffix] of entries) {
      const value = document.getElementById(`overview-omero-${id}`);
      const change = document.getElementById(`overview-omero-${id}-change`);
      const metric = data.metrics[key];
      if (!value || !metric) continue;
      value.textContent = metric.value == null ? '—' : `${format(metric.value, digits)}${suffix}`;
      if (metric.change_percent != null && data.comparison_date) {
        const sign = metric.change_percent >= 0 ? '+' : '';
        change.textContent = `${sign}${format(metric.change_percent, 1)}% vs ${data.comparison_date}`;
      } else change.textContent = 'No 30-day comparison';
    }
  }).catch(error => {status.textContent = error.message;});
})();
