const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('inventory expands fileset details and shows the active badge', async () => {
  function element() {
    return {children: [], listeners: {}, attributes: {}, value: '', textContent: '',
      append(...items) {this.children.push(...items);},
      replaceChildren(...items) {this.children = items;},
      addEventListener(name, fn) {this.listeners[name] = fn;},
      setAttribute(name, value) {this.attributes[name] = value;},
      getAttribute(name) {return this.attributes[name];},
      after(item) {this.inserted = item;},
    };
  }
  const ids = ['filesets', 'storage-status', 'previous', 'next', 'generate-email', 'search', 'group_id', 'status', 'imported', 'size', 'order', 'storage-search', 'refresh'];
  const elements = Object.fromEntries(ids.map(id => [id, element()]));
  Object.assign(elements.group_id, {value: 'all'}); Object.assign(elements.status, {value: 'active'});
  Object.assign(elements.imported, {value: 'all'}); Object.assign(elements.size, {value: 'any'}); Object.assign(elements.order, {value: 'largest'});
  const context = {document: {getElementById: id => elements[id], createElement: element}, URLSearchParams, setTimeout, clearTimeout,
    fetch: async url => ({ok: true, json: async () => url === '/api/omero/groups' ? {groups: []} : url.includes('/filesets/') ? {locations: [{project_name: 'Project', project_id: 1, dataset_name: 'Dataset', dataset_id: 2}], source_file_names: ['image.czi'], uncontained_image_count: 0, missing_runs: 0} : {count: 1, page: 1, page_size: 50, results: [{fileset_id: '7', username: 'owner', group_name: 'Group', total_bytes: 100, deleted_at: null}]}})};
  vm.runInNewContext(fs.readFileSync('static/js/storage.js', 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  const row = elements.filesets.children[0];
  assert.equal(row.children.at(-1).children[0].textContent, 'Active');
  const button = row.children[0].children[0];
  await button.listeners.click();
  assert.equal(button.getAttribute('aria-expanded'), 'true');
  const details = row.inserted.children[0].children[0];
  assert.match(details.children[0].children[1].textContent, /Project.*Dataset/);
  assert.equal(details.children.at(-1).children[1].textContent, 'image.czi');
});
