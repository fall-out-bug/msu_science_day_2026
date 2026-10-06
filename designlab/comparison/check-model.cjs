/* Behaviour checks: arithmetic, signs, snapshots, real-data causal effects. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const box = { window: {} }; vm.createContext(box);
for (const file of ['data.js', 'model.js']) vm.runInContext(fs.readFileSync(path.join(__dirname, file), 'utf8'), box);
const { ComparisonModel: M, COMPARISON_DATA: DATA } = box.window;
const checks = [];
function check(name, callback) { callback(); checks.push(name); }
const size = 128 * 128;
const fixture = { arrays: [new Array(size).fill(0), new Array(size).fill(0), new Array(size).fill(0)], displayTop: 100, noise: 1 };
const index = (x, y) => y * 128 + x;
fixture.arrays[0][index(30, 30)] = 100;
fixture.arrays[1][index(30, 30)] = 100;
fixture.arrays[1][index(60, 60)] = 100;
fixture.arrays[2] = fixture.arrays[0].slice();
check('equal observations cancel exactly', () => {
  assert(M.residual(fixture, 1, 2).every(x => x === 0));
  assert.equal(M.render(fixture, 1, 2).count, 0);
});
check('unchanged source cancels while new signal remains', () => {
  const r = M.residual(fixture, 1);
  assert.equal(r[index(30, 30)], 0); assert.equal(r[index(60, 60)], 100);
  assert.equal(M.render(fixture, 1).count, 1);
});
check('half subtraction preserves half the shared source', () => {
  assert.equal(M.residual(fixture, .5)[index(30, 30)], 50);
});
check('disappearing signal retains its negative sign', () => {
  fixture.arrays[0][index(90, 90)] = 100;
  assert.equal(M.residual(fixture, 1)[index(90, 90)], -100);
  assert(M.render(fixture, 1).peaks.some(p => p.value < 0));
});
check('snapshot immutable and invalid settings rejected', () => {
  assert(Object.isFrozen(M.buildSnapshot(.5, 2)));
  for (const a of [-1, 2, NaN]) assert.throws(() => M.buildSnapshot(a));
  assert.throws(() => M.buildSnapshot(.5, 0));
});
const results = [];
for (const c of DATA.cases) {
  check(`${c.id}: snapshot reproduces exact output after other settings`, () => {
    const snapshot = M.buildSnapshot(.37, 2), first = M.run(snapshot, c);
    M.render(c, 1, 1); M.render(c, 0, 2);
    const repeated = M.run(snapshot, c);
    assert.deepEqual(Array.from(repeated.pixels), Array.from(first.pixels));
    assert.deepEqual(repeated.peaks, first.peaks);
  });
  check(`${c.id}: selected coefficient actually determines every residual pixel`, () => {
    const actual = M.residual(c, .37, 2);
    for (let i = 0; i < size; i++) assert.equal(actual[i], c.arrays[2][i] - .37 * c.arrays[0][i]);
  });
  const before = M.render(c, 0), after = M.render(c, 1), third = M.render(c, 1, 2);
  check(`${c.id}: subtraction and third epoch change the image`, () => {
    assert.notDeepEqual(Array.from(before.pixels), Array.from(after.pixels));
    assert.notDeepEqual(Array.from(after.pixels), Array.from(third.pixels));
  });
  const sum = a => Array.from(a).reduce((s,v) => s + Math.abs(v), 0);
  results.push({ id: c.id, beforePeaks: before.count, differencePeaks: after.count,
    thirdEpochPeaks: third.count, residualToRawAbsoluteSum: sum(M.residual(c,1))/sum(M.residual(c,0)),
    differencePositions: after.peaks });
}
const report = { checks, count: checks.length, fields: results };
fs.mkdirSync(path.join(__dirname,'evidence'), { recursive:true });
fs.writeFileSync(path.join(__dirname,'evidence/model-check.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
