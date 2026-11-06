const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('upload chart renders stacked Plotly series and updates the requested metric', async () => {
  const ids = ['uploads-chart', 'period', 'scope', 'metric', 'uploads-status', 'start-date', 'end-date', 'custom-range', 'export-page'];
  const elements = Object.fromEntries(ids.map(id => [id, {
    value: '', hidden: false, listeners: {},
    addEventListener(name, handler) { this.listeners[name] = handler; },
    append() {},
  }]));
  elements.period.value = '30';
  elements.scope.value = 'all';
  elements.metric.value = 'file_count';
  const calls = [];
  const rendered = [];
  const data = {total_files: 2, total_size_gb: 1, chart_data: {labels: ['2026-01-01'], datasets: [{label: 'Scope A', data: [2], backgroundColor: '#123456'}]}};
  const context = {
    document: {
      getElementById: id => elements[id] || null,
      querySelectorAll: () => [],
      createElement: () => ({}),
    },
    fetch: async url => {
      calls.push(url);
      return {ok: true, json: async () => url.includes('/scopes') ? ['Scope A'] : data};
    },
    Plotly: {react: async (...args) => rendered.push(args)},
    URLSearchParams, AbortController,
  };
  vm.runInNewContext(fs.readFileSync('static/js/uploads.js', 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(rendered.length, 1);
  assert.equal(rendered[0][1][0].type, 'bar');
  assert.equal(rendered[0][2].barmode, 'stack');
  assert.equal(rendered[0][2].yaxis.title.text, 'Files');
  elements.metric.value = 'total_file_size_mb';
  elements.metric.listeners.change();
  await new Promise(resolve => setImmediate(resolve));
  assert.match(calls.at(-1), /metric=total_file_size_mb/);
  assert.equal(rendered.at(-1)[2].yaxis.title.text, 'Data (GB)');
});
