import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const sandbox={};sandbox.globalThis=sandbox;
for(const file of ['data.js','cnn-architectures.js','cnn-experiments.js','cnn-session.js']) vm.runInNewContext(fs.readFileSync(new URL(file,import.meta.url),'utf8'),sandbox);
const {GALAXY_DATA:data,GALAXY_CNN_EXPERIMENTS:table,GalaxyCNNLesson:api}=sandbox;
const lesson=api.create(data,table), act=(type,extra={})=>lesson.dispatch({type,...extra});
const canonical=id=>data.images.find(i=>i.id===id).label;
let checks=0;
function roundtrip(phase){
 const saved=JSON.parse(JSON.stringify(lesson.serialize()));
 assert.ok(!JSON.stringify(saved).includes('predictions'),'store inputs, never model answers');
 const restored=api.create(data,table);restored.restore(saved);
 assert.equal(restored.state.phase,'intro');restored.dispatch({type:'RESUME'});assert.equal(restored.state.phase,phase);
 assert.equal(JSON.stringify(restored.state.labels),JSON.stringify(lesson.state.labels));
 assert.equal(restored.state.architecture,lesson.state.architecture);
 assert.equal(restored.state.modelSettings,lesson.state.modelSettings);
 assert.equal(restored.state.current?.result,lesson.state.current?.result);
 checks++;
}
roundtrip('tutorial'); act('START');roundtrip('tutorial');act('LABELS');
act('SET_LABEL',{id:data.childIds[0],label:canonical(data.childIds[0])});roundtrip('labels');
for(const id of data.childIds)act('SET_LABEL',{id,label:canonical(id)});
act('RUN');roundtrip('review');act('REPAIR');
act('SET_LABEL',{id:data.oldIds[0],label:lesson.state.labels[data.oldIds[0]]});roundtrip('repair');
for(const id of data.oldIds)act('SET_LABEL',{id,label:canonical(id)});
act('RUN');act('MODEL_SETTINGS');roundtrip('review');
act('SET_ARCHITECTURE',{architecture:'d2-r-d-bn'});roundtrip('review');assert.equal(lesson.state.current,null);
act('SET_ARCHITECTURE',{architecture:'d1-r'});act('RUN');act('FINISH');roundtrip('final');
act('HOME');roundtrip('final');
const valid=JSON.parse(JSON.stringify(lesson.serialize()));
for(const mutate of [s=>s.protocolVersion='old',s=>s.datasetVersion='old',s=>s.state.labels[data.childIds[0]]='unknown',s=>s.state.architecture='d3-r',s=>s.state.current.labelKey='2222222',s=>s.state.reviewedOldIds=[],s=>s.state.finalSeen=false,s=>s.state.phase='missing',s=>delete s.state.baseline,s=>s.state.labels.extra='smooth']){
 const saved=structuredClone(valid);mutate(saved);assert.throws(()=>api.create(data,table).restore(saved));checks++;
}
act('RESUME');act('LABELS');act('SET_LABEL',{id:data.childIds[0],label:'edge_on'});roundtrip('labels');
const bad=structuredClone(table), key=valid.state.current.labelKey;
bad.experiments[key].architectures['d1-r'].review.correct=99;
assert.throws(()=>api.create(data,bad).restore(valid),/повреждён/);checks++;
const missing=structuredClone(table);delete missing.experiments[key].architectures['d1-r'];
assert.throws(()=>api.create(data,missing).restore(valid),/нет подготовленного/);checks++;
console.log(JSON.stringify({status:'PASS',checks,coverage:['partial labels','partial repair','model draft','final','home','stale version','invalid refs','malformed result','no fallback']}));
