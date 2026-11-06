(() => {
  const chart = document.getElementById('uploads-chart');
  const period = document.getElementById('period');
  const scope = document.getElementById('scope');
  const metric = document.getElementById('metric');
  const status = document.getElementById('uploads-status');
  const start = document.getElementById('start-date');
  const end = document.getElementById('end-date');
  let request = null;
  let requestNumber = 0;
  let chartReady = false;

  const set = (id, value) => { const element = document.getElementById(id); if (element) element.textContent = value; };
  const number = value => Number(value ?? 0).toLocaleString(undefined, {maximumFractionDigits: 2});

  function renderStats(data) {
    set('overview-files', number(data.total_files));
    set('overview-size', `${number(data.total_size_gb)} GB`);
    set('overview-scope', data.top_scope_files?.name || '—');
    document.querySelectorAll('[data-stat]').forEach(element => {
      const key = element.dataset.stat;
      const value = data[key];
      if (value == null) element.textContent = '—';
      else if (key === 'top_scope_files') element.textContent = `${value.name} (${number(value.count)})`;
      else if (key === 'top_scope_size') element.textContent = `${value.name} (${number(value.size_gb)} GB)`;
      else if (key === 'peak_day') element.textContent = `${value.date} (${number(value.count)})`;
      else if (key === 'period_change') element.textContent = `${value >= 0 ? '+' : ''}${number(value)}%`;
      else element.textContent = number(value);
    });
  }

  async function load() {
    request?.abort();
    const sequence = ++requestNumber;
    request = new AbortController();
    const params = new URLSearchParams();
    if (chart) {
      chartReady = false;
      params.set('scope', scope.value);
      params.set('metric', metric.value);
      if (period.value === 'custom') {
        if (!start.value || !end.value || start.value > end.value) {
          status.textContent = 'Choose a valid start and end date.';
          return;
        }
        params.set('startDate', start.value);
        params.set('endDate', end.value);
      } else params.set('period', period.value);
      status.textContent = 'Loading…';
    } else params.set('period', '30');
    try {
      const response = await fetch(`/api/uploads/summary?${params}`, {credentials: 'same-origin', signal: request.signal});
      if (!response.ok) throw new Error('Upload data is currently unavailable.');
      const data = await response.json();
      if (sequence !== requestNumber) return;
      renderStats(data);
      if (!chart) return;
      if (typeof Plotly === 'undefined') throw new Error('The chart library could not be loaded.');
      const sizeMetric = metric.value === 'total_file_size_mb';
      const traces = data.chart_data.datasets.map(dataset => ({
        type: 'bar', name: dataset.label, x: data.chart_data.labels, y: dataset.data,
        marker: {color: dataset.backgroundColor},
        hovertemplate: `%{x}<br>%{y:,.${sizeMetric ? '2' : '0'}f} ${sizeMetric ? 'GB' : 'files'}<extra>%{fullData.name}</extra>`,
      }));
      await Plotly.react(chart, traces, {
        barmode: 'stack', hovermode: 'x unified', showlegend: false,
        margin: {l: 65, r: 20, t: 15, b: 60},
        xaxis: {title: {text: 'Date'}, type: 'date'},
        yaxis: {title: {text: sizeMetric ? 'Data (GB)' : 'Files'}, rangemode: 'tozero'},
        paper_bgcolor: '#ffffff', plot_bgcolor: '#ffffff',
      }, {responsive: true, displaylogo: false, toImageButtonOptions: {format: 'png', filename: 'uploads-chart'}});
      chartReady = true;
      status.textContent = traces.length ? '' : 'No uploads in this period.';
    } catch (error) {
      if (error.name !== 'AbortError' && status && sequence === requestNumber) status.textContent = error.message;
    }
  }

  if (chart) {
    if (typeof ResizeObserver !== 'undefined') {
      let lastWidth = 0;
      let lastHeight = 0;
      let resizePending = false;
      const observer = new ResizeObserver(entries => {
        const {width, height} = entries[0].contentRect;
        if (!chartReady || !width || !height || (width === lastWidth && height === lastHeight)) return;
        lastWidth = width;
        lastHeight = height;
        if (!resizePending) {
          resizePending = true;
          requestAnimationFrame(() => { resizePending = false; if (chartReady) Plotly.Plots.resize(chart); });
        }
      });
      observer.observe(chart);
    }
    const customRange = document.getElementById('custom-range');
    period.addEventListener('change', () => { customRange.hidden = period.value !== 'custom'; load(); });
    for (const element of [scope, metric, start, end]) element.addEventListener('change', load);
    fetch('/api/uploads/scopes', {credentials: 'same-origin'}).then(response => {
      if (!response.ok) throw new Error();
      return response.json();
    }).then(scopes => {
      for (const name of scopes) {const option = document.createElement('option'); option.value = name; option.textContent = name; scope.append(option);}
    }).catch(() => { scope.disabled = true; scope.title = 'Microscope list is unavailable'; });

    document.getElementById('export-page').addEventListener('click', async event => {
      const button = event.currentTarget;
      if (!chartReady) { status.textContent = 'Wait for the chart before exporting.'; return; }
      button.disabled = true;
      try {
        const image = await Plotly.toImage(chart, {format: 'png', width: chart.clientWidth || 1000, height: chart.clientHeight || 420});
        const canvas = await html2canvas(document.getElementById('uploads-view'), {
          onclone: cloned => {
            const target = cloned.getElementById('uploads-chart');
            const replacement = cloned.createElement('img');
            replacement.src = image; replacement.alt = 'Uploads chart';
            replacement.style.width = '100%'; replacement.style.height = 'auto';
            target.replaceChildren(replacement);
            cloned.getElementById('export-page').hidden = true;
          },
        });
        const link = document.createElement('a'); link.download = 'uploads-dashboard.png'; link.href = canvas.toDataURL('image/png'); link.click();
      } catch { status.textContent = 'Unable to export the dashboard image.'; }
      finally { button.disabled = false; }
    });
  }
  load();
})();
