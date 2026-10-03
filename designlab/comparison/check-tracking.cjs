/* Synthetic failure cases and real measured-peak associations. No runtime truth. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const box = { window: {} }; vm.createContext(box);
for (const file of ['data.js', 'tracking.js']) {
  vm.runInContext(fs.readFileSync(path.join(__dirname, file), 'utf8'), box);
}
const M = box.window.TrackingModel, DATA = box.window.COMPARISON_DATA;
const checks = [], real = [];
function check(name, run) { run(); checks.push(name); }
const p = (x, y, peak = 60) => ({ x, y, peak });
const fixture = () => ({ dates: ['2020-01-01T00:00:00Z', '2020-01-01T01:00:00Z',
  '2020-01-01T03:00:00Z'], sources: [[p(10, 20), p(80, 80)],
    [p(20, 20), p(80, 80)], [p(40, 20), p(80, 80)]] });
const plain = value => JSON.parse(JSON.stringify(value));
check('empty sky and out-of-frame clicks do not invent a target', () => {
  for (const [x, y] of [[50, 50], [-1, 20], [128, 20], [NaN, 20]]) {
    const selection = M.select(fixture(), x, y);
    assert.equal(selection.status, 'empty'); assert.equal(selection.prediction, null);
    assert.equal(M.confirm(fixture(), selection).outcome, 'unresolved');
  }
});
check('a click selects the nearest measured peak within five pixels', () => {
  assert.deepEqual(plain(M.select(fixture(), 23, 22).point), { x: 20, y: 20 });
  assert.equal(M.select(fixture(), 25.01, 20).status, 'empty');
});
check('overlapping click choices require a different click', () => {
  const c = fixture(); c.sources[1].push(p(22, 20));
  assert.equal(M.select(c, 21, 20).status, 'ambiguous');
});
check('unequal epoch spacing determines the held-out prediction', () => {
  const c = fixture(), selection = M.select(c, 20, 20);
  assert.equal(selection.kind, 'moving'); assert.equal(selection.timeRatio, 2);
  assert.deepEqual(plain(selection.prediction), { x: 40, y: 20 });
  assert.equal(M.confirm(c, selection).outcome, 'moving');
  assert(Object.isFrozen(selection)); assert(Object.isFrozen(selection.point));
  assert(Object.isFrozen(selection.origin)); assert(Object.isFrozen(selection.prediction));
});
check('selection cannot read the third image, third detections or truth labels', () => {
  const c = fixture(), expected = plain(M.select(c, 20, 20));
  Object.defineProperty(c.sources, 2, { get() { throw Error('held-out sources accessed'); } });
  for (const name of ['arrays', 'truth', 'knownObject', 'id']) {
    Object.defineProperty(c, name, { get() { throw Error(`${name} accessed`); } });
  }
  assert.deepEqual(plain(M.select(c, 20, 20)), expected);
});
check('third-frame changes alter confirmation without altering selection', () => {
  const c = fixture(), selection = M.select(c, 20, 20), initial = plain(selection);
  assert.equal(M.confirm(c, selection).outcome, 'moving');
  c.sources[2] = [p(80, 80)];
  assert.equal(M.confirm(c, selection).outcome, 'lost');
  assert.deepEqual(plain(M.select(c, 20, 20)), initial);
  assert.deepEqual(plain(selection), initial);
});
check('confirmation uses the submitted prediction without recalculating dates', () => {
  const c = fixture(), selection = M.select(c, 20, 20);
  c.dates[2] = '2020-01-01T09:00:00Z';
  assert.equal(M.confirm(c, selection).outcome, 'moving');
  assert.deepEqual(plain(selection.prediction), { x: 40, y: 20 });
  assert.deepEqual(plain(M.select(c, 20, 20).prediction), { x: 100, y: 20 });
});
check('a changed first-frame measurement changes the prediction and outcome', () => {
  const c = fixture(); c.sources[0][0] = p(12, 20);
  const selection = M.select(c, 20, 20);
  assert.deepEqual(plain(selection.prediction), { x: 36, y: 20 });
  assert.equal(M.confirm(c, selection).outcome, 'lost');
});
check('two compatible disappeared peaks are unresolved', () => {
  const c = fixture(); c.sources[0].push(p(10, 35));
  const selection = M.select(c, 20, 20);
  assert.equal(selection.kind, 'unresolved'); assert.equal(selection.origin, null);
  assert.equal(selection.reason, 'several_possible_origins');
  assert.equal(M.confirm(c, selection).outcome, 'unresolved');
});
check('two new peaks cannot confidently share one origin', () => {
  const c = fixture(); c.sources[1].push(p(20, 35));
  assert.equal(M.select(c, 20, 20).reason, 'several_possible_destinations');
});
check('amplitude gate is fixed and weak vanished peaks can be excluded', () => {
  const c = fixture(); c.sources[0].push(p(10, 35, 10));
  assert.equal(M.select(c, 20, 20).kind, 'moving');
  c.sources[0][2].peak = 20;
  assert.equal(M.select(c, 20, 20).kind, 'unresolved');
  c.sources[0] = [p(10, 20, 10), p(80, 80)];
  assert.equal(M.select(c, 20, 20).reason, 'no_compatible_origin');
});
check('stationary targets never count as moving', () => {
  const c = fixture(), selection = M.select(c, 80, 80), result = M.confirm(c, selection);
  assert.equal(selection.kind, 'stationary'); assert.equal(result.outcome, 'stationary');
  c.sources[2] = [p(40, 20)];
  assert.equal(M.confirm(c, selection).outcome, 'lost');
});
check('centroid jitter and crowded first-epoch matches are unresolved', () => {
  const c = fixture(); c.sources[0][0] = p(17.5, 20);
  assert.equal(M.select(c, 20, 20).reason, 'ambiguous_nearby_origin');
  c.sources[0] = [p(19, 20), p(21, 20), p(80, 80)];
  assert.equal(M.select(c, 20, 20).kind, 'unresolved');
});
check('invalid chronology cannot create a linear prediction', () => {
  for (const dates of [['bad', 'bad', 'bad'], ['2020-01-01', '2020-01-01', '2020-01-02'],
    ['2020-01-02', '2020-01-01', '2020-01-03']]) {
    const c = fixture(); c.dates = dates;
    assert.equal(M.select(c, 20, 20).reason, 'invalid_observation_times');
  }
});
check('confirmation requires a unique third-frame peak within three pixels', () => {
  const c = fixture(), selection = M.select(c, 20, 20);
  c.sources[2] = [p(43, 20)];
  assert.equal(M.confirm(c, selection).outcome, 'moving');
  c.sources[2] = [p(43.01, 20)];
  assert.equal(M.confirm(c, selection).outcome, 'lost');
  c.sources[2] = [p(40, 20), p(41, 20)];
  assert.equal(M.confirm(c, selection).reason, 'several_peaks_at_prediction');
});
check('a coincident existing background peak cannot confirm a mover', () => {
  const c = fixture(); c.sources[0].push(p(40, 20)); c.sources[1].push(p(40, 20));
  const selection = M.select(c, 20, 20);
  assert.equal(selection.kind, 'moving');
  assert.equal(M.confirm(c, selection).reason, 'prediction_matches_existing_source');
});
for (const [id, origin, current, third, stable] of [
  ['s02', [42, 82], [58, 68], [91, 40], [71, 10]],
  ['s07', [36, 72], [59, 65], [95, 53], [38, 7]],
]) {
  const c = DATA.cases.find(c => c.id === id);
  check(`${id}: measured moving target supports prediction in held-out frame`, () => {
    const selection = M.select(c, ...current), result = M.confirm(c, selection);
    assert.equal(selection.kind, 'moving');
    assert.deepEqual(plain(selection.origin), { x: origin[0], y: origin[1] });
    assert.equal(result.outcome, 'moving');
    assert.deepEqual(plain(result.positions[2]), { x: third[0], y: third[1] });
    assert(result.distancePx < 3);
    real.push({ id, selection: plain(selection), confirmation: plain(result) });
  });
  check(`${id}: another chosen peak produces a stationary outcome`, () => {
    assert.equal(M.confirm(c, M.select(c, ...stable)).outcome, 'stationary');
  });
}
check('s04: isolated signal with several origins stays unresolved', () => {
  const c = DATA.cases.find(c => c.id === 's04');
  const selection = M.select(c, 63, 64), result = M.confirm(c, selection);
  assert.equal(selection.kind, 'unresolved'); assert.equal(result.outcome, 'unresolved');
  assert.equal(result.samePositionDetected, false);
  assert.equal(M.confirm(c, M.select(c, 111, 91)).outcome, 'stationary');
  real.push({ id: c.id, selection: plain(selection), confirmation: plain(result) });
});
console.log(JSON.stringify({ count: checks.length, checks, real,
  limits: 'Peak correspondence and linear extrapolation support a candidate motion only; no orbit, identity, artifact class or independent astronomical discovery is inferred.' }, null, 2));
