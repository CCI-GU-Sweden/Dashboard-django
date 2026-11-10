(() => {
  const $ = id => document.getElementById(id), dialog = $('archive-dialog'), list = $('archive-list'), status = $('archive-status');
  let page = 1;
  const node = (tag, text, cls) => {const element = document.createElement(tag); if (text != null) element.textContent = text; if (cls) element.className = cls; return element;};
  async function request(url, options = {}) {const response = await fetch(url, {credentials: 'same-origin', ...options}); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.error || 'The request could not be completed.'); return data;}
  async function action(item, type) {
    let payload = {};
    if (type === 'restore') {if (!window.confirm(`Restore ticket #${item.ticket_id}?`)) return;}
    else {const value = window.prompt(`Permanently delete ticket #${item.ticket_id}, its history and images? Existing backups may retain them. Type the ticket number to confirm.`); if (value === null) return; if (value !== item.ticket_id) {status.textContent = 'Ticket number did not match. Nothing was deleted.'; return;} payload = {confirm_ticket_id: value};}
    try {await request(`/api/tickets/${encodeURIComponent(item.ticket_id)}/${type}/archive-action`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': $('update-form').elements.csrfmiddlewaretoken.value}, body: JSON.stringify(payload)}); document.dispatchEvent(new Event('tickets-archive-changed')); await load();}
    catch (error) {status.textContent = error.message;}
  }
  async function load() {
    status.textContent = 'Loading…';
    try {
      const data = await request(`/api/tickets/archived?page=${page}`); list.replaceChildren();
      for (const item of data.results) {
        const box = node('section', null, 'ticket-event');
        box.append(node('h3', `Ticket #${item.ticket_id} · ${item.reporter || 'Unknown'}`, 'title is-6'), node('p', item.message), node('p', `Archived by ${item.archived_by} on ${new Date(item.archived_at).toLocaleString()} · Reason: ${item.reason}`));
        const details = document.createElement('details'), summary = node('summary', 'View ticket and history'); details.append(summary);
        details.addEventListener('toggle', async () => {if (!details.open || details.dataset.loaded) return; try {const data = await request(`/api/tickets/${encodeURIComponent(item.ticket_id)}`); details.dataset.loaded = 'yes'; details.append(node('p', `Status: ${data.status.replaceAll('_', ' ').toLowerCase()}`), node('p', `Resolution: ${data.resolution_note || '—'}`)); for (const image of data.images) {const link = node('a', `View image: ${image.filename}`); link.href = `/api/tickets/${encodeURIComponent(item.ticket_id)}/images/${encodeURIComponent(image.id)}`; link.target = '_blank'; link.rel = 'noopener'; details.append(node('p', null)); details.lastChild.append(link);} details.append(node('h4', 'History')); for (const event of data.events) details.append(node('p', `${new Date(event.occurred_at).toLocaleString()} · ${event.actor || 'Unknown'} · ${event.note || event.type}`));} catch (error) {status.textContent = error.message;}});
        const restore = node('button', 'Restore', 'button is-small is-light'), remove = node('button', 'Delete permanently', 'button is-small is-danger is-light'); restore.type = remove.type = 'button'; restore.addEventListener('click', () => action(item, 'restore')); remove.addEventListener('click', () => action(item, 'delete')); box.append(details, restore, remove); list.append(box);
      }
      status.textContent = data.results.length ? `Page ${data.page}` : 'No archived tickets on this page.'; $('archive-previous').disabled = page === 1; $('archive-next').disabled = !data.has_next;
    } catch (error) {status.textContent = error.message;}
  }
  $('show-archive').addEventListener('click', () => {page = 1; dialog.showModal(); load();});
  for (const id of ['close-archive', 'close-archive-footer']) $(id).addEventListener('click', () => dialog.close());
  $('archive-previous').addEventListener('click', () => {if (page > 1) {page--; load();}}); $('archive-next').addEventListener('click', () => {page++; load();});
})();
