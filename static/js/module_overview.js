(() => {
  document.querySelectorAll('[data-module-overview]').forEach(async card => {
    const metrics = card.querySelector('[data-module-metrics]');
    const status = card.querySelector('[data-module-status]');
    try {
      const response = await fetch(card.dataset.moduleOverview, {credentials: 'same-origin'});
      if (!response.ok) throw new Error();
      const data = await response.json();
      if (data.version !== 1 || !Array.isArray(data.metrics)) throw new Error();
      for (const metric of data.metrics) {
        if (typeof metric.label !== 'string' || typeof metric.value !== 'string') throw new Error();
        const item = document.createElement('div');
        const label = document.createElement('span');
        const value = document.createElement('strong');
        label.textContent = metric.label;
        value.textContent = metric.value;
        item.append(label, value);
        metrics.append(item);
      }
      status.textContent = data.metrics.length ? '' : 'No summary available.';
    } catch {
      metrics.replaceChildren();
      status.textContent = 'Summary unavailable.';
    }
  });
})();
