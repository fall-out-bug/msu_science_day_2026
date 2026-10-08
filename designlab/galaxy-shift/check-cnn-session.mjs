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

assert.deepEqual(Object.fromEntries(data.childIds.map(id => [id, lesson.state.labels[id]])),
  Object.fromEntries(data.childIds.map(id => [id, null])), 'fresh lesson must not pre-fill child labels from the table');
mustThrow('RUN');
mustThrow('SET_ARCHITECTURE', { architecture: '2' });
action('START'); action('LABELS');
mustThrow('SET_LABEL', { id: data.tutorialId, label: 'smooth' });
mustThrow('SET_LABEL', { id: data.childIds[0], label: 'not-a-class' });
label('child_m85', 'smooth'); label('child_ic5332', 'spiral'); label('child_ngc5023', 'edge_on');
action('RUN');
assert.equal(lesson.state.current.labelKey, '01210');
assert.equal(lesson.state.current.result, table.experiments['01210'].architectures['1']);
mustThrow('FINISH');
action('RUN');
assert.equal(lesson.state.notice, 'Метки и устройство те же: показан тот же подготовленный опыт.', 'unchanged run must not claim labels changed');
mustThrow('SET_ARCHITECTURE', { architecture: '2' });
mustThrow('MODEL_SETTINGS');
action('REPAIR'); label('old_ngc3610', 'smooth'); label('old_ngc7090', 'edge_on');
action('RUN');
assert.equal(lesson.state.repairCheckedLabelKey, '01202');
assert.equal(lesson.state.current.result, table.experiments['01202'].architectures['1']);

const beforeSameArchitecture = lesson.state.current;
action('SET_ARCHITECTURE', { architecture: '1' });
assert.equal(lesson.state.current, beforeSameArchitecture, 'same architecture must not invalidate a checked run');
action('MODEL_SETTINGS');
assert.equal(lesson.state.current, beforeSameArchitecture, 'opening settings must retain the displayed result');
assert.equal(lesson.state.modelSettings, true);
assert.equal(lesson.state.repairCheckedLabelKey, '01202');
action('LABELS');
assert.equal(lesson.state.modelSettings, false, 'returning to labels must close settings');
assert.equal(lesson.state.current, beforeSameArchitecture, 'labels route must keep its comparison snapshot');
action('RUN'); action('REPAIR');
assert.equal(lesson.state.modelSettings, false, 'opening repair must close settings');
action('RUN');
action('SET_ARCHITECTURE', { architecture: '2' });
assert.equal(lesson.state.current, null, 'a changed architecture needs its own exact run');
assert.equal(lesson.state.repairCheckedLabelKey, '01202', 'architecture switch must preserve repaired label approval');
mustThrow('FINISH');
action('RUN');
assert.equal(lesson.state.current.result, table.experiments['01202'].architectures['2']);
action('FINISH'); assert.equal(lesson.state.phase, 'final');
const finalCurrent = lesson.state.current;
action('HOME'); assert.equal(lesson.state.phase, 'intro');
action('RESUME'); assert.equal(lesson.state.phase, 'final');
assert.equal(lesson.state.current, finalCurrent, 'home/resume must preserve the completed exact run');

action('LABELS'); label('child_m85', 'spiral');
assert.equal(signature(), '11202');
assert.equal(lesson.state.current, null);
assert.equal(lesson.state.repairCheckedLabelKey, null, 'any label edit must invalidate repair approval');
action('RUN'); assert.equal(lesson.state.current.result, table.experiments['11202'].architectures['2']);
mustThrow('FINISH');
action('REPAIR'); action('RUN'); action('FINISH');
assert.equal(lesson.state.current.result, table.experiments['11202'].architectures['2'], 'wrong child label resolves an exact table row');

const malformed = structuredClone(table);
delete malformed.experiments['11202'].architectures['2'];
const missing = GalaxyCNNLesson.create(data, malformed);
const run = (type, extra = {}) => missing.dispatch({ type, ...extra });
run('START'); run('LABELS');
for (const [id, value] of [['child_m85', 'spiral'], ['child_ic5332', 'spiral'], ['child_ngc5023', 'edge_on']]) run('SET_LABEL', { id, label: value });
run('RUN'); run('REPAIR');
run('SET_LABEL', { id: 'old_ngc3610', label: 'smooth' });
run('SET_LABEL', { id: 'old_ngc7090', label: 'edge_on' });
run('RUN');
run('SET_ARCHITECTURE', { architecture: '2' });
assert.throws(() => run('RUN'), /нет подготовленного опыта/, 'missing table row must never fall back');
console.log(JSON.stringify({ status: 'PASS', checks: ['fresh child labels', 'exact lookup', 'label invalidation', 'architecture state', 'wrong child state', 'no fallback'] }));
