#!/usr/bin/env node
/* State-contract regression for the offline CNN lesson table. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const sandbox = { console };
sandbox.globalThis = sandbox;
for (const file of ['data.js', 'cnn-architectures.js', 'cnn-experiments.js', 'cnn-session.js']) {
  vm.runInNewContext(fs.readFileSync(new URL(file, import.meta.url), 'utf8'), sandbox, { filename: file });
}
const { GALAXY_DATA: data, GALAXY_CNN_EXPERIMENTS: table, GalaxyCNNLesson } = sandbox;
const baselineOnly = process.argv.includes('--baseline');
const secondary = baselineOnly ? 'd1-r' : 'd2-r';
if (!baselineOnly) {
  sandbox.GalaxyCNNResults = {register(id,payload) {
    for (const [key,row] of Object.entries(payload.experiments)) table.experiments[key].architectures[id]=row;
  }};
  vm.runInNewContext(fs.readFileSync(new URL('cnn-results/d2-r.js',import.meta.url),'utf8'),sandbox);
}
const lesson = GalaxyCNNLesson.create(data, table);
const action = (type, extra = {}) => lesson.dispatch({ type, ...extra });
const mustThrow = (type, extra = {}) => assert.throws(() => action(type, extra));
const label = (id, value) => action('SET_LABEL', { id, label: value });
const signature = () => data.editableIds.map(id => table.protocol.classes.indexOf(lesson.state.labels[id])).join('');
const imageById = Object.fromEntries(data.images.map(image => [image.id, image]));
const canonical = id => imageById[id].label;
const labelAll = ids => ids.forEach(id => label(id, canonical(id)));

assert.deepEqual(Object.fromEntries(data.childIds.map(id => [id, lesson.state.labels[id]])),
  Object.fromEntries(data.childIds.map(id => [id, null])), 'fresh lesson must not pre-fill child labels from the table');
mustThrow('RUN');
mustThrow('SET_ARCHITECTURE', { architecture: secondary });
action('START'); action('LABELS');
mustThrow('SET_LABEL', { id: data.tutorialId, label: 'smooth' });
mustThrow('SET_LABEL', { id: data.childIds[0], label: 'not-a-class' });
labelAll(data.childIds);
action('RUN');
const canonicalKey = signature();
assert.equal(lesson.state.current.labelKey, canonicalKey);
assert.equal(lesson.state.current.result, table.experiments[canonicalKey].architectures['d1-r']);
mustThrow('FINISH'); mustThrow('GUIDE_OPEN'); mustThrow('GUIDE_NEXT'); mustThrow('GUIDE_ADD_CONVOLUTION');
action('RUN');
assert.equal(lesson.state.notice, 'Метки и архитектура те же: показан тот же подготовленный опыт.', 'unchanged run must not claim labels changed');
mustThrow('SET_ARCHITECTURE', { architecture: secondary });
mustThrow('MODEL_SETTINGS');
action('REPAIR');
assert.deepEqual(Array.from(lesson.state.reviewedOldIds), [], 'old labels must not appear as learner choices before confirmation');
assert.equal(lesson.state.nextAction, 'confirm_old_labels');
mustThrow('RUN');
const firstOldId = data.oldIds[0];
label(firstOldId, lesson.state.labels[firstOldId]);
assert.deepEqual(Array.from(lesson.state.reviewedOldIds), [firstOldId], 'confirming an unchanged old label must still be tracked');
labelAll(data.oldIds);
assert.equal(lesson.state.repairReady, true);
assert.equal(lesson.state.nextAction, 'run_repair');
action('RUN');
const repairedKey = signature();
assert.equal(lesson.state.repairCheckedLabelKey, repairedKey);
assert.equal(lesson.state.current.result, table.experiments[repairedKey].architectures['d1-r']);
action('REPAIR');
assert.deepEqual(Array.from(lesson.state.reviewedOldIds), Array.from(data.oldIds), 'returning to old labels must keep explicit confirmations');
action('RUN');
assert.equal(lesson.state.cnnGuide, 'bridge');
mustThrow('FINISH'); mustThrow('MODEL_SETTINGS');
mustThrow('GUIDE_ADD_CONVOLUTION');
action('GUIDE_OPEN'); assert.equal(lesson.state.cnnGuide, 'intro');
action('GUIDE_ADD_CONVOLUTION');
assert.equal(lesson.state.architecture, 'd2-r'); assert.equal(lesson.state.current, null);
if (baselineOnly) {
  assert.throws(() => action('RUN'), /нет подготовленного опыта/, 'baseline-only must expose a missing d2-r row, never fall back');
  console.log(JSON.stringify({ status: 'PASS', scope: 'baseline-only', checks: ['fresh child labels', 'exact lookup', 'label invalidation', 'mandatory direct guide', 'no fallback'] }));
  process.exit(0);
}
action('RUN'); assert.equal(lesson.state.cnnGuide, 'observe');
mustThrow('FINISH'); action('GUIDE_CONFIRM_COMPARE'); assert.equal(lesson.state.cnnGuide, 'independent');
mustThrow('RUN'); mustThrow('FINISH');

action('SET_ARCHITECTURE', { architecture: 'd1-r' });
assert.equal(lesson.state.current, null, 'free editor architecture change must require an exact run');
action('RUN');
const beforeSameArchitecture = lesson.state.current;
assert.equal(lesson.state.cnnGuide, 'independent-observe');
mustThrow('FINISH'); mustThrow('SET_ARCHITECTURE', { architecture: secondary });
action('INDEPENDENT_CONFIRM'); assert.equal(lesson.state.cnnGuide, 'complete');
assert.equal(lesson.state.current, beforeSameArchitecture, 'own comparison retains its exact run');
action('MODEL_SETTINGS'); assert.equal(lesson.state.modelSettings, true);
assert.equal(lesson.state.repairCheckedLabelKey, repairedKey);
action('SET_ARCHITECTURE', { architecture: secondary });
assert.equal(lesson.state.current, null, 'a free architecture change needs its own exact run');
action('RUN');
assert.equal(lesson.state.current.result, table.experiments[repairedKey].architectures[secondary]);
action('FINISH'); assert.equal(lesson.state.phase, 'final');
const finalCurrent = lesson.state.current;
action('HOME'); assert.equal(lesson.state.phase, 'intro');
action('RESUME'); assert.equal(lesson.state.phase, 'final');
assert.equal(lesson.state.current, finalCurrent, 'home/resume must preserve the completed exact run');

action('LABELS');
const changedChild = data.childIds[0];
const wrongLabel = table.protocol.classes.find(labelId => labelId !== canonical(changedChild));
label(changedChild, wrongLabel);
const wrongKey = signature();
assert.equal(lesson.state.current, null);
assert.equal(lesson.state.repairCheckedLabelKey, null, 'any label edit must invalidate repair approval');
assert.equal(lesson.state.cnnGuide, 'complete', 'a completed own comparison remains part of the lesson after label edits');
action('RUN'); assert.equal(lesson.state.current.result, table.experiments[wrongKey].architectures[secondary]);
mustThrow('FINISH');
action('REPAIR'); for (const id of data.oldIds) label(id, lesson.state.labels[id]); action('RUN');
assert.equal(lesson.state.cnnGuide, 'complete', 'rechecking labels does not demand a second guided and own experiment');
action('FINISH');
assert.equal(lesson.state.current.result, table.experiments[wrongKey].architectures[secondary], 'wrong child label resolves an exact table row');

if (!baselineOnly) {
const malformed = structuredClone(table);
delete malformed.experiments[wrongKey].architectures[secondary];
const missing = GalaxyCNNLesson.create(data, malformed);
const run = (type, extra = {}) => missing.dispatch({ type, ...extra });
run('START'); run('LABELS');
for (const id of data.childIds) run('SET_LABEL', { id, label: id === changedChild ? wrongLabel : canonical(id) });
run('RUN'); run('REPAIR');
for (const id of data.oldIds) run('SET_LABEL', { id, label: canonical(id) });
run('RUN');
run('GUIDE_OPEN'); run('GUIDE_ADD_CONVOLUTION');
assert.throws(() => run('RUN'), /нет подготовленного опыта/, 'missing table row must never fall back');
}
console.log(JSON.stringify({ status: 'PASS', scope: baselineOnly ? 'baseline-only' : 'two-architectures', checks: ['fresh child labels', 'bridge before network', 'guided and independent comparison', 'exact lookup', 'label invalidation', 'no fallback'] }));
