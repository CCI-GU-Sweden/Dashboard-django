(() => {
  const body = document.getElementById('filesets');
  const status = document.getElementById('storage-status');
  const previous = document.getElementById('previous');
  const next = document.getElementById('next');
  let page = 1;
  async function load() {
    const query = new URLSearchParams({page: String(page), search: document.getElementById('search').value});
    for (const key of ['group_id', 'status', 'imported', 'size']) query.set(key, document.getElementById(key).value);
    const order = document.getElementById('order').value;
    query.set('sort', order === 'largest' ? 'total_bytes' : 'imported_at');
    query.set('order', order === 'oldest' ? 'asc' : 'desc');
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
        detail.className = 'button is-small is-light'; detail.type = 'button'; detail.textContent = 'Details';
        detail.setAttribute('aria-expanded', 'false');
        detail.addEventListener('click', async () => {
          if (detail.getAttribute('aria-expanded') === 'true') { row.nextElementSibling?.remove(); detail.setAttribute('aria-expanded', 'false'); return; }
          detail.disabled = true;
          try {
            const result = await fetch(`/api/omero/filesets/${encodeURIComponent(item.fileset_id)}`, {credentials: 'same-origin'});
            if (!result.ok) throw new Error('Details unavailable.');
            const data = await result.json();
            const expanded = document.createElement('tr'); const cell = document.createElement('td'); cell.colSpan = 9;
            const summary = document.createElement('p'); summary.textContent = `First seen: ${data.first_seen_at || '—'} · Last seen: ${data.last_seen_at || '—'} · Missing runs: ${data.missing_runs ?? '—'}`; cell.append(summary);
            const names = document.createElement('p'); names.textContent = `Source files: ${(data.source_file_names || []).filter(Boolean).join(', ') || '—'}`; cell.append(names);
            expanded.append(cell); row.after(expanded); detail.setAttribute('aria-expanded', 'true');
          } catch (error) { status.textContent = error.message; } finally { detail.disabled = false; }
        });
        detailCell.append(detail); row.append(detailCell);
        const owner = [item.firstname, item.lastname].filter(Boolean).join(' ') || item.username || '—';
        for (const value of [item.fileset_id, owner, item.group_name || '—', item.imported_at ? item.imported_at.slice(0, 10) : '—', item.source_file_count ?? '—', item.image_count ?? '—', `${(Number(item.total_bytes || 0) / 1e9).toFixed(2)} GB`, item.deleted_at ? 'Deleted' : 'Active']) {
          const cell = document.createElement('td');
          cell.textContent = value;
          row.append(cell);
        }
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
  document.getElementById('refresh').addEventListener('click', load);
  previous.addEventListener('click', () => {if (page > 1) {page--; load();}});
  next.addEventListener('click', () => {page++; load();});
  fetch('/api/omero/groups', {credentials: 'same-origin'}).then(response => response.ok ? response.json() : Promise.reject()).then(data => {
    const select = document.getElementById('group_id');
    for (const group of data.groups) {const option = document.createElement('option'); option.value = group.id; option.textContent = group.name || group.id; select.append(option);}
  }).catch(() => {});
  load();
})();
