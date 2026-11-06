(() => {
  const $ = id => document.getElementById(id);
  const plotConfig = {responsive: true, displaylogo: false};
  const layout = {paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: {color: '#475569'}, margin: {l: 65, r: 25, t: 25, b: 60}, legend: {orientation: 'h'}};
  async function get(url) {
    const response = await fetch(url, {credentials: 'same-origin'});
    if (!response.ok) throw new Error('Data is unavailable or the selected filters are invalid.');
    return response.json();
  }
  async function history() {
    const period = $('history-period').value;
    document.querySelectorAll('.history-custom').forEach(el => {el.hidden = period !== 'custom';});
    const query = new URLSearchParams({period, group_id: $('history-group')?.value || 'all', metric: $('history-metric')?.value || 'bytes'});
    if (period === 'custom') {query.set('start', $('history-start').value); query.set('end', $('history-end').value);}
    try {
      const data = await get(`/api/omero/history?${query}`);
      const dates = data.history.map(row => row.date);
      const series = (key, name, color) => ({type: 'scatter', mode: 'lines', name, x: dates, y: data.history.map(row => row[key]), line: {color, width: 2}, fill: 'tozeroy', fillcolor: color === '#3273dc' ? 'rgba(50,115,220,.12)' : 'rgba(35,209,160,.12)', hovertemplate: '%{x}<br>%{y:.2f}<extra>%{fullData.name}</extra>'});
      await Plotly.react('omeroChart', [series('total', 'Total', '#3273dc'), series('billable', 'Billable', '#23d1a0')], {...layout, xaxis: {title: 'Date'}, yaxis: {title: data.metric === 'ore' ? 'Daily charge (öre)' : 'Storage (GB)', rangemode: 'tozero'}}, plotConfig);
      $('history-status').textContent = data.history.length ? '' : 'No storage snapshots for this period.';
    } catch (error) {$('history-status').textContent = error.message;}
  }
  for (const id of ['history-period', 'history-start', 'history-end', 'history-group', 'history-metric']) $(id)?.addEventListener('change', history);
  $('refresh').addEventListener('click', history);
  history();

  let groups = [];
  async function ranking() {
    const selected = groups.slice(0, Number($('ranking-limit').value)).reverse();
    const trace = (key, name, color) => ({type: 'bar', orientation: 'h', name, x: selected.map(g => g[key]), y: selected.map(g => g.name || g.id), customdata: selected.map(g => g.id), marker: {color}, hovertemplate: '%{y}<br>%{x:.2f} GB<extra>%{fullData.name}</extra>'});
    await Plotly.react('groupRankingChart', [trace('billable', 'Billable', '#3273dc'), trace('free', 'Free', '#23d1a0')], {...layout, height: Math.max(350, selected.length * 28 + 100), barmode: 'stack', margin: {l: 180, r: 25, t: 20, b: 60}, xaxis: {title: 'Storage (GB)'}}, plotConfig);
    const chart = $('groupRankingChart');
    chart.removeAllListeners('plotly_click');
    chart.on('plotly_click', event => {
      const group = String(event.points[0].customdata);
      for (const id of ['history-group', 'group_id']) {if ($(id)) $(id).value = group;}
      history(); $('storage-search').requestSubmit();
    });
  }
  if ($('ranking-limit')) {
    $('ranking-limit').addEventListener('change', ranking);
    get('/api/omero/overview').then(data => {
      document.querySelectorAll('[data-metric]').forEach(el => {el.textContent = Number(data.metrics[el.dataset.metric] || 0).toLocaleString(undefined, {maximumFractionDigits: 2});});
      groups = data.groups; return ranking();
    }).catch(() => {$('groupRankingChart').textContent = 'Storage summary is currently unavailable.';});
    get('/api/omero/groups').then(data => {for (const group of data.groups) {const option = document.createElement('option'); option.value = group.id; option.textContent = group.name || group.id; $('history-group').append(option); if ($('policy-group')) $('policy-group').append(option.cloneNode(true));}}).catch(() => {});
  }
  function appendRow(parent, values) {
    const row = document.createElement('tr');
    values.forEach(value => {const cell = document.createElement('td'); cell.textContent = value ?? '—'; row.append(cell);});
    parent.append(row);
  }
  async function adminTable(kind) {
    try {
      const data = await get(`/api/omero/admin/${kind}`);
      const rows = $(`${kind}-rows`); rows.replaceChildren();
      const keys = kind === 'policies' ? ['group_name', 'policy_type', 'grace_days', 'billing_grace_days', 'rate_ore_per_gb_day', 'valid_from', 'valid_until', 'notes'] : ['status', 'started_at', 'finished_at', 'filesets_seen', 'filesets_inserted', 'filesets_updated', 'filesets_marked_deleted', 'snapshots_written', 'deletion_suppressed', 'error_message'];
      data.rows.forEach(row => appendRow(rows, keys.map(key => row[key])));
      $(`${kind}-status`).textContent = `${data.rows.length} records`;
    } catch (error) {$(`${kind}-status`).textContent = error.message;}
  }
  document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => {
    document.querySelectorAll('[data-tab]').forEach(tab => {tab.parentElement.classList.toggle('is-active', tab === button); $(`panel-${tab.dataset.tab}`).hidden = tab !== button;});
    if (['policies', 'health'].includes(button.dataset.tab)) adminTable(button.dataset.tab);
    if (button.dataset.tab === 'billing' && $('billingChart').data) Plotly.Plots.resize('billingChart');
  }));
  $('policy-form')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    try {
      const response = await fetch('/api/omero/policies', {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value}, body: JSON.stringify(data)});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Unable to save policy.');
      await adminTable('policies');
      $('policies-status').textContent = 'Policy scheduled.';
    } catch (error) {$('policies-status').textContent = error.message;}
  });
  let billing = [];
  $('billing-form')?.addEventListener('submit', async event => {
    event.preventDefault();
    const query = new URLSearchParams({startDate: $('start').value, endDate: $('end').value, limit: $('billing-limit').value});
    try {
      const data = await get(`/api/omero/billing?${query}`); billing = data.groups;
      $('billing-rows').replaceChildren(); billing.forEach(g => appendRow($('billing-rows'), [g.group_name, g.snapshot_days, g.billable_gb_days.toFixed(2), g.total_sek.toFixed(2)]));
      $('billing-status').textContent = `${billing.length} groups · inclusive dates`;
      const reversed = [...billing].reverse();
      await Plotly.react('billingChart', [{type: 'bar', orientation: 'h', x: reversed.map(g => g.total_sek), y: reversed.map(g => g.group_name), marker: {color: '#3273dc'}}], {...layout, height: Math.max(350, reversed.length * 28 + 100), margin: {l: 180, r: 25, t: 20, b: 60}, xaxis: {title: 'Total SEK'}}, plotConfig);
    } catch (error) {$('billing-status').textContent = error.message;}
  });
  $('billing-export')?.addEventListener('click', () => {
    const csv = value => `"${String(value ?? '').replace(/^[=+@\-\t\r]/, "'$&").replace(/"/g, '""')}"`;
    const rows = [['Group', 'Snapshot days', 'Billable GB-days', 'Total SEK'], ...billing.map(g => [g.group_name, g.snapshot_days, g.billable_gb_days, g.total_sek])];
    const url = URL.createObjectURL(new Blob([rows.map(row => row.map(csv).join(',')).join('\r\n')], {type: 'text/csv;charset=utf-8'}));
    const link = document.createElement('a'); link.href = url; link.download = 'omero-billing.csv'; link.click(); URL.revokeObjectURL(url);
  });
})();
