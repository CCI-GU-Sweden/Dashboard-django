(() => {
  const $ = id => document.getElementById(id), body = $('ticket-rows');
  const label = value => ({OPEN: 'Open', IN_PROGRESS: 'In progress', WAITING: 'Waiting (legacy)', RESOLVED: 'Resolved', CANCELLED: 'Cancelled', USER_REQUEST: 'User issue', USER_REPORT: 'User issue', INTERNAL_ISSUE: 'Technical issue'}[value] || value || '—');
  const date = value => value ? new Intl.DateTimeFormat(undefined, {timeZone: 'Europe/Stockholm', dateStyle: 'medium', timeStyle: 'short'}).format(new Date(value)) : '—';
  const node = (tag, text) => {const el = document.createElement(tag); el.textContent = text ?? ''; return el;};
  let page = 1, submissionId = null, equipment = new Map();
  async function read(url) {const response = await fetch(url, {credentials: 'same-origin'}); if (!response.ok) throw new Error('Ticket information is unavailable.'); return response.json();}
  async function load() {
    try {
      const data = await read(`/api/tickets?page=${page}&status=all`); body.replaceChildren();
      for (const item of data.results) {
        const row = document.createElement('tr'), first = document.createElement('td'), button = node('button', 'Details'); button.className = 'button is-small is-light'; button.type = 'button'; button.setAttribute('aria-expanded', 'false');
        button.addEventListener('click', async () => {
          if (button.getAttribute('aria-expanded') === 'true') {row.nextElementSibling.remove(); button.setAttribute('aria-expanded', 'false'); return;}
          button.disabled = true;
          try {const ticket = await read(`/api/tickets/${encodeURIComponent(item.ticket_id)}`); const expansion = document.createElement('tr'), cell = document.createElement('td'), panel = document.createElement('div'); cell.colSpan = 6; panel.className = 'ticket-details'; panel.append(node('h3', `Ticket #${ticket.ticket_id}`), node('p', ticket.message), node('p', `Status: ${label(ticket.status)} · Updated: ${date(ticket.updated_at)}`));
            if (item.tags?.length) panel.append(node('h4', 'Tags'), node('p', item.tags.map(tag => tag.name).join(', ')));
            if (ticket.status === 'RESOLVED' && ticket.resolution_note) panel.append(node('h4', 'Resolution note'), node('p', ticket.resolution_note));
            if (ticket.images.length) {panel.append(node('h4', 'Your attachments')); ticket.images.forEach(image => {const container = document.createElement('div'), preview = node('button', `Preview ${image.filename}`); preview.type = 'button'; preview.className = 'button is-small is-light'; preview.addEventListener('click', () => {if (container.querySelector('img')) {container.querySelector('img').remove(); return;} const img = document.createElement('img'); img.alt = image.filename; img.loading = 'lazy'; img.src = `/api/tickets/${encodeURIComponent(ticket.ticket_id)}/images/${encodeURIComponent(image.id)}`; img.style.maxWidth = '100%'; container.append(img);}); container.append(preview); panel.append(container);});}
            cell.append(panel); expansion.append(cell); row.after(expansion); button.setAttribute('aria-expanded', 'true');
          } catch (error) {$('ticket-status').textContent = error.message;} finally {button.disabled = false;}
        }); first.append(button); row.append(first);
        for (const value of [item.ticket_id, date(item.opened_at), equipment.get(item.microscope) || item.microscope || 'Facility-wide', item.message, label(item.status)]) row.append(node('td', value)); body.append(row);
      }
      $('ticket-status').textContent = `${data.count.toLocaleString()} tickets · Page ${data.page}`; $('previous').disabled = page <= 1; $('next').disabled = page * data.page_size >= data.count;
    } catch (error) {$('ticket-status').textContent = error.message;}
  }
  async function summary() {try {const data = await read('/api/tickets/summary'); for (const key of ['total', 'active', 'resolved']) $(key).textContent = Number(data[key]).toLocaleString();} catch {}}
  $('previous').addEventListener('click', () => {if (page > 1) {page--; load();}}); $('next').addEventListener('click', () => {page++; load();});
  const form = $('create-form');
  if (form) {
    $('clear-create-tags').addEventListener('click', () => {for (const option of $('create-tags').options) option.selected = false;});
    $('add-ticket').addEventListener('click', () => {submissionId ||= crypto.randomUUID(); $('create-dialog').showModal();});
    for (const id of ['close-ticket', 'cancel-ticket']) $(id).addEventListener('click', () => $('create-dialog').close());
    form.addEventListener('submit', async event => {event.preventDefault(); const data = new FormData(form), button = form.querySelector('[type=submit]'); data.set('source_event_id', submissionId); data.set('tags', JSON.stringify([...$('create-tags').selectedOptions].map(option => option.value))); const files = data.getAll('images'); if (files.length && files.every(file => typeof file !== 'string' && !file.name)) data.delete('images'); button.disabled = true; $('create-error').textContent = '';
      try {const response = await fetch('/api/tickets', {method: 'POST', credentials: 'same-origin', headers: {'X-CSRFToken': form.elements.csrfmiddlewaretoken.value}, body: data}); const result = await response.json().catch(() => ({})); if (!response.ok) throw new Error(result.error || (response.status === 403 ? 'Your session or permission may have expired. Refresh the page and sign in again.' : response.status === 413 ? 'The upload is too large. Use up to five images of at most 5 MiB each.' : 'The ticket could not be saved. Please try again.')); $('create-dialog').close(); form.reset(); submissionId = null; page = 1; load(); summary();} catch (error) {$('create-error').textContent = error.message;} finally {button.disabled = false;}
    });
  }
  if (form) read('/api/tickets/tags').then(data => {data.tags.forEach(tag => {const option = node('option', tag.name); option.value = tag.id; $('create-tags').append(option);});}).catch(() => {$('create-error').textContent = 'Tags are unavailable. Refresh to try again.';});
  read('/api/tickets/equipment').then(data => {const groups = new Map(); data.equipment.forEach(item => {equipment.set(item.id, item.name); if (!groups.has(item.category)) groups.set(item.category, []); groups.get(item.category).push(item);}); if (form) groups.forEach((items, category) => {const group = document.createElement('optgroup'); group.label = category; items.forEach(item => {const option = node('option', item.name); option.value = item.id; group.append(option);}); $('create-equipment').append(group);}); load();}).catch(() => {if (form) $('add-ticket').disabled = true; load();});
  summary();
})();
