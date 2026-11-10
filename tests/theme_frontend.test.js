const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function setup({saved = null, systemDark = false, storageFails = false} = {}) {
  const listeners = {}, windowListeners = {}, mediaListeners = {}, changes = [], plots = [];
  const button = {textContent: '', attributes: {}, setAttribute(key, value) {this.attributes[key] = value;}, addEventListener(name, handler) {listeners[name] = handler;}};
  const chart = {data: [{}]};
  const document = {documentElement: {dataset: {}}, getElementById: id => id === 'theme-toggle' ? button : null,
    querySelectorAll: () => [chart], addEventListener: (name, fn) => {listeners[name] = fn;}};
  const media = {matches: systemDark, addEventListener: (name, fn) => {mediaListeners[name] = fn;}};
  const storage = {getItem() {if (storageFails) throw Error(); return saved;}, setItem(key, value) {if (storageFails) throw Error(); changes.push([key, value]);}};
  const window = {matchMedia: () => media, addEventListener: (name, fn) => {windowListeners[name] = fn;}, Plotly: {relayout: (...args) => plots.push(args)}};
  const context = {document, window, localStorage: storage};
  vm.runInNewContext(fs.readFileSync('static/js/theme.js', 'utf8'), context);
  listeners.DOMContentLoaded();
  return {document, window, media, mediaListeners, listeners, windowListeners, button, changes, plots};
}

test('theme follows system until changed and persists the selected mode', () => {
  const page = setup({systemDark: true});
  assert.equal(page.document.documentElement.dataset.theme, 'dark');
  assert.equal(page.button.attributes['aria-pressed'], 'true');
  assert.equal(page.window.dashboardTheme.plotlyLayout().font.color, '#cbd5e1');
  page.listeners.click();
  assert.equal(page.document.documentElement.dataset.theme, 'light');
  assert.deepEqual(page.changes[0], ['cci-dashboard-theme', 'light']);
  assert.equal(page.plots.at(-1)[1]['font.color'], '#475569');
  page.media.matches = true; page.mediaListeners.change();
  assert.equal(page.document.documentElement.dataset.theme, 'light');
  page.windowListeners.storage({key: 'cci-dashboard-theme', newValue: 'dark'});
  assert.equal(page.document.documentElement.dataset.theme, 'dark');
});

test('saved preference wins and unavailable storage does not break the toggle', () => {
  const saved = setup({saved: 'light', systemDark: true});
  assert.equal(saved.document.documentElement.dataset.theme, 'light');
  const blocked = setup({storageFails: true});
  blocked.listeners.click();
  assert.equal(blocked.document.documentElement.dataset.theme, 'dark');
});

test('system changes update the page when no preference was saved', () => {
  const page = setup();
  page.media.matches = true;
  page.mediaListeners.change();
  assert.equal(page.document.documentElement.dataset.theme, 'dark');
  assert.equal(page.plots.at(-1)[1]['xaxis.gridcolor'], '#39485d');
  assert.equal(page.changes.length, 0);
});
