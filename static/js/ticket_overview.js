(() => {
  fetch('/api/tickets/summary', {credentials: 'same-origin'}).then(response => {if (!response.ok) throw new Error(); return response.json();}).then(data => {
    for (const key of ['total', 'active', 'resolved']) {
      document.getElementById(`overview-tickets-${key}`).textContent = Number(data[key]).toLocaleString();
      const change = data.changes[key];
      document.getElementById(`overview-tickets-${key}-change`).textContent = change == null ? 'Comparison unavailable' : `${change >= 0 ? '+' : ''}${Number(change).toLocaleString()} ${key === 'resolved' ? 'vs previous 30 days' : 'vs 30 days ago'}`;
    }
  }).catch(() => {document.getElementById('overview-tickets-status').textContent = 'Ticket statistics are currently unavailable.';});
})();
