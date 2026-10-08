#!/usr/bin/env node
/* State-contract regression for the offline CNN lesson table. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const sandbox = { console };
sandbox.globalThis = sandbox;
for (const file of ['data.js', 'cnn-experiments.js', 'cnn-session.js']) {
  vm.runInNewContext(fs.readFileSync(new URL(file, import.meta.url), 'utf8'), sandbox, { filename: file });
}
const { GALAXY_DATA: data, GALAXY_CNN_EXPERIMENTS: table, GalaxyCNNLesson } = sandbox;
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
mustThrow('SET_ARCHITECTURE', { architecture: '2' });
action('START'); action('LABELS');
mustThrow('SET_LABEL', { id: data.tutorialId, label: 'smooth' });
mustThrow('SET_LABEL', { id: data.childIds[0], label: 'not-a-class' });
labelAll(data.childIds);
action('RUN');
const canonicalKey = signature();
assert.equal(lesson.state.current.labelKey, canonicalKey);
assert.equal(lesson.state.current.result, table.experiments[canonicalKey].architectures['1']);
mustThrow('FINISH');
action('RUN');
assert.equal(lesson.state.notice, 'Метки и устройство те же: показан тот же подготовленный опыт.', 'unchanged run must not claim labels changed');
mustThrow('SET_ARCHITECTURE', { architecture: '2' });
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
assert.equal(lesson.state.current.result, table.experiments[repairedKey].architectures['1']);
action('REPAIR');
assert.deepEqual(Array.from(lesson.state.reviewedOldIds), Array.from(data.oldIds), 'returning to old labels must keep explicit confirmations');
action('RUN');

const beforeSameArchitecture = lesson.state.current;
action('SET_ARCHITECTURE', { architecture: '1' });
assert.equal(lesson.state.current, beforeSameArchitecture, 'same architecture must not invalidate a checked run');
action('MODEL_SETTINGS');
assert.equal(lesson.state.current, beforeSameArchitecture, 'opening settings must retain the displayed result');
assert.equal(lesson.state.modelSettings, true);
assert.equal(lesson.state.repairCheckedLabelKey, repairedKey);
action('LABELS');
assert.equal(lesson.state.modelSettings, false, 'returning to labels must close settings');
assert.equal(lesson.state.current, beforeSameArchitecture, 'labels route must keep its comparison snapshot');
action('RUN'); action('REPAIR');
assert.equal(lesson.state.modelSettings, false, 'opening repair must close settings');
for (const id of data.oldIds) label(id, lesson.state.labels[id]);
action('RUN');
action('SET_ARCHITECTURE', { architecture: '2' });
assert.equal(lesson.state.current, null, 'a changed architecture needs its own exact run');
assert.equal(lesson.state.repairCheckedLabelKey, repairedKey, 'architecture switch must preserve repaired label approval');
mustThrow('FINISH');
action('RUN');
assert.equal(lesson.state.current.result, table.experiments[repairedKey].architectures['2']);
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
action('RUN'); assert.equal(lesson.state.current.result, table.experiments[wrongKey].architectures['2']);
mustThrow('FINISH');
action('REPAIR'); for (const id of data.oldIds) label(id, lesson.state.labels[id]); action('RUN'); action('FINISH');
assert.equal(lesson.state.current.result, table.experiments[wrongKey].architectures['2'], 'wrong child label resolves an exact table row');

const malformed = structuredClone(table);
delete malformed.experiments[wrongKey].architectures['2'];
const missing = GalaxyCNNLesson.create(data, malformed);
const run = (type, extra = {}) => missing.dispatch({ type, ...extra });
run('START'); run('LABELS');
for (const id of data.childIds) run('SET_LABEL', { id, label: id === changedChild ? wrongLabel : canonical(id) });
run('RUN'); run('REPAIR');
for (const id of data.oldIds) run('SET_LABEL', { id, label: canonical(id) });
run('RUN');
run('SET_ARCHITECTURE', { architecture: '2' });
assert.throws(() => run('RUN'), /нет подготовленного опыта/, 'missing table row must never fall back');
console.log(JSON.stringify({ status: 'PASS', checks: ['fresh child labels', 'exact lookup', 'label invalidation', 'architecture state', 'wrong child state', 'no fallback'] }));
