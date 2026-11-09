const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('ticket list groups equipment, formats codes and loads images only on request', async () => {
  function element(tag = 'div') {
    return {tag, children: [], listeners: {}, attributes: {}, value: '', textContent: '',
      append(...items) {this.children.push(...items);}, replaceChildren(...items) {this.children = items;},
      addEventListener(type, fn) {this.listeners[type] = fn;}, setAttribute(key, value) {this.attributes[key] = value;}, getAttribute(key) {return this.attributes[key];},
      after(item) {this.expanded = item;}, querySelector(selector) {return selector === 'img' ? this.children.find(child => child.tag === 'img') : null;},
    };
  }
  const ids = ['ticket-rows', 'ticket-status', 'search', 'reporter', 'message', 'microscope', 'startDate', 'endDate', 'dateField', 'issueType', 'type', 'priority', 'source', 'sort', 'order', 'status', 'previous', 'next', 'refresh', 'ticket-search', 'create-form', 'create-dialog', 'add-ticket', 'close-ticket', 'cancel-ticket', 'update-dialog', 'update-form', 'close-update', 'cancel-update', 'reload-update', 'create-equipment', 'total', 'active', 'resolved'];
  const elements = Object.fromEntries(ids.map(id => [id, element()])); elements.status.value = 'active';
  const item = {ticket_id: '7', reporter_name: 'A', microscope: 'scope', message: 'Problem', ticket_type: 'INTERNAL_ISSUE', priority: 'NORMAL', status: 'OPEN', image_count: 1};
  const detail = {...item, events: [], images: [{id: '3', filename: 'image.png'}]};
  const requests = [];
  const context = {document: {getElementById: id => elements[id], createElement: element}, URLSearchParams, Intl, Date, setTimeout, crypto: {randomUUID: () => 'test'},
    fetch: async url => {requests.push(url); return {ok: true, json: async () => url.endsWith('/equipment') ? {equipment: [{id: 'scope', name: 'Microscope A', category: 'MICROSCOPE'}]} : url.endsWith('/staff') ? {staff: []} : url.endsWith('/summary') ? {total: 1, active: 1, resolved: 0} : url === '/api/tickets/7' ? detail : {count: 1, page: 1, page_size: 50, results: [item]}};}};
  vm.runInNewContext(fs.readFileSync('static/js/tickets.js', 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(elements.microscope.children[0].tag, 'optgroup');
  assert.equal(elements.microscope.children[0].label, 'Microscope');
  const row = elements['ticket-rows'].children[0];
  assert.equal(row.children[4].textContent, 'Microscope A');
  assert.equal(row.children[6].textContent, 'Internal issue / Normal');
  await row.children[0].children[0].listeners.click();
  const panel = row.expanded.children[0].children[0];
  const gallery = panel.children.find(child => child.className === 'ticket-gallery');
  assert.equal(gallery.children[0].querySelector('img'), undefined);
  gallery.children[0].children[1].listeners.click();
  assert.equal(gallery.children[0].querySelector('img').src, '/api/tickets/7/images/3');
  assert.equal(requests.some(url => url.includes('/images/')), false);
});
