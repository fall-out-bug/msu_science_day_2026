import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { create } = require('./model.js');
const sandbox = {}; vm.runInNewContext(fs.readFileSync(new URL('./data.js', import.meta.url), 'utf8'), sandbox);
const data = sandbox.GALAXY_DATA;
const objects = Object.fromEntries(data.images.map(i => [i.id, i]));
const ids = data.editableIds;
assert.equal(new Set(data.images.map(i => i.id)).size, data.images.length);
assert.equal(Object.keys(data.experiments).length, 243);
assert.ok(!ids.includes(data.tutorialId), 'tutorial must not reveal an editable example');
const classIds = data.classes.map(c => c.id);
const model = create(data);
assert.throws(() => model.dispatch({ type: 'FINISH' }));
model.dispatch({ type: 'START' }); model.dispatch({ type: 'LABELS' });
assert.throws(() => model.dispatch({ type: 'RUN' }));
assert.throws(() => model.dispatch({ type: 'SET_LABEL', id: data.oldIds[0], label: classIds[0] }));
for (const id of data.childIds) model.dispatch({ type: 'SET_LABEL', id, label: objects[id].label });
model.dispatch({ type: 'RUN' });
const initialKey = model.state.key;
const initialReview = model.state.current.review.correct;
assert.throws(() => model.dispatch({ type: 'FINISH' }), /старые метки/);
model.dispatch({ type: 'HOME' }); model.dispatch({ type: 'RESUME' });
assert.equal(model.state.phase, 'results'); assert.equal(model.state.key, initialKey);
model.dispatch({ type: 'REPAIR' }); model.dispatch({ type: 'RUN' });
assert.equal(model.state.current.key, initialKey);
assert.match(model.state.notice, /тот же опыт/);
model.dispatch({ type: 'REPAIR' });
for (const id of data.oldIds) model.dispatch({ type: 'SET_LABEL', id, label: objects[id].label });
assert.equal(model.state.current, null, 'editing must invalidate result');
assert.equal(model.state.baseline.key, initialKey, 'first result stays visible as historical');
assert.throws(() => model.dispatch({ type: 'FINISH' }));
model.dispatch({ type: 'RUN' });
const correctedReview = model.state.current.review.correct;
model.dispatch({ type: 'FINISH' });assert.equal(model.state.finalSeen, true);
model.dispatch({ type: 'LABELS' });
const id = data.childIds[0];
model.dispatch({ type: 'SET_LABEL', id, label: classIds.find(c => c !== objects[id].label) });
assert.equal(model.state.current, null);assert.equal(model.state.finalSeen, true);
model.dispatch({ type: 'RUN' });
assert.throws(() => model.dispatch({ type: 'FINISH' }), /старые метки/);
model.dispatch({ type: 'REPAIR' });model.dispatch({ type: 'RUN' });
model.dispatch({ type: 'FINISH' });assert.match(model.state.notice, /повторный просмотр/);
model.dispatch({ type: 'HOME' });model.dispatch({ type: 'RESUME' });assert.match(model.state.notice, /повторный просмотр/);
model.dispatch({ type: 'RESET' });assert.equal(model.state.baseline, null);assert.equal(model.state.finalSeen, false);
const train = new Set(data.images.filter(i => i.split === 'train').map(i => i.id));
let changes = 0;
for (let n = 0; n < 243; n++) {
  const key = n.toString(3).padStart(5, '0');const result = data.experiments[key];
  assert.equal(result.key, key);
  for (const split of ['review', 'final']) {
    const r = result[split];assert.equal(r.total, r.predictions.length);
    assert.equal(r.correct, r.predictions.filter(p => p.predicted === p.expected).length);
    assert.deepEqual([...r.predictions.map(p => p.id)].sort(), [...data.images.filter(i => i.split === split).map(i => i.id)].sort());
    for (const p of r.predictions) {
      assert.equal(objects[p.id].split, split);assert.equal(p.expected, objects[p.id].label);assert.ok(classIds.includes(p.predicted));
      assert.ok(train.has(p.neighborId), 'neighbor must be a train galaxy');
      const editIndex = ids.indexOf(p.neighborId);
      const expectedPrediction = editIndex < 0 ? objects[p.neighborId].label : classIds[Number(key[editIndex])];
      assert.equal(p.predicted, expectedPrediction, '1-NN prediction must follow current neighbor label');
    }
  }
  if (JSON.stringify(result.review.predictions.map(p => p.predicted)) !== JSON.stringify(data.experiments['00000'].review.predictions.map(p => p.predicted))) changes++;
}
assert.ok(changes > 0, 'labels must causally affect predictions');
console.log(JSON.stringify({ status: 'PASS', experiments: 243, initialReview, correctedReview, checks: ['guarded phases', 'all keys and metrics', 'train-only neighbors', 'causal labels', 'invalidation', 'unchanged branch', 'first and repeated final', 'reset'] }, null, 2));
