'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const root = { window: {} };
vm.createContext(root);
for (const file of ['data.js', 'tracking.js', 'launch-data.js', 'launch-model.js']) {
  vm.runInContext(fs.readFileSync(path.join(__dirname, file), 'utf8'), root, { filename: file });
}
const { LAUNCH_DATA, LaunchModel } = root.window;
const provenance = JSON.parse(fs.readFileSync(path.join(__dirname, 'launch-provenance.json'), 'utf8'));
const hash = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
assert.equal(hash(path.join(__dirname, 'launch-data.js')), provenance.exportedDataSha256);
assert.equal(hash(path.join(__dirname, 'data.js')), provenance.movementReference.sha256);
assert.equal(hash(path.join(__dirname, 'provenance.json')), provenance.movementReference.provenanceSha256);
for (const input of [...provenance.inputs, ...provenance.movementReference.inputs]) {
  assert.equal(hash(path.join(__dirname, '../..', input.file)), input.sha256);
}
const output = [];
for (const data of LAUNCH_DATA.cases) {
  assert.equal(data.arrays.length, 3);
  for (const array of data.arrays) {
    assert.equal(array.length, 128 * 128);
    assert.ok(array.every(Number.isFinite));
  }
  assert.ok(data.dates.every((date, i) => i === 0 || Date.parse(date) > Date.parse(data.dates[i - 1])));
  for (const mode of ['movement', 'fading']) {
    const scan = LaunchModel.scan(data, mode);
    assert.equal(scan.inspectedCount, data.sources[mode === 'movement' ? 1 : 0].length);
    // The scan must never consult withheld third pixels/detections.
    const withheld = { ...data, arrays: [data.arrays[0], data.arrays[1]],
      sources: [data.sources[0], data.sources[1]] };
    assert.equal(JSON.stringify(LaunchModel.scan(withheld, mode)), JSON.stringify(scan));
    const guarded = { ...withheld };
    for (const key of ['id', 'name', 'historical', 'label', 'truth']) {
      Object.defineProperty(guarded, key, { get() { throw Error(`${key} accessed by scan`); } });
    }
    assert.equal(JSON.stringify(LaunchModel.scan(guarded, mode)), JSON.stringify(scan));
    const renamed = { ...data, id: 'unknown', name: 'unknown', historical: null, label: 'unknown' };
    assert.equal(JSON.stringify(LaunchModel.scan(renamed, mode)), JSON.stringify(scan));
    assert.equal(LaunchModel.verify(data, mode, { id: 'invented', point: { x: 0, y: 0 } }).outcome,
      'unresolved');
    const verified = scan.candidates.map(candidate => LaunchModel.verify(data, mode, candidate));
    output.push({ id: data.id, mode, inspectedCount: scan.inspectedCount, reason: scan.reason,
      points: scan.candidates.map(c => c.point), controls: scan.controls, verified });
  }
}
const movement = output.find(r => r.id === 'launch-motion' && r.mode === 'movement');
assert.equal(movement.verified.length, 1);
assert.equal(movement.verified[0].outcome, 'moving');
// Destroying third detections must invalidate confirmation without altering scan.
const motionData = LAUNCH_DATA.cases.find(c => c.id === 'launch-motion');
assert.equal(LaunchModel.verify({ ...motionData, sources: [motionData.sources[0],
  motionData.sources[1], []] }, 'movement', LaunchModel.scan(motionData, 'movement').candidates[0]).outcome, 'lost');
const variable = output.find(r => r.id === 'launch-variable' && r.mode === 'fading');
assert.ok(variable.verified.length > 0);
assert.equal(variable.verified[0].outcome, 'faded');
assert.equal(variable.verified[0].thirdOutcome, 'rebrightened');
assert.equal(variable.verified[0].sustainedFade, false);
// An independent Python aperture calculation checks every accepted variable proposal.
for (const evidence of variable.verified) {
  const expected = provenance.independentApertureChecks.find(p =>
    p.point.x === evidence.point.x && p.point.y === evidence.point.y);
  assert.ok(expected);
  [evidence.firstFlux, evidence.secondFlux, evidence.thirdFlux].forEach((flux, i) =>
    assert.ok(Math.abs(flux - expected.scienceFlux[i]) < .02));
}
assert.equal(output.find(r => r.id === 'launch-variable' && r.mode === 'movement').verified.length, 0);
assert.equal(output.find(r => r.id === 'launch-motion' && r.mode === 'fading').verified.length, 0);
// Same real observation repeated gives no fading proposals.
const variableData = LAUNCH_DATA.cases.find(c => c.id === 'launch-variable');
assert.equal(LaunchModel.scan({ ...variableData,
  arrays: [variableData.arrays[0], variableData.arrays[0]],
  sources: [variableData.sources[0], variableData.sources[0]] }, 'fading').candidates.length, 0);
console.log(JSON.stringify({ pass: true, checks: ['archive hashes', 'blind all-source scan',
  'withheld third epoch', 'no identity labels', 'linear prediction verification',
  'independent Python aperture values', 'rebrightening limit', 'zero-candidate modes'], results: output }, null, 2));
