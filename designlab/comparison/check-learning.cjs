/* Fixed lesson checks: no truth names or source pixels enter the learner. */
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const box = { window: {} }; vm.createContext(box);
for (const file of ['data.js', 'learning-data.js', 'learning-model.js']) vm.runInContext(fs.readFileSync(path.join(__dirname, file), 'utf8'), box);
const M = box.window.LearningModel, DATA = box.window.COMPARISON_DATA, L = box.window.LEARNING_DATA;
const R = JSON.parse(fs.readFileSync(path.join(__dirname, 'learning-reference.json'), 'utf8'));
const check = (name, run) => { run(); checks.push(name); }, checks = [];
const trainField = DATA.cases.find(row => row.id === L.trainCase), reservedField = DATA.cases.find(row => row.id === L.reservedCase);
const train = M.generate(trainField, L.pixelScaleArcsec.s02), reserved = M.generate(reservedField, L.pixelScaleArcsec.s07), fitted = M.fit(train);
const decisions = (labels, query = reserved) => M.score(train, labels, query, fitted);
const accepted = values => values.filter(row => row.accepted).length;
const plain = value => JSON.parse(JSON.stringify(value));

check('runtime extraction matches independent Python coordinates and features', () => {
  for (const field of [train, reserved]) {
    const reference = R.fields[field.caseId];
    assert.equal(field.candidates.length, reference.candidates.length);
    field.candidates.forEach((row, index) => {
      assert.equal(JSON.stringify(plain(row.points)), JSON.stringify(plain(reference.candidates[index].points)));
      row.feature.forEach((value, column) => assert(Math.abs(value - reference.candidates[index].feature[column]) < 1e-12));
    });
  }
  fitted.scale.forEach((value, i) => assert(Math.abs(value - R.scale[i]) < 1e-12));
});
check('source data hash is intact before lesson extraction', () => {
  const hash = crypto.createHash('sha256').update(fs.readFileSync(path.join(__dirname, 'data.js'))).digest('hex');
  const provenance = JSON.parse(fs.readFileSync(path.join(__dirname, 'learning-provenance.json'), 'utf8'));
  assert.equal(hash, provenance.source.data_js_sha256);
  assert.deepEqual([train.candidates.length, reserved.candidates.length], provenance.validation.source_tuples);
});
check('initial examples contain one same-object and four stationary wrong links', () => {
  assert.equal(L.initialExamples.filter(row => row.label === 'sameObject').length, 1);
  assert.equal(L.initialExamples.filter(row => row.label === 'wrongLink').length, 4);
  const ids = new Set(L.initialExamples.map(row => row.id)); assert.equal(ids.size, 5);
});
check('vector mismatch sees a turn even when the two speeds are equal', () => {
  const straight = { id: 'straight', dates: ['2020-01-01T00:00:00Z', '2020-01-01T01:00:00Z', '2020-01-01T02:00:00Z'], sources: [[{ x: 0, y: 0, peak: 10 }], [{ x: 3, y: 0, peak: 10 }], [{ x: 6, y: 0, peak: 10 }]] };
  const turn = { ...straight, sources: [[{ x: 0, y: 0, peak: 10 }], [{ x: 3, y: 0, peak: 10 }], [{ x: 3, y: 3, peak: 10 }]] };
  const a = M.generate(straight, 1).candidates[0].feature, b = M.generate(turn, 1).candidates[0].feature;
  assert.equal(a[0], b[0]); assert.equal(a[1], 0); assert(b[1] > 1);
});
check('labels affect transfer to the reserved other field', () => {
  const corrected = [...L.initialExamples, { id: L.correction.id, label: 'wrongLink' }];
  assert.notDeepEqual(plain(decisions(L.initialExamples)), plain(decisions(corrected)));
  assert.notEqual(accepted(decisions(L.initialExamples)), accepted(decisions(corrected)));
});
check('calling the wrong triple same-object makes its own score worse as a filter', () => {
  const correct = decisions([...L.initialExamples, { id: L.correction.id, label: 'wrongLink' }], train);
  const wrong = decisions([...L.initialExamples, { id: L.correction.id, label: 'sameObject' }], train);
  const a = correct.find(row => row.id === L.correction.id), b = wrong.find(row => row.id === L.correction.id);
  assert(a.acceptanceScore < 0); assert(b.acceptanceScore > 0);
});
check('undo returns the exact original transfer decisions', () => {
  const before = decisions(L.initialExamples);
  const corrected = decisions([...L.initialExamples, { id: L.correction.id, label: 'wrongLink' }]);
  const removed = decisions(L.initialExamples.slice());
  assert.notDeepEqual(plain(before), plain(corrected));
  assert.deepEqual(plain(before), plain(removed));
});
check('repeating the same correction is idempotent', () => {
  const once = decisions([...L.initialExamples, { id: L.correction.id, label: 'wrongLink' }]);
  const twice = decisions([...L.initialExamples, { id: L.correction.id, label: 'wrongLink' }, { id: L.correction.id, label: 'wrongLink' }]);
  assert.deepEqual(plain(once), plain(twice));
});
check('generate and score do not read names, identities or image pixels', () => {
  const limited = { id: trainField.id, dates: trainField.dates, sources: trainField.sources };
  Object.defineProperties(limited, Object.fromEntries(['name', 'arrays', 'truth', 'knownObject'].map(key => [key, { get() { throw Error(key); } }])));
  const generated = M.generate(limited, L.pixelScaleArcsec.s02);
  assert.equal(generated.candidates.length, train.candidates.length);
  const labels = L.initialExamples.map(row => ({ ...row }));
  assert.equal(decisions(labels).length, reserved.candidates.length);
});
console.log(JSON.stringify({ count: checks.length, checks, candidates: { train: train.candidates.length, reserved: reserved.candidates.length }, reservedAccepted: { before: accepted(decisions(L.initialExamples)), after: accepted(decisions([...L.initialExamples, { id: L.correction.id, label: 'wrongLink' }])) } }, null, 2));
