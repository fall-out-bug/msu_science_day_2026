/* Validate exported archive fields and evaluate current unmodified instrument models. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const here = __dirname;
const context = vm.createContext({ console });
for (const file of ['tracking.js', 'brightness-model.js', 'launch-model.js', 'archive-data.js']) {
  vm.runInContext(fs.readFileSync(path.join(here, file), 'utf8'), context, { filename: file });
}
const { ARCHIVE_DATA, TrackingModel, LaunchModel } = context;
const provenance = JSON.parse(fs.readFileSync(path.join(here, 'archive-provenance.json'), 'utf8'));
const median = values => {
  const copy = [...values].sort((a, b) => a - b), middle = Math.floor(copy.length / 2);
  return copy.length % 2 ? copy[middle] : (copy[middle - 1] + copy[middle]) / 2;
};
function aperture(array, point) { // independent numeric repetition of Python check
  const inside = [], ring = [];
  for (let y = Math.ceil(point.y - 12); y <= Math.floor(point.y + 12); y++) for (let x = Math.ceil(point.x - 12); x <= Math.floor(point.x + 12); x++) {
    const d2 = (x - point.x) ** 2 + (y - point.y) ** 2;
    if (d2 <= 16) inside.push(array[y * 128 + x]);
    if (d2 >= 64 && d2 <= 144) ring.push(array[y * 128 + x]);
  }
  const background = median(ring);
  return inside.reduce((sum, value) => sum + value - background, 0);
}
assert.equal(ARCHIVE_DATA.cases.length, 4);
const outcome = {};
for (const field of ARCHIVE_DATA.cases) {
  assert.equal(field.arrays.length, 3, `${field.id}: three epochs`);
  assert.equal(field.sources.length, 3, `${field.id}: source epochs`);
  assert.equal(new Set(field.dates).size, 3, `${field.id}: distinct dates`);
  assert.deepEqual(field.dates.slice().sort(), field.dates, `${field.id}: chronological`);
  for (const array of field.arrays) assert.equal(array.length, 128 * 128, `${field.id}: pixels`);
  for (const list of field.sources) assert.ok(list.length > 0 && list.every(p =>
    Number.isFinite(p.x) && Number.isFinite(p.y) && p.peak > 0), `${field.id}: blind peaks`);
  const first = field.sources[0][0];
  const track = TrackingModel.select(field, first.x, first.y);
  const target = provenance.cases.find(row => row.id === field.id).independentTargetApertureCheck;
  target.scienceFlux.forEach((value, epoch) => assert.ok(Math.abs(aperture(field.arrays[epoch], target.point) - value) < 1e-2,
    `${field.id}: independent aperture epoch ${epoch}`));
  const movement = LaunchModel.scan(field, 'movement');
  const fading = LaunchModel.scan(field, 'fading');
  outcome[field.id] = { tracking: track.kind, brightness: 'not_evaluated_without_pipeline_difference',
    movement: movement.reason, fading: fading.reason,
    movementCandidates: movement.candidates.length, fadingCandidates: fading.candidates.length };
}
console.log(JSON.stringify({ cases: ARCHIVE_DATA.cases.map(c => c.id), outcome }));
