(() => {
  const $ = id => document.getElementById(id);
  const dialog = $('equipment-dialog'), form = $('equipment-form');
  let editing = null;
  function reset() {
    editing = null; form.reset(); $('equipment-form-title').textContent = 'Add equipment';
    $('equipment-active-label').hidden = true; $('equipment-cancel-edit').hidden = true; $('equipment-error').textContent = '';
  }
  async function load() {
    const response = await fetch('/api/tickets/equipment/manage', {credentials: 'same-origin'});
    if (!response.ok) throw new Error('Equipment list is unavailable.');
    const data = await response.json(); const list = $('equipment-list'); list.replaceChildren();
    const categories = $('equipment-categories'); categories.replaceChildren();
    [...new Set(data.equipment.map(item => item.category))].sort().forEach(name => {const option = document.createElement('option'); option.value = name; categories.append(option);});
    data.equipment.forEach(item => {
      const row = document.createElement('div'); row.className = 'equipment-row';
      const title = document.createElement('span'); title.textContent = `${item.name} · ${item.category}${item.active ? '' : ' · Inactive'}`;
      const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'button is-small is-light'; edit.textContent = 'Edit'; edit.setAttribute('aria-label', `Edit ${item.name}`);
      edit.addEventListener('click', () => {editing = item; form.elements.name.value = item.name; form.elements.category.value = item.category; form.elements.active.checked = item.active; $('equipment-form-title').textContent = `Edit ${item.name}`; $('equipment-active-label').hidden = false; $('equipment-cancel-edit').hidden = false; $('equipment-error').textContent = ''; form.elements.name.focus();});
      row.append(title, edit); list.append(row);
    });
    if (!data.equipment.length) list.textContent = 'No equipment yet.';
  }
  async function open() {
    reset(); dialog.showModal();
    try {await load();} catch (error) {$('equipment-error').textContent = error.message;}
  }
  $('manage-equipment').addEventListener('click', open);
  for (const id of ['close-equipment', 'close-equipment-footer']) $(id).addEventListener('click', () => dialog.close());
  $('equipment-cancel-edit').addEventListener('click', reset);
  form.addEventListener('submit', async event => {
    event.preventDefault(); const button = form.querySelector('[type=submit]'); button.disabled = true; $('equipment-error').textContent = '';
    const payload = {name: form.elements.name.value, category: form.elements.category.value};
    if (editing) {payload.active = form.elements.active.checked; payload.expected = {name: editing.name, category: editing.category, active: editing.active};}
    try {
      const response = await fetch('/api/tickets/equipment/manage' + (editing ? `/${encodeURIComponent(editing.id)}` : ''), {method: editing ? 'PATCH' : 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRFToken': form.elements.csrfmiddlewaretoken.value}, body: JSON.stringify(payload)});
      const result = await response.json(); if (!response.ok) throw new Error(result.error || 'Unable to save equipment.');
      reset(); document.dispatchEvent(new Event('equipment-changed')); await load();
    } catch (error) {$('equipment-error').textContent = error.message;} finally {button.disabled = false;}
  });
  if (new URLSearchParams(window.location.search).get('manage-equipment') === '1') open();
})();
