(() => {
  const $ = id => document.getElementById(id);
  const plotConfig = {responsive: true, displaylogo: false};
  const layout = () => ({paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: {color: '#475569'}, margin: {l: 65, r: 25, t: 25, b: 60}, legend: {orientation: 'h'}, ...(globalThis.dashboardTheme?.plotlyLayout() || {})});
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
      const theme = layout();
      await Plotly.react('omeroChart', [series('total', 'Total', '#3273dc'), series('billable', 'Billable', '#23d1a0')], {...theme, margin: {l: 85, r: 25, t: 25, b: 80}, xaxis: {...theme.xaxis, title: {text: 'Date'}, automargin: true}, yaxis: {...theme.yaxis, title: {text: data.metric === 'ore' ? 'Daily charge (öre)' : 'Storage (GB)'}, rangemode: 'tozero', automargin: true}}, plotConfig);
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
    const theme = layout();
    await Plotly.react('groupRankingChart', [trace('billable', 'Billable', '#3273dc'), trace('free', 'Free', '#23d1a0')], {...theme, height: Math.max(350, selected.length * 28 + 100), barmode: 'stack', margin: {l: 180, r: 25, t: 20, b: 60}, xaxis: {...theme.xaxis, title: 'Storage (GB)'}}, plotConfig);
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
    get('/api/omero/groups').then(data => {for (const group of data.groups) {const option = document.createElement('option'); option.value = group.id; option.textContent = group.name || group.id; $('history-group').append(option);}}).catch(() => {});
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
      if (kind === 'policies') {
        const groups = new Map();
        data.rows.forEach(item => {const id = String(item.group_id); if (!groups.has(id)) groups.set(id, []); groups.get(id).push(item);});
        groups.forEach(history => {
          history.sort((a, b) => String(b.valid_from).localeCompare(String(a.valid_from)));
          const item = history[0];
          appendRow(rows, ['', item.group_name, item.policy_type, item.grace_days, item.billing_grace_days, item.rate_ore_per_gb_day, item.valid_from, item.valid_until, item.notes]);
          const mainRow = rows.lastElementChild;
          const toggle = document.createElement('button'); toggle.type = 'button'; toggle.className = 'fileset-detail-button'; toggle.textContent = '›'; toggle.setAttribute('aria-expanded', 'false'); toggle.setAttribute('aria-label', `Show policy history for ${item.group_name || item.group_id}`);
          mainRow.firstElementChild.append(toggle);
          toggle.addEventListener('click', () => {
            if (toggle.getAttribute('aria-expanded') === 'true') {mainRow.nextElementSibling.remove(); toggle.setAttribute('aria-expanded', 'false'); toggle.textContent = '›'; toggle.setAttribute('aria-label', `Show policy history for ${item.group_name || item.group_id}`); return;}
            const detail = document.createElement('tr'); const cell = document.createElement('td'); cell.colSpan = 10; const wrapper = document.createElement('div'); wrapper.className = 'policy-history';
            const title = document.createElement('strong'); title.textContent = `Policy history for ${item.group_name || item.group_id}`; wrapper.append(title);
            const table = document.createElement('table'); table.className = 'policy-history-table'; const thead = document.createElement('thead'); appendRow(thead, ['Policy', 'From', 'Until', 'Rate (öre/GB/day)', 'Status', 'Notes']); table.append(thead);
            const tbody = document.createElement('tbody'); const today = new Intl.DateTimeFormat('sv-SE', {timeZone: 'Europe/Stockholm', year: 'numeric', month: '2-digit', day: '2-digit'}).format(new Date());
            history.forEach(entry => appendRow(tbody, [entry.policy_type, entry.valid_from, entry.valid_until, entry.rate_ore_per_gb_day, entry.valid_from > today ? 'Upcoming' : entry.valid_until && entry.valid_until < today ? 'Expired' : 'Active', entry.notes]));
            table.append(tbody); wrapper.append(table); cell.append(wrapper); detail.append(cell); mainRow.after(detail); toggle.setAttribute('aria-expanded', 'true'); toggle.textContent = '⌄'; toggle.setAttribute('aria-label', `Hide policy history for ${item.group_name || item.group_id}`);
          });
          const cell = document.createElement('td'); const button = document.createElement('button'); button.type = 'button'; button.className = 'button is-small is-link is-light'; button.textContent = '✎ Edit';
          button.addEventListener('click', () => {
            const form = $('policy-form'); form.hidden = false; form.elements.group_id.value = item.group_id; form.elements.policy_type.value = item.policy_type; form.elements.grace_days.value = item.grace_days ?? 0; form.elements.billing_grace_days.value = item.billing_grace_days ?? 0; form.elements.rate_ore_per_gb_day.value = item.rate_ore_per_gb_day ?? 0; form.elements.notes.value = item.notes || ''; form.elements.valid_from.value = ''; $('policy-form-title').textContent = `Schedule a new policy for ${item.group_name || item.group_id}`; form.elements.valid_from.focus();
          });
          cell.append(button); mainRow.append(cell);
        });
      } else {
        const shown = data.rows.slice(0, Number($('health-limit').value));
        shown.forEach(item => {
          const start = item.started_at ? new Date(item.started_at) : null; const finish = item.finished_at ? new Date(item.finished_at) : null;
          const seconds = start && finish ? Math.max(0, Math.round((finish - start) / 1000)) : null;
          const notes = [item.deletion_suppressed ? 'Deletion suppressed' : '', item.error_message || ''].filter(Boolean).join(' · ') || '—';
          appendRow(rows, ['', start ? start.toLocaleString() : '—', seconds === null ? '—' : seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`, item.filesets_seen, `+${item.filesets_inserted ?? 0} / ~${item.filesets_updated ?? 0} / −${item.filesets_marked_deleted ?? 0}`, item.snapshots_written, notes]);
          const badge = document.createElement('span'); const state = String(item.status || '').toLowerCase(); badge.className = `health-status ${['success', 'running', 'partial', 'failed'].includes(state) ? `is-${state}` : 'is-partial'}`; badge.textContent = item.status || 'Unknown'; rows.lastElementChild.firstElementChild.append(badge);
        });
      }
      $(`${kind}-status`).textContent = data.rows.length ? '' : 'No records available.';
    } catch (error) {$(`${kind}-status`).textContent = error.message;}
  }
  document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => {
    document.querySelectorAll('[data-tab]').forEach(tab => {tab.parentElement.classList.toggle('is-active', tab === button); $(`panel-${tab.dataset.tab}`).hidden = tab !== button;});
    if (['policies', 'health'].includes(button.dataset.tab)) adminTable(button.dataset.tab);
    if (button.dataset.tab === 'billing') {if ($('billingChart').data) Plotly.Plots.resize('billingChart'); else $('billing-form').requestSubmit();}
  }));
  $('health-limit')?.addEventListener('change', () => adminTable('health'));
  $('policy-cancel')?.addEventListener('click', () => {$('policy-form').hidden = true;});
  $('policy-form')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    try {
      const response = await fetch('/api/omero/policies', {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value}, body: JSON.stringify(data)});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Unable to save policy.');
      await adminTable('policies');
      form.hidden = true;
      $('policies-status').textContent = 'Policy scheduled.';
    } catch (error) {$('policies-status').textContent = error.message;}
  });
  let billing = [];
  if ($('billing-form')) {
    const today = new Intl.DateTimeFormat('sv-SE', {timeZone: 'Europe/Stockholm', year: 'numeric', month: '2-digit', day: '2-digit'}).format(new Date());
    const start = new Date(`${today}T12:00:00Z`); start.setUTCDate(start.getUTCDate() - 29);
    $('start').value = start.toISOString().slice(0, 10);
    $('end').value = today;
  }
  $('billing-form')?.addEventListener('submit', async event => {
    event.preventDefault();
    const query = new URLSearchParams({startDate: $('start').value, endDate: $('end').value, limit: $('billing-limit').value});
    try {
      const data = await get(`/api/omero/billing?${query}`); billing = data.groups;
      $('billing-rows').replaceChildren(); billing.forEach(g => appendRow($('billing-rows'), [g.group_name, g.snapshot_days, g.billable_gb_days.toFixed(2), g.total_sek.toFixed(2)]));
      $('billing-status').textContent = `${billing.length} groups · inclusive dates`;
      const reversed = [...billing].reverse();
      const theme = layout();
      await Plotly.react('billingChart', [{type: 'bar', orientation: 'h', x: reversed.map(g => g.total_sek), y: reversed.map(g => g.group_name), marker: {color: '#3273dc'}}], {...theme, height: Math.max(350, reversed.length * 28 + 100), margin: {l: 180, r: 25, t: 20, b: 60}, xaxis: {...theme.xaxis, title: 'Total SEK'}}, plotConfig);
    } catch (error) {$('billing-status').textContent = error.message;}
  });
  $('billing-export')?.addEventListener('click', () => {
    const csv = value => `"${String(value ?? '').replace(/^[=+@\-\t\r]/, "'$&").replace(/"/g, '""')}"`;
    const rows = [['Group', 'Snapshot days', 'Billable GB-days', 'Total SEK'], ...billing.map(g => [g.group_name, g.snapshot_days, g.billable_gb_days, g.total_sek])];
    const url = URL.createObjectURL(new Blob([rows.map(row => row.map(csv).join(',')).join('\r\n')], {type: 'text/csv;charset=utf-8'}));
    const link = document.createElement('a'); link.href = url; link.download = 'omero-billing.csv'; link.click(); URL.revokeObjectURL(url);
  });
  $('generate-email')?.addEventListener('click', async () => {
    const dialog = $('email-dialog'); $('email-status').textContent = 'Preparing draft…';
    for (const id of ['email-recipients', 'email-subject', 'email-body']) $(id).value = '';
    dialog.showModal();
    try {
      const data = await get(`/api/omero/groups/${encodeURIComponent($('group_id').value)}/email-draft`);
      $('email-recipients').value = data.recipients.join(', ');
      $('email-subject').value = `OMERO storage for ${data.group_name}`;
      const policy = data.policy_type === 'CORE' ? 'Your group currently has a CORE policy, so storage is not billed.' : `Your group's ${data.policy_type} policy has ${data.billable_gb.toFixed(1)} GB of billable storage at ${data.rate} öre/GB/day, currently approximately ${data.daily_sek.toFixed(2)} SEK/day.`;
      $('email-body').value = `Hello members of ${data.group_name},\n\nAccording to the latest inventory (${data.snapshot_date}), your group has ${data.total_gb.toFixed(1)} GB stored on OMERO.\n\n${policy}\n\nPlease review your data and remove anything you no longer need after confirming it has been safely copied elsewhere. Please let us know if you have any questions.\n\nBest regards`;
      $('email-status').textContent = data.recipients.length ? `${data.recipients.length} active owner email address(es) found. Please review the recipients and message.` : 'No owner email addresses found. Please add recipients before sending.';
    } catch (error) {$('email-status').textContent = error.message;}
  });
  $('email-close')?.addEventListener('click', () => $('email-dialog').close());
})();
