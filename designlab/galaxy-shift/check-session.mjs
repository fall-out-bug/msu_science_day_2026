import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const GalaxyModel = require('./model.js');

function loadGlobal(file, name) {
  const sandbox = {};
  vm.runInNewContext(fs.readFileSync(new URL(file, import.meta.url), 'utf8'), sandbox);
  return sandbox[name];
}

const base = loadGlobal('./data.js', 'GALAXY_DATA');
const archive = loadGlobal('./archive-data.js', 'GALAXY_ARCHIVE');
const sessionSandbox = { crypto: { getRandomValues(values) { values[0] = sequence++ >>> 0; return values; } } };
let sequence = 0;
vm.runInNewContext(fs.readFileSync(new URL('./session.js', import.meta.url), 'utf8'), sessionSandbox);
const { create, choose, combinations } = sessionSandbox.GalaxySession;

assert.equal(archive.images.length, 24);
for (const label of base.classes.map(item => item.id)) assert.equal(archive.images.filter(item => item.label === label).length, 8);
assert.equal(Object.keys(archive.features).length, 36, '15 original plus 21 newly admitted images');
assert.ok(Object.values(archive.features).every(vector => vector.length === 14 && vector.every(Number.isFinite)));

const all = combinations(base, archive);
assert.equal(all.length, 512, '8 × 8 × 8 possible one-per-class shifts');
assert.equal(new Set(all.map(ids => [...ids].sort().join(','))).size, 512);

const values = new Map();
const storage = { getItem(key) { return values.get(key) ?? null; }, setItem(key, value) { values.set(key, value); } };
const chosen = [];
for (let i = 0; i < 512; i++) chosen.push(choose(base, archive, storage));
assert.equal(new Set(chosen.map(ids => [...ids].sort().join(','))).size, 512, 'choice must exhaust every unique combination before repeating');
for (const ids of chosen) {
  assert.equal(ids.length, 3);
  assert.deepEqual(new Set(ids.map(id => archive.images.find(item => item.id === id).label)), new Set(base.classes.map(item => item.id)));
}
const afterExhaustion = choose(base, archive, storage);
assert.notDeepEqual([...afterExhaustion].sort(), [...chosen.at(-1)].sort(), 'cycle boundary must not repeat the immediately previous shift');

const parity = create(base, archive, base.childIds);
assert.equal(JSON.stringify(parity.experiments), JSON.stringify(base.experiments), 'the original child trio must retain all 243 precomputed outcomes');
assert.equal(JSON.stringify(create(base, archive, base.childIds).experiments), JSON.stringify(parity.experiments), 'same archive vectors give the same neighbours and outcomes');

const selected = create(base, archive, all[17]);
assert.equal(Object.keys(selected.experiments).length, 243);
assert.equal(selected.protocol.trainingIds.length, 9);
const train = new Set(selected.protocol.trainingIds);
const selectedSet = new Set(selected.sessionIds);
for (const image of selected.images) {
  if (selectedSet.has(image.id)) assert.equal(image.split, 'train');
  if (archive.images.some(item => item.id === image.id) && !selectedSet.has(image.id)) assert.equal(image.split, 'archive', 'unselected archive images cannot enter training');
}
for (const result of Object.values(selected.experiments)) {
  for (const split of ['review', 'final']) {
    for (const prediction of result[split].predictions) {
      assert.ok(train.has(prediction.neighborId), 'prediction must only use the nine current training images');
      assert.ok(!base.protocol.reviewIds.includes(prediction.neighborId));
      assert.ok(!base.protocol.finalIds.includes(prediction.neighborId));
    }
  }
}
assert.throws(() => create(base, archive, [base.childIds[0], 'archive_ngc4889', 'archive_ngc1132']), /Неверная подборка/);
assert.throws(() => create(base, archive, ['archive_m101', 'archive_m81', 'archive_m83']), /Неверная подборка/);

// A correction must be evaluated from the current five labels, not from the
// first result.  The final set is intentionally independent of review, so its
// score is not expected to improve by a fixed amount.
for (const ids of all) {
  const shift = create(base, archive, ids);
  const images = Object.fromEntries(shift.images.map(image => [image.id, image]));
  const expectedKey = shift.editableIds
    .map(id => shift.classes.findIndex(item => item.id === images[id].label))
    .join('');
  const game = GalaxyModel.create(shift);
  game.dispatch({ type: 'START' });
  game.dispatch({ type: 'LABELS' });
  for (const id of shift.childIds) game.dispatch({ type: 'SET_LABEL', id, label: images[id].label });
  game.dispatch({ type: 'RUN' });
  game.dispatch({ type: 'REPAIR' });
  for (const id of shift.oldIds) game.dispatch({ type: 'SET_LABEL', id, label: images[id].label });
  assert.equal(game.state.current, null, 'a corrected old label invalidates the prior result');
  game.dispatch({ type: 'RUN' });
  assert.equal(game.state.current.key, expectedKey);
  assert.equal(game.state.repairCheckedKey, expectedKey);
  assert.deepEqual(game.state.current.final, shift.experiments[expectedKey].final);
  game.dispatch({ type: 'FINISH' });
  assert.equal(game.state.phase, 'final');
}

console.log(JSON.stringify({ status: 'PASS', combinations: all.length, states: Object.keys(selected.experiments).length, features: Object.keys(archive.features).length, checks: ['unique 512-cycle', 'one per class', 'original 243-state parity', 'reproducible vectors and neighbours', 'train-only no leakage', 'invalid selections', 'all-shifts correction invalidation and current final result'] }, null, 2));
