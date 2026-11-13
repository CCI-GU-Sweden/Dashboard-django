const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('module cards render returned metrics as text and isolate failures', async () => {
  function element() { return {textContent: '', children: [], append(...items) { this.children.push(...items); }, replaceChildren() { this.children = []; }}; }
  function card(url) {
    const metrics = element(), status = element();
    return {dataset: {moduleOverview: url}, metrics, status, querySelector: selector => selector === '[data-module-metrics]' ? metrics : status};
  }
  const good = card('/good'), bad = card('/bad');
  const context = {
    document: {querySelectorAll: () => [good, bad], createElement: element},
    fetch: async url => url === '/good'
      ? {ok: true, json: async () => ({version: 1, metrics: [{label: 'Files', value: '<5>'}]})}
      : {ok: false},
  };
  vm.runInNewContext(fs.readFileSync('static/js/module_overview.js', 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(good.metrics.children[0].children[1].textContent, '<5>');
  assert.equal(good.status.textContent, '');
  assert.equal(bad.status.textContent, 'Summary unavailable.');
});
