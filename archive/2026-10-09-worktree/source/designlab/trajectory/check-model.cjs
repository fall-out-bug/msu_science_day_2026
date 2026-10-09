const assert = require('assert/strict');
const { Investigation, predict } = require('./model.js');
const fs = require('fs');
const vm = require('vm');
const sandbox = { window: {} }; vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(__dirname + '/labdata.js', 'utf8'), sandbox);
const cases = sandbox.window.TRAJECTORY_DATA;
const p = predict([{ x: 1, y: 3 }, { x: 5, y: 1 }],
  ['2020-01-01T00:00:00Z', '2020-01-01T00:10:00Z', '2020-01-01T00:30:00Z']);
assert.deepEqual(p, { x: 13, y: -3, ratio: 2 });
for (const item of cases) {
  const model = new Investigation(item);
  assert.equal(model.test(), false);
  assert.equal(model.result(), null);
  model.mark(0, 10, 10); model.mark(1, 10, 10); model.test();
  const before = JSON.stringify(model.frozen);
  assert.equal(model.result(true).withinTolerance, false);
  const [a, b] = item.truth.targets;
  model.mark(0, a.x, a.y); model.mark(1, b.x, b.y); model.test();
  assert.equal(JSON.stringify(model.frozen), before);
  assert.equal(model.result().withinTolerance, true);
  const dates = item.observations.map(o => o.date);
  const full = predict([a, b], dates);
  assert(Math.abs(full.ratio - 1) > .5, 'Real epochs have unequal time gaps');
  // Ground truth can change independently without changing the player forecast.
  const other = new Investigation({ ...item, truth: { targets: [{}, {}, { x: 0, y: 0 }] } });
  other.mark(0, a.x, a.y); other.mark(1, b.x, b.y);
  assert.deepEqual(other.prediction, model.prediction);
  assert.throws(() => model.mark(2, 5, 5), RangeError);
  console.log(item.id, 'unequal-time fit; wrong association; recovery; frozen first forecast; truth isolation: PASS');
}
