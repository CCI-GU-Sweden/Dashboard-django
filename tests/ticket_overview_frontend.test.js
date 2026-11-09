const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('ticket card shows totals and rolling comparisons', async () => {
  const ids = ['total', 'active', 'resolved'].flatMap(key => [`overview-tickets-${key}`, `overview-tickets-${key}-change`]);
  ids.push('overview-tickets-status');
  const elements = Object.fromEntries(ids.map(id => [id, {textContent: ''}]));
  const data = {total: 7, active: 3, resolved: 4, changes: {total: 7, active: null, resolved: -1}};
  vm.runInNewContext(fs.readFileSync('static/js/ticket_overview.js', 'utf8'), {document: {getElementById: id => elements[id]}, fetch: async () => ({ok: true, json: async () => data})});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(elements['overview-tickets-total'].textContent, '7');
  assert.equal(elements['overview-tickets-total-change'].textContent, '+7 vs 30 days ago');
  assert.equal(elements['overview-tickets-active-change'].textContent, 'Comparison unavailable');
  assert.equal(elements['overview-tickets-resolved-change'].textContent, '-1 vs previous 30 days');
});
