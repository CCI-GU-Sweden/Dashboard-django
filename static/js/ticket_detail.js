(() => {
  const id = document.querySelector('[data-ticket-id]').dataset.ticketId;
  const status = document.getElementById('detail-status');
  const node = (tag, text) => { const el = document.createElement(tag); el.textContent = text ?? '—'; return el; };
  fetch(`/api/tickets/${encodeURIComponent(id)}`, {credentials: 'same-origin'}).then(response => {
    if (!response.ok) throw new Error('Ticket is unavailable.');
    return response.json();
  }).then(data => {
    status.textContent = '';
    const form = document.getElementById('update-ticket');
    form.elements.status.value = data.status;
    form.elements.priority.value = data.priority;
    form.hidden = false;
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const submit = form.querySelector('[type=submit]');
      const error = document.getElementById('update-error');
      submit.disabled = true; error.textContent = '';
      try {
        const payload = {version: data.version, status: form.elements.status.value, priority: form.elements.priority.value, change_note: form.elements.change_note.value, resolution_note: form.elements.resolution_note.value};
        const result = await fetch(`/api/tickets/${encodeURIComponent(id)}`, {method: 'PATCH', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRFToken': form.elements.csrfmiddlewaretoken.value}, body: JSON.stringify(payload)});
        const resultData = await result.json();
        if (!result.ok) throw new Error(resultData.error || 'Unable to update ticket.');
        window.location.reload();
      } catch (problem) {error.textContent = problem.message;} finally {submit.disabled = false;}
    });
    const fields = document.getElementById('detail-fields');
    data.ticket_type = ({USER_REQUEST: 'User issue', USER_REPORT: 'User issue', INTERNAL_ISSUE: 'Technical issue', INCIDENT: 'Incident'})[data.ticket_type] || data.ticket_type;
    for (const [label, value] of [['Reporter', data.reporter_name], ['Contact', data.reporter_identifier], ['Equipment', data.microscope], ['Message', data.message], ['Type', data.ticket_type], ['Issue', data.issue_type], ['Status', data.status], ['Priority', data.priority], ['Assigned to', data.assigned_to], ['Opened', data.opened_at], ['Resolution', data.resolution_note]]) {
      fields.append(node('dt', label), node('dd', value));
    }
    const images = document.getElementById('detail-images');
    for (const image of data.images) { const link = node('a', image.filename); link.href = `/api/tickets/${encodeURIComponent(id)}/images/${encodeURIComponent(image.id)}`; link.target = '_blank'; link.rel = 'noopener'; images.append(node('p', ''), link); }
    if (!data.images.length) images.append(node('p', 'No attachments.'));
    const events = document.getElementById('detail-events');
    for (const event of data.events) events.append(node('p', `${event.occurred_at} · ${event.actor} · ${event.type}${event.note ? ` · ${event.note}` : ''}`));
    if (!data.events.length) events.append(node('p', 'No history.'));
  }).catch(error => {status.textContent = error.message;});
})();
