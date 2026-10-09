import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const sandbox={}; sandbox.globalThis=sandbox;
for(const file of ['data.js','cnn-architectures.js','cnn-experiments.js','cnn-session.js']) {
  vm.runInNewContext(fs.readFileSync(new URL(file,import.meta.url),'utf8'),sandbox);
}
sandbox.GalaxyCNNResults={register(id,payload){
  for(const [key,row] of Object.entries(payload.experiments)) sandbox.GALAXY_CNN_EXPERIMENTS.experiments[key].architectures[id]=row;
}};
vm.runInNewContext(fs.readFileSync(new URL('cnn-results/d2-r.js',import.meta.url),'utf8'),sandbox);
const {GALAXY_DATA:data,GALAXY_CNN_EXPERIMENTS:table,GalaxyCNNLesson:api}=sandbox;
const canonical=id=>data.images.find(image=>image.id===id).label;
const lesson=api.create(data,table), act=(type,extra={})=>lesson.dispatch({type,...extra});
let checks=0;
function roundtrip(phase, guide) {
  const saved=structuredClone(lesson.serialize());
  assert.ok(!JSON.stringify(saved).includes('predictions'),'storage contains references, never answers');
  const restored=api.create(data,table); restored.restore(saved);
  assert.equal(restored.state.phase,'intro'); restored.dispatch({type:'RESUME'});
  assert.equal(restored.state.phase,phase); assert.equal(restored.state.cnnGuide,guide);
  assert.deepEqual(restored.state.labels,lesson.state.labels);
  assert.equal(restored.state.current?.result,lesson.state.current?.result);
  checks++;
}

act('START'); act('LABELS');
for(const id of data.childIds) act('SET_LABEL',{id,label:canonical(id)});
act('RUN'); act('REPAIR');
for(const id of data.oldIds) act('SET_LABEL',{id,label:canonical(id)});
act('RUN'); roundtrip('review','bridge');
act('GUIDE_OPEN'); roundtrip('review','intro');
act('GUIDE_ADD_CONVOLUTION'); roundtrip('review','compare');
act('RUN'); roundtrip('review','observe');
act('GUIDE_CONFIRM_COMPARE'); roundtrip('review','independent');
act('SET_ARCHITECTURE',{architecture:'d1-r'}); roundtrip('review','independent');
const independentDraft=structuredClone(lesson.serialize());
act('SET_ARCHITECTURE',{architecture:'d2-r'}); roundtrip('review','independent');
act('SET_ARCHITECTURE',{architecture:'d1-r'});
act('RUN'); roundtrip('review','independent-observe');
act('INDEPENDENT_CONFIRM'); roundtrip('review','complete');
act('FINISH'); roundtrip('final','complete');
const completedFinal=structuredClone(lesson.serialize());
act('HOME'); roundtrip('final','complete');

// Rechecking data after the own experience invalidates answers, but it does
// not make the learner repeat the two completed architecture experiments.
act('RESUME'); act('LABELS');
const changedChild=data.childIds[0], changedTo=data.classes.find(item=>item.id!==canonical(changedChild)).id;
act('SET_LABEL',{id:changedChild,label:changedTo}); act('RUN'); act('REPAIR');
for(const id of data.oldIds) act('SET_LABEL',{id,label:canonical(id)});
act('RUN'); roundtrip('review','complete');

// Invalid references and stage contracts must never restore a different experiment.
const valid=structuredClone(lesson.serialize());
for(const mutate of [
  saved=>saved.protocolVersion='old',
  saved=>saved.state.labels[data.childIds[0]]='unknown',
  saved=>saved.state.current.labelKey='2222222',
  saved=>saved.state.phase='missing'
]) { const saved=structuredClone(valid); mutate(saved); assert.throws(()=>api.create(data,table).restore(saved)); checks++; }

for(const mutate of [
  saved=>saved.state.independentBaseline=null,
  saved=>saved.state.current={labelKey:saved.state.independentBaseline.labelKey,architecture:'d2-r'},
  saved=>saved.state.current={labelKey:saved.state.independentBaseline.labelKey,architecture:'d1-r'},
  saved=>saved.state.cnnGuide='independent-observe'
]) { const saved=structuredClone(independentDraft); mutate(saved); assert.throws(()=>api.create(data,table).restore(saved)); checks++; }

// Partial work is stored as inputs and survives; a repair approval cannot be
// forged without confirming every old label.
const partial=api.create(data,table), partialAct=(type,extra={})=>partial.dispatch({type,...extra});
partialAct('START'); partialAct('LABELS'); partialAct('SET_LABEL',{id:data.childIds[0],label:canonical(data.childIds[0])});
let partialSaved=structuredClone(partial.serialize()), partialRestored=api.create(data,table);
partialRestored.restore(partialSaved); partialRestored.dispatch({type:'RESUME'});
assert.equal(partialRestored.state.phase,'labels'); assert.equal(partialRestored.state.labels[data.childIds[0]],canonical(data.childIds[0])); checks++;
for(const id of data.childIds.slice(1)) partialAct('SET_LABEL',{id,label:canonical(id)});
partialAct('RUN'); partialAct('REPAIR'); partialAct('SET_LABEL',{id:data.oldIds[0],label:canonical(data.oldIds[0])});
partialSaved=structuredClone(partial.serialize()); partialRestored=api.create(data,table);
partialRestored.restore(partialSaved); partialRestored.dispatch({type:'RESUME'});
assert.equal(partialRestored.state.phase,'repair'); assert.deepEqual(Array.from(partialRestored.state.reviewedOldIds),[data.oldIds[0]]); checks++;
const forged=structuredClone(partialSaved); forged.state.repairCheckedLabelKey=forged.state.labels && forged.state.current?.labelKey || '0000000';
assert.throws(()=>api.create(data,table).restore(forged)); checks++;

// An old free-editor save remains a review, but it must perform a new own
// comparison; a truly completed final is never demoted.
const oldEditor=structuredClone(valid);
Object.assign(oldEditor.state,{phase:'review',resumePhase:'review',finalSeen:false,cnnGuide:'complete'});
delete oldEditor.state.independentBaseline;
let restored=api.create(data,table); restored.restore(oldEditor); restored.dispatch({type:'RESUME'});
assert.equal(restored.state.cnnGuide,'independent'); assert.ok(restored.state.current); checks++;
const oldDraft=structuredClone(valid);
Object.assign(oldDraft.state,{phase:'review',resumePhase:'review',finalSeen:false,cnnGuide:'complete',current:null,architecture:'d1-r',modelSettings:false});
delete oldDraft.state.independentBaseline;
restored=api.create(data,table); restored.restore(oldDraft); restored.dispatch({type:'RESUME'});
assert.equal(restored.state.cnnGuide,'bridge'); assert.equal(restored.state.current.architecture,'d1-r'); checks++;
const oldLabels=structuredClone(valid);
Object.assign(oldLabels.state,{phase:'labels',resumePhase:'labels',finalSeen:false,cnnGuide:'complete',current:null,architecture:'d1-r',modelSettings:false});
delete oldLabels.state.independentBaseline;
restored=api.create(data,table); restored.restore(oldLabels); restored.dispatch({type:'RESUME'});
assert.equal(restored.state.phase,'labels'); assert.equal(restored.state.cnnGuide,'bridge'); checks++;
const oldFinal=structuredClone(completedFinal); delete oldFinal.state.cnnGuide; delete oldFinal.state.independentBaseline;
restored=api.create(data,table); restored.restore(oldFinal); restored.dispatch({type:'RESUME'});
assert.equal(restored.state.phase,'final'); assert.equal(restored.state.cnnGuide,'complete'); checks++;

const damaged=structuredClone(table), key=lesson.state.current.labelKey;
damaged.experiments[key].architectures['d1-r'].review.correct=99;
assert.throws(()=>api.create(data,damaged).restore(valid),/повреждён/); checks++;
const missing=structuredClone(table); delete missing.experiments[key].architectures['d1-r'];
assert.throws(()=>api.create(data,missing).restore(valid),/нет подготовленного/); checks++;
console.log(JSON.stringify({status:'PASS',checks,coverage:['partial labels','partial repair','bridge','guided comparison','independent draft and comparison','final reload','legacy editor','legacy final','invalid references','damaged and missing result']}));
