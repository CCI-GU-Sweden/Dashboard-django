(() => {
  const $ = id => document.getElementById(id);
  const body = $('account-rows');
  const rows = Array.from(body.querySelectorAll('.account-row'));
  function render() {
    const search = $('account-search').value.trim().toLocaleLowerCase();
    const role = $('account-role-filter').value;
    const status = $('account-status-filter').value;
    const sort = $('account-sort').value;
    rows.sort((left, right) => {
      const name = left.dataset.name.localeCompare(right.dataset.name, undefined, {sensitivity: 'base'});
      if (sort === 'name-desc') return -name;
      if (sort === 'joined') return right.dataset.joined.localeCompare(left.dataset.joined) || name;
      if (sort === 'role' || sort === 'status') return left.dataset[sort].localeCompare(right.dataset[sort]) || name;
      return name;
    });
    let shown = 0;
    rows.forEach(row => {
      const searchable = [row.dataset.name, row.cells[1]?.textContent || '', row.querySelector('.group-summary')?.textContent || ''].join(' ').toLocaleLowerCase();
      const visible = (!search || searchable.includes(search)) && (role === 'all' || row.dataset.role === role) && (status === 'all' || row.dataset.status === status);
      row.hidden = !visible; if (visible) shown++; body.append(row);
    });
    $('account-count').textContent = `${shown} of ${rows.length} accounts`;
    $('accounts-empty').hidden = shown > 0 || rows.length === 0;
  }
  for (const id of ['account-search', 'account-role-filter', 'account-status-filter', 'account-sort']) $(id).addEventListener(id === 'account-search' ? 'input' : 'change', render);
  render();
  const selects = document.querySelectorAll('.group-select');
  if (!selects.length) return;
  fetch('/api/omero/groups', {credentials: 'same-origin'}).then(response => {
    if (!response.ok) throw new Error();
    return response.json();
  }).then(data => {
    const names = new Map(data.groups.map(group => [String(group.id), group.name || `Group ${group.id}`]));
    const nameCounts = new Map(); data.groups.forEach(group => {const name = group.name || `Group ${group.id}`; nameCounts.set(name, (nameCounts.get(name) || 0) + 1);});
    document.querySelectorAll('.group-name[data-group-id]').forEach(label => {
      const name = names.get(label.dataset.groupId);
      if (name) label.textContent = name;
      else label.textContent = `Group ${label.dataset.groupId} (not in current inventory)`;
    });
    selects.forEach(select => {
      const current = select.dataset.current;
      select.replaceChildren();
      const placeholder = document.createElement('option'); placeholder.value = ''; placeholder.textContent = current && !names.has(current) ? 'Current group unavailable — select a group' : 'Select a group'; select.append(placeholder);
      data.groups.forEach(group => {const option = document.createElement('option'); option.value = String(group.id); const name = group.name || `Group ${group.id}`; option.textContent = nameCounts.get(name) > 1 ? `${name} (ID ${group.id})` : name; select.append(option);});
      select.value = names.has(current) ? current : '';
      select.disabled = data.groups.length === 0;
      const save = select.closest('form').querySelector('button[type=submit]');
      const update = () => {save.disabled = select.disabled || !select.value;};
      select.addEventListener('change', update); update();
    });
    if (!data.groups.length) $('groups-message').textContent = 'No OMERO groups are available in the collected storage data.';
    render();
  }).catch(() => {$('groups-message').textContent = 'Could not load OMERO groups. Existing access is unchanged; try again later.';});
})();
