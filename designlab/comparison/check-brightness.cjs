/* Verify real provenance, independently measured apertures, and causal choices. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const vm = require('node:vm');
const box = { window: {} }; vm.createContext(box);
for (const file of ['brightness-data.js', 'brightness-model.js']) {
  vm.runInContext(fs.readFileSync(path.join(__dirname, file), 'utf8'), box);
}
const { BrightnessModel: M, BRIGHTNESS_DATA: data } = box.window;
const provenance = JSON.parse(fs.readFileSync(path.join(__dirname, 'brightness-provenance.json'), 'utf8'));
const checks = [], check = (name, callback) => { callback(); checks.push(name); };
const plain = value => JSON.parse(JSON.stringify(value));
const hash = filename => crypto.createHash('sha256').update(fs.readFileSync(filename)).digest('hex');
const root = path.resolve(__dirname, '../..');
check('four local FITS hashes and exported data match provenance', () => {
  assert.equal(provenance.inputs.length, 4);
  for (const item of provenance.inputs) assert.equal(hash(path.join(root, item.file)), item.sha256);
  assert.equal(hash(path.join(root, 'assets/discoveries/provenance.json')), provenance.inputProvenanceSha256);
  assert.equal(hash(path.join(__dirname, 'brightness-data.js')), provenance.exportedDataSha256);
});
check('exactly two calibrated science and two pipeline difference images', () => {
  assert.equal(data.dates.length, 2); assert.equal(data.arrays.length, 2);
  assert.equal(data.differenceArrays.length, 2);
  for (const a of [...data.arrays, ...data.differenceArrays]) {
    assert.equal(a.length, 128 * 128); assert(a.every(Number.isFinite));
  }
  assert(data.differenceArrays[0].some(v => v < 0));
  assert(Date.parse(data.dates[1]) > Date.parse(data.dates[0]));
});
check('first-frame peak selection never snaps to a historical position', () => {
  const s = M.select(data, 63.5, 63.5);
  assert.deepEqual(plain(s.point), { x: 65, y: 64 });
  assert(Object.isFrozen(s)); assert(Object.isFrozen(s.point));
  assert.equal(M.select(data, 65, 58.99).status, 'empty');
  assert.equal(M.select(data, 80, 80).status, 'empty');
});
check('select and measure cannot read identity, historical position, or later detections', () => {
  const independent = { arrays: data.arrays, differenceArrays: data.differenceArrays, sources: [data.sources[0]] };
  for (const key of ['historical', 'truth', 'id']) {
    Object.defineProperty(independent, key, { get() { throw Error(`${key} accessed`); } });
  }
  Object.defineProperty(independent.sources, 1, { get() { throw Error('later peaks accessed'); } });
  assert.equal(M.measure(independent, M.select(independent, 65, 64)).outcome, 'faded');
});
check('JavaScript aperture sums reproduce independent Python realdata measurements', () => {
  for (const reference of provenance.independentApertureChecks) {
    const result = M.measure(data, M.select(data, reference.point.x, reference.point.y));
    for (let epoch = 0; epoch < 2; epoch++) {
      assert(Math.abs(result.measurements[epoch].flux - reference.differenceFlux[epoch]) < .01);
      assert(Math.abs(result.measurements[epoch].scienceFlux - reference.scienceFlux[epoch]) < .01);
    }
  }
});
const target = M.measure(data, M.select(data, 65, 64));
const control = M.measure(data, M.select(data, 23, 64));
check('real central blend has a measured decline in pipeline difference flux', () => {
  assert.equal(target.outcome, 'faded'); assert(target.firstFlux > 0);
  assert(target.ratio > .33 && target.ratio < .34);
  assert(target.absoluteChange < -360); assert(target.scienceChangeFraction < -.17);
  assert.equal(target.measurements[0].aperturePixels, 49);
  assert.equal(target.measurements[0].annulusPixels, 248);
});
check('a different real selection produces stable under fixed tolerance gates', () => {
  assert.equal(control.outcome, 'stable');
  assert(Math.abs(control.scienceChangeFraction) < .03);
  assert.equal(control.ratio, null); assert(control.firstFlux < 0);
});
check('edge detections and empty selections remain unresolved', () => {
  for (const p of [[6, 52], [107, 122], [33, 125]]) {
    const result = M.measure(data, M.select(data, ...p));
    assert.equal(result.outcome, 'unresolved');
    assert.equal(result.reason, 'incomplete_background_annulus');
    assert.equal(result.firstFlux, null);
  }
  assert.equal(M.measure(data, M.select(data, 80, 80)).reason, 'no_selected_peak');
});
check('real image counterfactual changes outcome without changing choice', () => {
  const unchanged = { arrays: data.arrays, sources: data.sources,
    differenceArrays: [data.differenceArrays[0], data.differenceArrays[0]] };
  const s = M.select(unchanged, 65, 64);
  assert.deepEqual(plain(s.point), plain(target.point));
  const result = M.measure(unchanged, s);
  assert.equal(result.absoluteChange, 0); assert.equal(result.ratio, 1);
  assert.equal(result.outcome, 'unresolved');
});
function fixture() {
  const baseline = Array.from({ length: 128 * 128 }, (_, i) => 10 + (i % 3) - 1);
  const science = [baseline.slice(), baseline.slice()], difference = [baseline.slice(), baseline.slice()];
  for (const a of science) a[40 * 128 + 40] += 2000;
  difference[0][40 * 128 + 40] += 1000;
  difference[1][40 * 128 + 40] += 250;
  return { arrays: science, differenceArrays: difference,
    sources: [[{ x: 40, y: 40, peak: 200 }]] };
}
check('synthetic pixel changes cause faded, stable, or unresolved outcomes', () => {
  const c = fixture(), s = M.select(c, 40, 40);
  assert.equal(M.measure(c, s).outcome, 'faded');
  c.differenceArrays[1] = c.differenceArrays[0].slice();
  assert.equal(M.measure(c, s).outcome, 'unresolved');
  c.differenceArrays = c.arrays.map(a => a.map((v, i) => i === 40 * 128 + 40 ? 10 : v));
  assert.equal(M.measure(c, s).outcome, 'stable');
});
check('crowded clicks are ambiguous and invalid local pixels fail explicitly', () => {
  const c = fixture(); c.sources[0].push({ x: 42, y: 40, peak: 200 });
  assert.equal(M.select(c, 41, 40).status, 'ambiguous');
  c.differenceArrays[0][40 * 128 + 40] = NaN;
  assert.throws(() => M.measure(c, M.select(c, 40, 40)), /Non-finite/);
});
check('measurement reports and selected positions are immutable', () => {
  assert(Object.isFrozen(target)); assert(Object.isFrozen(target.point));
  assert(Object.isFrozen(target.measurements)); assert(Object.isFrozen(target.measurements[0]));
});
console.log(JSON.stringify({ count: checks.length, checks, target, control,
  scientificLimits: provenance.limits }, null, 2));
