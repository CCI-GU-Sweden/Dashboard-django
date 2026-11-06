(() => {
  const body = document.getElementById('ticket-rows');
  const status = document.getElementById('ticket-status');
  const previous = document.getElementById('previous');
  const next = document.getElementById('next');
  let page = 1;
  let submissionId = null;
  async function load() {
    const query = new URLSearchParams({page: String(page)});
    for (const id of ['search', 'reporter', 'message', 'microscope', 'startDate', 'endDate', 'dateField', 'issueType', 'type', 'priority', 'source', 'sort', 'order']) {
      const value = document.getElementById(id).value;
      if (value) query.set(id, value);
    }
    const selected = document.getElementById('status').value;
    if (selected !== 'active') query.set('status', selected);
    status.textContent = 'Loading…';
    try {
      const response = await fetch(`/api/tickets?${query}`, {credentials: 'same-origin'});
      if (!response.ok) throw new Error('Tickets are currently unavailable.');
      const data = await response.json();
      body.replaceChildren();
      for (const item of data.results) {
        const row = document.createElement('tr');
        for (const [index, value] of [item.ticket_id, item.opened_at?.slice(0, 10), item.reporter_name, item.microscope, item.message, [item.ticket_type, item.priority].filter(Boolean).join(' / '), item.issue_type, item.status, item.assigned_to, item.resolved_at?.slice(0, 10)].entries()) {
          const cell = document.createElement('td');
          if (index === 0) { const link = document.createElement('a'); link.href = `/tickets/${encodeURIComponent(value)}/`; link.textContent = value; cell.append(link); }
          else cell.textContent = value || '—';
          row.append(cell);
        }
        body.append(row);
      }
      status.textContent = `${data.count.toLocaleString()} tickets · Page ${data.page}`;
      previous.disabled = page === 1;
      next.disabled = page * data.page_size >= data.count;
    } catch (error) { status.textContent = error.message; }
  }
  async function loadSummary() {
    try {
      const response = await fetch('/api/tickets/summary', {credentials: 'same-origin'});
      if (!response.ok) return;
      const data = await response.json();
      for (const key of ['total', 'active', 'resolved']) document.getElementById(key).textContent = data[key].toLocaleString();
    } catch { /* The inventory can still load if summary is unavailable. */ }
  }
  const form = document.getElementById('ticket-search');
  form.addEventListener('submit', event => {event.preventDefault(); page = 1; load();});
  form.addEventListener('reset', () => {page = 1; setTimeout(load, 0);});
  document.getElementById('refresh').addEventListener('click', () => {load(); loadSummary();});
  const dialog = document.getElementById('create-dialog');
  const createForm = document.getElementById('create-form');
  document.getElementById('add-ticket').addEventListener('click', () => {
    submissionId ||= crypto.randomUUID();
    dialog.showModal();
  });
  for (const id of ['close-ticket', 'cancel-ticket']) document.getElementById(id).addEventListener('click', () => dialog.close());
  createForm.addEventListener('submit', async event => {
    event.preventDefault();
    const button = createForm.querySelector('[type=submit]');
    const error = document.getElementById('create-error');
    const fields = new FormData(createForm);
    const payload = {};
    for (const key of ['reporter_name', 'reporter_identifier', 'microscope', 'message', 'ticket_type', 'issue_type', 'priority']) payload[key] = fields.get(key);
    payload.source_event_id = submissionId;
    button.disabled = true; error.textContent = '';
    try {
      const response = await fetch('/api/tickets', {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRFToken': fields.get('csrfmiddlewaretoken')}, body: JSON.stringify(payload)});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Unable to create the ticket.');
      dialog.close(); createForm.reset(); submissionId = null; page = 1; load(); loadSummary();
    } catch (problem) {error.textContent = problem.message;} finally {button.disabled = false;}
  });
  fetch('/api/tickets/equipment', {credentials: 'same-origin'}).then(response => response.ok ? response.json() : Promise.reject()).then(data => {
    const select = document.getElementById('create-equipment');
    for (const item of data.equipment) {const option = document.createElement('option'); option.value = item.id; option.textContent = item.name; select.append(option);}
  }).catch(() => {document.getElementById('create-error').textContent = 'Equipment is unavailable; please refresh before creating a ticket.'; document.getElementById('add-ticket').disabled = true;});
  previous.addEventListener('click', () => {if (page > 1) {page--; load();}});
  next.addEventListener('click', () => {page++; load();});
  load(); loadSummary();
})();
