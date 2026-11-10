const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('ticket list groups equipment, formats codes and loads images only on request', async () => {
  function element(tag = 'div') {
    return {tag, children: [], listeners: {}, attributes: {}, value: '', textContent: '',
      append(...items) {this.children.push(...items);}, replaceChildren(...items) {this.children = items;},
      addEventListener(type, fn) {this.listeners[type] = fn;}, setAttribute(key, value) {this.attributes[key] = value;}, getAttribute(key) {return this.attributes[key];},
      get options() {return this.children.flatMap(child => child.tag === 'optgroup' ? child.children : [child]);},
      after(item) {this.expanded = item;}, querySelector(selector) {return selector === 'img' ? this.children.find(child => child.tag === 'img') : selector === '[type=submit]' ? this.submitButton : null;},
      querySelectorAll(selector) {const inputs = this.children.flatMap(child => child.children || []).filter(child => child.tag === 'input' && child.type === 'checkbox'); return selector.endsWith(':checked') ? inputs.filter(input => input.checked) : inputs;},
      showModal() {this.open = true;}, close() {this.open = false;},
    };
  }
  const ids = ['ticket-rows', 'ticket-status', 'search', 'reporter', 'message', 'microscope', 'startDate', 'endDate', 'dateField', 'issueType', 'type', 'priority', 'source', 'sort', 'order', 'status', 'previous', 'next', 'refresh', 'ticket-search', 'create-form', 'create-dialog', 'add-ticket', 'close-ticket', 'cancel-ticket', 'update-dialog', 'update-form', 'close-update', 'cancel-update', 'reload-update', 'create-equipment', 'total', 'active', 'resolved', 'ticket-tag-dialog', 'ticket-tag-title', 'ticket-tag-error', 'ticket-tag-choices', 'ticket-tag-close', 'ticket-tag-cancel', 'ticket-tag-clear', 'ticket-tag-form'];
  const elements = Object.fromEntries(ids.map(id => [id, element()])); elements.status.value = 'active';
  elements['ticket-tag-form'].submitButton = element('button'); elements['update-form'].elements = {csrfmiddlewaretoken: {value: 'csrf'}};
  const item = {ticket_id: '7', reporter_name: 'A', microscope: 'scope', message: 'Problem', ticket_type: 'INTERNAL_ISSUE', priority: 'NORMAL', status: 'OPEN', image_count: 1};
  const detail = {...item, events: [], images: [{id: '3', filename: 'image.png'}]};
  const requests = [], writes = [];
  const context = {document: {getElementById: id => elements[id], createElement: element, addEventListener() {}}, window: {prompt: () => '   ', confirm: () => true}, URLSearchParams, Intl, Date, setTimeout, crypto: {randomUUID: () => 'test'},
    fetch: async (url, options = {}) => {requests.push(url); if (options.method === 'PATCH') writes.push(JSON.parse(options.body)); return {ok: true, json: async () => url.endsWith('/equipment') ? {equipment: [{id: 'scope', name: 'Microscope A', category: 'Microscope', active: true}]} : url === '/api/tickets/tags' ? {tags: [{id: '1', name: 'Software'}, {id: '2', name: 'Optics'}]} : url.endsWith('/tags') ? {tags: [{id: '1', name: 'Software'}]} : url.endsWith('/staff') ? {staff: []} : url.endsWith('/researchers') ? {researchers: []} : url.endsWith('/researcher') ? {researcher_id: null} : url.endsWith('/summary') ? {total: 1, active: 1, resolved: 0} : url === '/api/tickets/7' ? detail : {count: 1, page: 1, page_size: 50, results: [item]}};}};
  vm.runInNewContext(fs.readFileSync('static/js/tickets.js', 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(elements.microscope.children[2].tag, 'optgroup');
  assert.equal(elements.microscope.children[2].label, 'Microscope');
  const row = elements['ticket-rows'].children[0];
  assert.equal(row.children[4].textContent, 'Microscope A');
  assert.equal(row.children[6].textContent, 'Technical issue / Normal');
  await row.children[12].children[1].listeners.click();
  assert.equal(elements['ticket-tag-dialog'].open, true);
  assert.equal(elements['ticket-tag-choices'].children[0].children[0].checked, true);
  elements['ticket-tag-choices'].children[1].children[0].checked = true;
  await elements['ticket-tag-form'].listeners.submit({preventDefault() {}});
  assert.deepEqual(writes[0], {tags: ['1', '2'], expected: ['1']});
  await row.children[12].children[1].listeners.click();
  elements['ticket-tag-clear'].listeners.click();
  await elements['ticket-tag-form'].listeners.submit({preventDefault() {}});
  assert.deepEqual(writes[1], {tags: [], expected: ['1']});
  await row.children[12].children.at(-1).listeners.click();
  assert.match(elements['ticket-status'].textContent, /Enter a reason/);
  assert.equal(requests.some(url => url.includes('archive-action')), false);
  await row.children[0].children[0].listeners.click();
  const panel = row.expanded.children[0].children[0];
  const gallery = panel.children.find(child => child.className === 'ticket-gallery');
  assert.equal(gallery.children[0].querySelector('img'), undefined);
  gallery.children[0].children[1].listeners.click();
  assert.equal(gallery.children[0].querySelector('img').src, '/api/tickets/7/images/3');
  assert.equal(requests.some(url => url.includes('/images/')), false);
});
