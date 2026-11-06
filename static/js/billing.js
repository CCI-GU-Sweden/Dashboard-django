document.getElementById('billing-form').addEventListener('submit', async event => {
  event.preventDefault();
  const status = document.getElementById('billing-status');
  const rows = document.getElementById('billing-rows');
  const query = new URLSearchParams({startDate: document.getElementById('start').value, endDate: document.getElementById('end').value});
  status.textContent = 'Loading…';
  try {
    const response = await fetch(`/api/omero/billing?${query}`, {credentials: 'same-origin'});
    if (!response.ok) throw new Error('Billing data is unavailable or the date range is invalid.');
    const data = await response.json();
    rows.replaceChildren();
    for (const group of data.groups) {
      const row = document.createElement('tr');
      for (const value of [group.group_name, group.snapshot_days, group.billable_gb_days.toFixed(2), group.total_sek.toFixed(2)]) {
        const cell = document.createElement('td'); cell.textContent = value ?? '—'; row.append(cell);
      }
      rows.append(row);
    }
    status.textContent = `${data.groups.length} groups · inclusive dates`;
  } catch (error) { status.textContent = error.message; }
});
