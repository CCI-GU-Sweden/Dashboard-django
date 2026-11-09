const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('overview displays scoped numbers and dated comparison', async () => {
  const ids = ['overview-omero-status', 'overview-omero-filesets', 'overview-omero-filesets-change', 'overview-omero-storage', 'overview-omero-storage-change'];
  const elements = Object.fromEntries(ids.map(id => [id, {textContent: ''}]));
  const data = {snapshot_date: '2026-11-08', comparison_date: '2026-10-09', metrics: {filesets: {value: 11, change_percent: 0}, storage_gb: {value: 0.91, change_percent: null}}};
  const context = {document: {getElementById: id => elements[id] || null}, fetch: async () => ({ok: true, json: async () => data})};
  vm.runInNewContext(fs.readFileSync('static/js/storage_overview.js', 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(elements['overview-omero-filesets'].textContent, '11');
  assert.match(elements['overview-omero-filesets-change'].textContent, /\+0[.,]0% vs 2026-10-09/);
  assert.match(elements['overview-omero-storage'].textContent, /0[.,]91 GB/);
  assert.equal(elements['overview-omero-storage-change'].textContent, 'No 30-day comparison');
});

test('unverified researcher sees an explanation instead of totals', async () => {
  const status = {textContent: ''};
  const context = {document: {getElementById: id => id === 'overview-omero-status' ? status : null}, fetch: async () => ({ok: false, status: 403})};
  vm.runInNewContext(fs.readFileSync('static/js/storage_overview.js', 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  assert.match(status.textContent, /verify your OMERO group/);
});
