const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('equipment editor opens with the selected equipment and its active state', async () => {
  const element = () => ({children: [], listeners: {}, attributes: {}, textContent: '', hidden: false,
    append(...items) {this.children.push(...items);}, replaceChildren(...items) {this.children = items;},
    addEventListener(name, callback) {this.listeners[name] = callback;}, setAttribute(name, value) {this.attributes[name] = value;},
    showModal() {this.open = true;}, close() {this.open = false;}, focus() {this.focused = true;}});
  const ids = ['equipment-dialog', 'equipment-form', 'equipment-form-title', 'equipment-active-label', 'equipment-cancel-edit', 'equipment-error', 'equipment-list', 'equipment-categories', 'manage-equipment', 'close-equipment', 'close-equipment-footer'];
  const elements = Object.fromEntries(ids.map(id => [id, element()]));
  const form = elements['equipment-form']; form.reset = () => {}; form.elements = {name: element(), category: element(), active: element(), csrfmiddlewaretoken: {value: 'token'}};
  const context = {document: {getElementById: id => elements[id], createElement: element}, window: {location: {search: ''}}, URLSearchParams,
    fetch: async () => ({ok: true, json: async () => ({equipment: [{id: 'scope', name: 'Scope', category: 'Microscope', active: false}]})})};
  vm.runInNewContext(fs.readFileSync('static/js/equipment_manager.js', 'utf8'), context);
  await elements['manage-equipment'].listeners.click();
  assert.equal(elements['equipment-dialog'].open, true);
  const row = elements['equipment-list'].children[0];
  assert.match(row.children[0].textContent, /Scope.*Inactive/);
  row.children[1].listeners.click();
  assert.equal(form.elements.name.value, 'Scope');
  assert.equal(form.elements.active.checked, false);
  assert.equal(elements['equipment-active-label'].hidden, false);
});
