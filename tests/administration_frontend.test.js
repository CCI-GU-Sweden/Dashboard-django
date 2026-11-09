const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('administration filters and sorts saved account data', () => {
  const input = value => ({value, listeners: {}, addEventListener(type, fn) {this.listeners[type] = fn;}});
  const account = (name, role, status, group, joined) => ({dataset: {name, role, status, joined}, cells: [{}, {textContent: `${name}@example.org`}], hidden: false, querySelector(selector) {return selector === '.group-summary' ? {textContent: group} : null;}});
  const accounts = [account('Zoe', 'staff', 'active', '', '2026-01-01'), account('Ada', 'researcher', 'active', 'Microscopy', '2026-02-01'), account('Bob', 'researcher', 'disabled', 'Imaging', '2026-03-01')];
  const body = {children: [], querySelectorAll: () => accounts, append(row) {this.children.push(row);}};
  const elements = {'account-rows': body, 'account-search': input(''), 'account-role-filter': input('all'), 'account-status-filter': input('all'), 'account-sort': input('name'), 'account-count': {}, 'accounts-empty': {}};
  const context = {document: {getElementById: id => elements[id], querySelectorAll: () => []}};
  vm.runInNewContext(fs.readFileSync('static/js/administration.js', 'utf8'), context);
  assert.deepEqual(body.children.map(row => row.dataset.name), ['Ada', 'Bob', 'Zoe']);
  elements['account-role-filter'].value = 'researcher'; elements['account-status-filter'].value = 'active';
  elements['account-role-filter'].listeners.change();
  assert.equal(elements['account-count'].textContent, '1 of 3 accounts');
  assert.equal(accounts.find(row => row.dataset.name === 'Ada').hidden, false);
  elements['account-search'].value = 'Imaging'; elements['account-search'].listeners.input();
  assert.equal(elements['account-count'].textContent, '0 of 3 accounts');
  assert.equal(elements['accounts-empty'].hidden, false);
});
