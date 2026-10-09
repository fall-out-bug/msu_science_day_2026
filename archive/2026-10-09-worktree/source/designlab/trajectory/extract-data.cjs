/* Extract unchanged image URIs and provenance. Run from this directory. */
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const root = path.resolve(__dirname, '../..');
const sandbox = { window: {} };
vm.createContext(sandbox);
for (const name of ['data.js', 'nightshift-evidence.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, 'app', name), 'utf8'), sandbox);
}
const cases = ['s02', 's07'].map(id => {
  const item = sandbox.window.GAME_DATA.contact.find(c => c.id === id);
  return { id, name: item.name, frames: item.frames, observations: item.observations,
    ra: item.ra, dec: item.dec, source: item.source,
    truth: sandbox.window.NIGHTSHIFT_EVIDENCE[id] };
});
fs.writeFileSync(path.join(__dirname, 'labdata.js'),
  '// Real ZTF previews, copied unchanged; regenerate with extract-data.cjs.\n' +
  'window.TRAJECTORY_DATA = ' + JSON.stringify(cases) + ';\n');
console.log('Extracted', cases.length, 'cases with unchanged data URI frames.');
