(() => {
  const body = document.getElementById('filesets');
  const status = document.getElementById('storage-status');
  const previous = document.getElementById('previous');
  const next = document.getElementById('next');
  let page = 1;
  const emailButton = document.getElementById('generate-email');
  function updateEmailButton() {
    if (!emailButton) return;
    emailButton.disabled = document.getElementById('group_id').value === 'all';
    emailButton.title = emailButton.disabled ? 'Select one group first' : 'Generate a storage email for this group';
  }
  async function load() {
    const query = new URLSearchParams({page: String(page), search: document.getElementById('search').value});
    for (const key of ['group_id', 'status', 'imported', 'size']) query.set(key, document.getElementById(key).value);
    const order = document.getElementById('order').value;
    query.set('sort', order === 'largest' ? 'total_bytes' : 'imported_at');
    query.set('order', order === 'oldest' ? 'asc' : 'desc');
    updateEmailButton();
    status.textContent = 'Loading…';
    try {
      const response = await fetch(`/api/omero/filesets?${query}`, {credentials: 'same-origin'});
      if (!response.ok) throw new Error('Storage data is currently unavailable.');
      const data = await response.json();
      body.replaceChildren();
      for (const item of data.results) {
        const row = document.createElement('tr');
        const detailCell = document.createElement('td');
        const detail = document.createElement('button');
        detail.className = 'fileset-detail-button'; detail.type = 'button'; detail.textContent = '›'; detail.setAttribute('aria-label', 'Show fileset details');
        detail.setAttribute('aria-expanded', 'false');
        detail.addEventListener('click', async () => {
          if (detail.getAttribute('aria-expanded') === 'true') { row.nextElementSibling?.remove(); detail.setAttribute('aria-expanded', 'false'); detail.setAttribute('aria-label', 'Show fileset details'); detail.textContent = '›'; return; }
          detail.disabled = true;
          try {
            const result = await fetch(`/api/omero/filesets/${encodeURIComponent(item.fileset_id)}`, {credentials: 'same-origin'});
            if (!result.ok) throw new Error('Details unavailable.');
            const data = await result.json();
            const expanded = document.createElement('tr'); const cell = document.createElement('td'); cell.colSpan = 9;
            const details = document.createElement('dl'); details.className = 'fileset-details';
            const dates = value => value ? new Date(value).toLocaleString() : '—';
            const locations = (data.locations || []).map(location => `${location.project_name ? `${location.project_name} (ID ${location.project_id ?? '—'})` : 'No project'} / ${location.dataset_name ? `${location.dataset_name} (ID ${location.dataset_id ?? '—'})` : 'No dataset'}`).join('\n') || 'No project or dataset location';
            const fields = [['OMERO location', locations, true], ['Collected at', dates(data.first_seen_at)], ['Last seen', dates(data.last_seen_at)], ['Uncontained images', data.uncontained_image_count ?? '—'], ['Missing runs', data.missing_runs ?? '—'], ['Source files', (data.source_file_names || []).join('\n') || 'No source file names', true]];
            if (data.missing_since_at) fields.push(['Missing since', dates(data.missing_since_at)]);
            if (data.deleted_at) fields.push(['Deleted at', dates(data.deleted_at)]);
            fields.forEach(([label, value, wide]) => {const item = document.createElement('div'); if (wide) item.className = 'is-wide'; const term = document.createElement('dt'); term.textContent = label; const description = document.createElement('dd'); description.textContent = value; item.append(term, description); details.append(item);});
            cell.append(details); expanded.append(cell); row.after(expanded); detail.setAttribute('aria-expanded', 'true'); detail.setAttribute('aria-label', 'Hide fileset details'); detail.textContent = '⌄';
          } catch (error) { status.textContent = error.message; } finally { detail.disabled = false; }
        });
        detailCell.append(detail); row.append(detailCell);
        const owner = [item.firstname, item.lastname].filter(Boolean).join(' ') || item.username || '—';
        for (const value of [item.fileset_id, owner, item.group_name || '—', item.imported_at ? item.imported_at.slice(0, 10) : '—', item.source_file_count ?? '—', item.image_count ?? '—', `${(Number(item.total_bytes || 0) / 1e9).toFixed(2)} GB`]) {
          const cell = document.createElement('td');
          cell.textContent = value;
          row.append(cell);
        }
        const state = document.createElement('td'); const badge = document.createElement('span'); badge.className = `fileset-status ${item.deleted_at ? 'is-deleted' : 'is-active'}`; badge.textContent = item.deleted_at ? 'Deleted' : 'Active'; state.append(badge); row.append(state);
        body.append(row);
      }
      status.textContent = `${data.count.toLocaleString()} filesets · Page ${data.page}`;
      previous.disabled = page === 1;
      next.disabled = page * data.page_size >= data.count;
    } catch (error) { status.textContent = error.message; }
  }
  const form = document.getElementById('storage-search');
  form.addEventListener('submit', event => {event.preventDefault(); page = 1; load();});
  form.addEventListener('reset', () => {document.getElementById('search').value = ''; page = 1; setTimeout(load, 0);});
  for (const id of ['group_id', 'status', 'imported', 'size', 'order']) document.getElementById(id).addEventListener('change', () => {page = 1; load();});
  let searchTimer; document.getElementById('search').addEventListener('input', () => {clearTimeout(searchTimer); searchTimer = setTimeout(() => {page = 1; load();}, 300);});
  document.getElementById('refresh').addEventListener('click', load);
  previous.addEventListener('click', () => {if (page > 1) {page--; load();}});
  next.addEventListener('click', () => {page++; load();});
  fetch('/api/omero/groups', {credentials: 'same-origin'}).then(response => response.ok ? response.json() : Promise.reject()).then(data => {
    const select = document.getElementById('group_id');
    for (const group of data.groups) {const option = document.createElement('option'); option.value = group.id; option.textContent = group.name || group.id; select.append(option);}
  }).catch(() => {});
  load();
})();
