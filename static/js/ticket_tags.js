(() => {
  const $ = id => document.getElementById(id), dialog = $('tags-dialog'), list = $('tags-list'), status = $('tags-status');
  const csrf = () => $('update-form').elements.csrfmiddlewaretoken.value;
  async function request(url, options = {}) {const response = await fetch(url, {credentials: 'same-origin', ...options}); const result = await response.json().catch(() => ({})); if (!response.ok) throw new Error(result.error || 'Tags are currently unavailable.'); return result;}
  async function load() {
    try {const result = await request('/api/tickets/tags'); list.replaceChildren();
      result.tags.forEach(tag => {const row = document.createElement('div'); row.className = 'ticket-event'; const label = document.createElement('span'); label.textContent = tag.name; row.append(label);
        if (dialog.dataset.admin === 'true') {const button = document.createElement('button'); button.type = 'button'; button.className = 'button is-small is-light'; button.textContent = 'Delete'; button.addEventListener('click', async () => {if (!window.confirm(`Delete tag “${tag.name}”? It will be removed from every ticket, including archived tickets.`)) return; button.disabled = true; try {await request(`/api/tickets/tags/${encodeURIComponent(tag.id)}`, {method: 'DELETE', headers: {'X-CSRFToken': csrf()}}); document.dispatchEvent(new Event('ticket-tags-changed')); await load();} catch (error) {status.textContent = error.message; button.disabled = false;}}); row.append(button);} list.append(row);});
      status.textContent = result.tags.length ? '' : 'No tags yet.';
    } catch (error) {status.textContent = error.message;}
  }
  $('manage-tags').addEventListener('click', () => {dialog.showModal(); load();});
  for (const id of ['close-tags', 'close-tags-footer']) $(id).addEventListener('click', () => dialog.close());
  $('tag-form').addEventListener('submit', async event => {event.preventDefault(); const name = $('tag-name').value.trim(); try {await request('/api/tickets/tags', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()}, body: JSON.stringify({name})}); $('tag-name').value = ''; document.dispatchEvent(new Event('ticket-tags-changed')); await load();} catch (error) {status.textContent = error.message;}});
})();
