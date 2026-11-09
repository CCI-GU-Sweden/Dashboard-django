const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('policy table shows one group row and expands its dated history', async () => {
  function element() {
    return {children: [], listeners: {}, attributes: {}, dataset: {}, value: '', textContent: '', hidden: false,
      append(...items) {this.children.push(...items);}, replaceChildren(...items) {this.children = items;},
      get firstElementChild() {return this.children[0];}, get lastElementChild() {return this.children.at(-1);},
      addEventListener(name, fn) {this.listeners[name] = fn;},
      setAttribute(name, value) {this.attributes[name] = value;}, getAttribute(name) {return this.attributes[name];},
      after(item) {this.expandedRow = item;},
    };
  }
  const ids = ['history-period', 'history-status', 'refresh', 'panel-policies', 'policies-rows', 'policies-status'];
  const elements = Object.fromEntries(ids.map(id => [id, element()])); elements['history-period'].value = '30';
  const tab = element(); tab.dataset.tab = 'policies'; tab.parentElement = {classList: {toggle() {}}};
  const records = [
    {group_id: '5', group_name: 'Group A', policy_type: 'CORE', valid_from: '2026-01-01'},
    {group_id: '5', group_name: 'Group A', policy_type: 'TEMPORARY', valid_from: '2025-01-01', valid_until: '2025-12-31'},
    {group_id: '6', group_name: 'Group B', policy_type: 'AGREEMENT', valid_from: '2025-01-01'},
  ];
  const context = {document: {getElementById: id => elements[id] || null, createElement: element, querySelectorAll: selector => selector === '[data-tab]' ? [tab] : []}, URLSearchParams, Intl, Date,
    fetch: async url => ({ok: true, json: async () => url.includes('/admin/policies') ? {rows: records} : {history: [], metric: 'bytes'}}),
    Plotly: {react: async () => {}},
  };
  vm.runInNewContext(fs.readFileSync('static/js/storage_dashboard.js', 'utf8'), context);
  tab.listeners.click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(elements['policies-rows'].children.length, 2);
  const group = elements['policies-rows'].children[0];
  assert.equal(group.children[1].textContent, 'Group A');
  assert.equal(group.children[2].textContent, 'CORE');
  const toggle = group.firstElementChild.firstElementChild;
  toggle.listeners.click();
  assert.equal(toggle.getAttribute('aria-expanded'), 'true');
  const historyTable = group.expandedRow.firstElementChild.firstElementChild.children[1];
  assert.equal(historyTable.children[1].children.length, 2);
  assert.equal(historyTable.children[1].children[1].children[0].textContent, 'TEMPORARY');
});
