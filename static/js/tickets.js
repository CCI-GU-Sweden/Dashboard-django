(() => {
  const $ = id => document.getElementById(id);
  const body = $('ticket-rows'), status = $('ticket-status');
  const labels = {USER_REQUEST: 'User request', USER_REPORT: 'User report', INTERNAL_ISSUE: 'Internal issue', INCIDENT: 'Incident', LOW: 'Low', NORMAL: 'Normal', HIGH: 'High', CRITICAL: 'Critical', SOFTWARE: 'Software', HARDWARE: 'Hardware', CONNECTION: 'Connection', ACCESS_PERMISSIONS: 'Access / permissions', ACQUISITION_IMAGE_QUALITY: 'Acquisition / image quality', OTHER: 'Other', OPEN: 'Open', IN_PROGRESS: 'In progress', WAITING: 'Waiting', RESOLVED: 'Resolved', CANCELLED: 'Cancelled', CONTACT_FORM: 'Contact form', DASHBOARD: 'Dashboard', CREATED: 'Ticket created', UPDATED: 'Ticket updated', STATUS_CHANGED: 'Status changed'};
  const friendly = value => labels[value] || (value ? String(value).replaceAll('_', ' ').toLowerCase().replace(/^./, c => c.toUpperCase()) : '—');
  const node = (tag, text, className) => {const el = document.createElement(tag); if (text != null) el.textContent = text; if (className) el.className = className; return el;};
  const date = value => value ? new Intl.DateTimeFormat(undefined, {timeZone: 'Europe/Stockholm', dateStyle: 'medium', timeStyle: 'short'}).format(new Date(value)) : '—';
  let page = 1, submissionId = null, equipment = new Map(), staff = new Map(), researchers = [], updateTicket = null, inventorySequence = 0;
  function equipmentName(value) {return equipment.get(value) || value || 'Facility-wide';}
  function omitUnselectedImages(payload) {const files = payload.getAll('images'); if (files.length && files.every(file => typeof file !== 'string' && !file.name)) payload.delete('images');}
  function assignedName(value) {if (!value) return 'Unassigned'; return value.startsWith('dashboard-user:') ? staff.get(value.slice(15)) || 'Former staff member' : value;}
  async function ticketResponse(response) {
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || (response.status === 403 ? 'Your session or permission may have expired. Refresh the page and sign in again.' : response.status === 413 ? 'The upload is too large. Use up to five images of at most 5 MiB each.' : 'The ticket could not be saved. Please try again.'));
    return result;
  }
  async function read(url) {const response = await fetch(url, {credentials: 'same-origin'}); if (!response.ok) throw new Error('Ticket data is currently unavailable.'); return response.json();}
  async function details(id) {return read(`/api/tickets/${encodeURIComponent(id)}`);}
  function updateButton(id, text = 'Update') {const button = node('button', text, 'button is-small is-light'); button.type = 'button'; button.addEventListener('click', () => openUpdate(id)); return button;}
  function field(container, title, value) {const el = node('div', null, 'ticket-detail-field'); el.append(node('h4', title), node('p', value || '—')); container.append(el);}
  function renderDetails(data, link) {
    const panel = node('div', null, 'ticket-details'); panel.append(node('h3', `Ticket #${data.ticket_id}`, 'title is-5'));
    const grid = node('div', null, 'ticket-detail-grid');
    for (const [name, value] of [['Original report', data.message], ['Reported by', data.reporter_name], ['Ticket type', friendly(data.ticket_type)], ['Equipment / assigned staff', `${equipmentName(data.microscope)} / ${data.assigned_to_name || assignedName(data.assigned_to)}`], ['Opened / updated (Europe/Stockholm)', `${date(data.opened_at)} / ${date(data.updated_at)}`], ['Closing date', date(data.resolved_at)], ['Resolution / closing note', data.resolution_note || 'No closing note provided']]) field(grid, name, value);
    panel.append(grid);
    const linkBox = node('div', null, 'ticket-researcher-link'); linkBox.append(node('h4', 'Linked researcher', 'title is-6'));
    linkBox.append(node('p', 'Linking allows this researcher to view the ticket report and status.'));
    const search = document.createElement('input'); search.type = 'search'; search.className = 'input'; search.placeholder = 'Search by name or ORCID'; search.setAttribute('aria-label', 'Search researchers');
    const select = document.createElement('select'); select.className = 'input'; select.setAttribute('aria-label', 'Linked researcher');
    const saveLink = node('button', 'Save researcher link', 'button is-small is-light'); saveLink.type = 'button'; const linkStatus = node('p', '', 'ticket-help'); linkStatus.setAttribute('role', 'status');
    let selected = link.researcher_id || '', expected = link.researcher_id || null;
    function options() {
      const query = search.value.trim().toLocaleLowerCase(); select.replaceChildren(); const empty = node('option', 'No researcher'); empty.value = ''; select.append(empty);
      let selectedFound = false;
      researchers.forEach(person => {if (person.id !== selected && query && !`${person.name} ${person.orcid}`.toLocaleLowerCase().includes(query)) return; const option = node('option', `${person.name}${person.orcid ? ` · ${person.orcid}` : ''}`); option.value = person.id; select.append(option); if (person.id === selected) selectedFound = true;});
      if (selected && !selectedFound) {const option = node('option', `Unavailable researcher (ID ${selected})`); option.value = selected; select.append(option);}
      select.value = selected;
    }
    search.addEventListener('input', options); select.addEventListener('change', () => {selected = select.value;}); options();
    saveLink.addEventListener('click', async () => {saveLink.disabled = true; linkStatus.textContent = '';
      try {const response = await fetch(`/api/tickets/${encodeURIComponent(data.ticket_id)}/researcher`, {method: 'PATCH', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRFToken': $('update-form').elements.csrfmiddlewaretoken.value}, body: JSON.stringify({researcher_id: selected || null, expected_researcher_id: expected})}); const result = await response.json(); if (!response.ok) throw new Error(result.error || 'Unable to save researcher link.'); expected = result.researcher_id; linkStatus.textContent = 'Researcher link saved.';}
      catch (error) {linkStatus.textContent = error.message;} finally {saveLink.disabled = false;}
    });
    linkBox.append(search, select, saveLink, linkStatus); panel.append(linkBox);
    panel.append(node('h4', `Images (${data.images.length} / 5)`, 'title is-6'));
    if (!data.images.length) panel.append(node('p', 'No images attached.'));
    else {
      const gallery = node('div', null, 'ticket-gallery');
      data.images.forEach(image => {const box = node('div', null, 'ticket-image'); box.append(node('strong', image.filename)); const button = node('button', 'Preview image', 'button is-small is-light'); button.type = 'button'; button.addEventListener('click', () => {if (box.querySelector('img')) {box.querySelector('img').remove(); button.textContent = 'Preview image'; return;} const img = document.createElement('img'); img.alt = image.filename; img.loading = 'lazy'; img.src = `/api/tickets/${encodeURIComponent(data.ticket_id)}/images/${encodeURIComponent(image.id)}`; box.append(img); button.textContent = 'Hide image';}); box.append(button); gallery.append(box);});
      panel.append(gallery);
    }
    panel.append(node('h4', 'History', 'title is-6'), updateButton(data.ticket_id, 'Add update'));
    if (!data.events.length) panel.append(node('p', 'No history.'));
    data.events.forEach(event => {const entry = node('div', null, 'ticket-event'); entry.append(node('strong', `${date(event.occurred_at)} · ${event.actor || 'Unknown'}`)); const title = event.old_status && event.new_status && event.old_status !== event.new_status ? `${friendly(event.old_status)} → ${friendly(event.new_status)}` : friendly(event.type); entry.append(node('p', title)); if (event.note) entry.append(node('p', event.note, 'ticket-preserve-text')); panel.append(entry);});
    return panel;
  }
  async function load() {
    const sequence = ++inventorySequence;
    const query = new URLSearchParams({page: String(page)});
    for (const id of ['search', 'reporter', 'message', 'microscope', 'startDate', 'endDate', 'dateField', 'issueType', 'type', 'priority', 'source', 'sort', 'order']) {const value = $(id).value; if (value) query.set(id, value);}
    const selected = $('status').value; if (selected !== 'active') query.set('status', selected);
    status.textContent = 'Loading…';
    try {
      const data = await read(`/api/tickets?${query}`); if (sequence !== inventorySequence) return; body.replaceChildren();
      for (const item of data.results) {
        const row = document.createElement('tr'); const detailCell = document.createElement('td'); const detail = node('button', 'Details', 'button is-small is-light'); detail.type = 'button'; detail.setAttribute('aria-expanded', 'false');
        detail.addEventListener('click', async () => {
          if (detail.getAttribute('aria-expanded') === 'true') {row.nextElementSibling.remove(); detail.setAttribute('aria-expanded', 'false'); return;}
          detail.disabled = true;
          try {const [data, link] = await Promise.all([details(item.ticket_id), read(`/api/tickets/${encodeURIComponent(item.ticket_id)}/researcher`)]); const expanded = document.createElement('tr'), cell = document.createElement('td'); cell.colSpan = 13; cell.append(renderDetails(data, link)); expanded.append(cell); row.after(expanded); detail.setAttribute('aria-expanded', 'true');}
          catch (error) {status.textContent = error.message;} finally {detail.disabled = false;}
        });
        detailCell.append(detail); row.append(detailCell);
        const values = [item.ticket_id, date(item.opened_at), item.reporter_name, equipmentName(item.microscope), item.message, `${friendly(item.ticket_type)} / ${friendly(item.priority)}`, friendly(item.issue_type), friendly(item.status), assignedName(item.assigned_to), date(item.resolved_at), item.image_count];
        values.forEach((value, index) => {const cell = document.createElement('td'); if (index === 4) cell.className = 'ticket-message-preview'; if (index === 7) cell.append(node('span', value, `ticket-status ticket-status-${String(item.status || '').toLowerCase().replaceAll('_', '-')}`)); else cell.textContent = value ?? '—'; row.append(cell);});
        const action = document.createElement('td'); action.append(updateButton(item.ticket_id)); row.append(action); body.append(row);
      }
      status.textContent = `${data.count.toLocaleString()} tickets · Page ${data.page}`; $('previous').disabled = page === 1; $('next').disabled = page * data.page_size >= data.count;
    } catch (error) {if (sequence === inventorySequence) status.textContent = error.message;}
  }
  async function loadSummary() {try {const data = await read('/api/tickets/summary'); for (const key of ['total', 'active', 'resolved']) $(key).textContent = data[key].toLocaleString();} catch { /* Inventory remains usable. */ }}
  const filters = $('ticket-search'); filters.addEventListener('submit', event => {event.preventDefault(); page = 1; load();}); filters.addEventListener('reset', () => {page = 1; setTimeout(load, 0);});
  $('refresh').addEventListener('click', () => {load(); loadSummary();});
  $('previous').addEventListener('click', () => {if (page > 1) {page--; load();}}); $('next').addEventListener('click', () => {page++; load();});
  const createForm = $('create-form'), createDialog = $('create-dialog');
  $('add-ticket').addEventListener('click', () => {submissionId ||= crypto.randomUUID(); createDialog.showModal();});
  for (const id of ['close-ticket', 'cancel-ticket']) $(id).addEventListener('click', () => createDialog.close());
  createForm.addEventListener('submit', async event => {
    event.preventDefault(); const button = createForm.querySelector('[type=submit]'), error = $('create-error'), payload = new FormData(createForm); payload.set('source_event_id', submissionId); omitUnselectedImages(payload); button.disabled = true; error.textContent = '';
    try {const response = await fetch('/api/tickets', {method: 'POST', credentials: 'same-origin', headers: {'X-CSRFToken': createForm.elements.csrfmiddlewaretoken.value}, body: payload}); await ticketResponse(response); createDialog.close(); createForm.reset(); submissionId = null; page = 1; load(); loadSummary();}
    catch (problem) {error.textContent = problem.message;} finally {button.disabled = false;}
  });
  const updateDialog = $('update-dialog'), updateForm = $('update-form');
  function fillUpdate(data, preserveDraft = false) {
    updateTicket = data; $('update-title').textContent = `Update ticket #${data.ticket_id}`; $('update-summary').textContent = `${data.reporter_name} · ${equipmentName(data.microscope)} · Version ${data.version}`;
    updateForm.elements.status.value = data.status; updateForm.elements.priority.value = data.priority; updateForm.elements.issue_type.value = data.issue_type || '';
    const select = $('update-assigned'); select.replaceChildren(); const empty = node('option', 'Unassigned'); empty.value = ''; select.append(empty);
    staff.forEach((name, id) => {const option = node('option', name); option.value = id; select.append(option);});
    const assigned = data.assigned_to || ''; const selected = assigned.startsWith('dashboard-user:') ? assigned.slice(15) : '';
    if (assigned && (!selected || !staff.has(selected))) {const option = node('option', `Keep current: ${data.assigned_to_name || assignedName(assigned)}`); option.value = '__keep__'; select.append(option); select.value = '__keep__';} else select.value = selected;
    if (!preserveDraft) {updateForm.elements.change_note.value = ''; updateForm.elements.resolution_note.value = ''; updateForm.elements.images.value = '';}
    $('update-image-help').textContent = `${data.images.length} / 5 images already stored; each image can be at most 5 MiB.`; $('update-error').textContent = '';
  }
  async function openUpdate(id) {try {fillUpdate(await details(id)); updateDialog.showModal();} catch (error) {status.textContent = error.message;}}
  for (const id of ['close-update', 'cancel-update']) $(id).addEventListener('click', () => updateDialog.close());
  $('reload-update').addEventListener('click', async () => {try {fillUpdate(await details(updateTicket.ticket_id), true);} catch (error) {$('update-error').textContent = error.message;}});
  updateForm.addEventListener('submit', async event => {
    event.preventDefault(); const button = updateForm.querySelector('[type=submit]'), payload = new FormData(updateForm); payload.set('version', String(updateTicket.version)); omitUnselectedImages(payload); if (payload.get('assigned_to') === '__keep__') payload.delete('assigned_to'); button.disabled = true; $('update-error').textContent = '';
    try {const response = await fetch(`/api/tickets/${encodeURIComponent(updateTicket.ticket_id)}`, {method: 'POST', credentials: 'same-origin', headers: {'X-CSRFToken': updateForm.elements.csrfmiddlewaretoken.value}, body: payload}); await ticketResponse(response); updateDialog.close(); load(); loadSummary();}
    catch (error) {$('update-error').textContent = error.message;} finally {button.disabled = false;}
  });
  function fillEquipment(items) {
    equipment.clear();
    items.forEach(item => equipment.set(item.id, item.name));
    for (const [select, isFilter] of [[$('microscope'), true], [$('create-equipment'), false]]) {
      const selected = select.value;
      select.replaceChildren();
      const all = node('option', isFilter ? 'All equipment' : 'Facility-wide'); all.value = ''; select.append(all);
      if (isFilter) {const facility = node('option', 'Facility-wide'); facility.value = '__facility__'; select.append(facility);}
      const categories = new Map();
      items.filter(item => isFilter || item.active !== false).forEach(item => {const category = item.active === false ? 'Inactive equipment' : (item.category || 'Other'); if (!categories.has(category)) categories.set(category, []); categories.get(category).push(item);});
      categories.forEach((entries, name) => {const group = document.createElement('optgroup'); group.label = name; entries.forEach(item => {const option = node('option', item.name); option.value = item.id; group.append(option);}); select.append(group);});
      if (selected && Array.from(select.options).some(option => option.value === selected)) select.value = selected;
    }
  }
  document.addEventListener('equipment-changed', async () => {try {const data = await read('/api/tickets/equipment'); fillEquipment(data.equipment); load();} catch {status.textContent = 'Could not refresh equipment. Please reload the page.';}});
  Promise.all([read('/api/tickets/equipment'), read('/api/tickets/staff'), read('/api/tickets/researchers')]).then(([equipmentData, staffData, researcherData]) => {fillEquipment(equipmentData.equipment); staff = new Map(staffData.staff.map(item => [String(item.id), item.name])); researchers = researcherData.researchers; load();}).catch(() => {status.textContent = 'Equipment or staff list is unavailable. Please refresh.'; $('add-ticket').disabled = true;});
  loadSummary();
})();
