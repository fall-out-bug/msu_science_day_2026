import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const sandbox={};sandbox.globalThis=sandbox;
for(const file of ['data.js','cnn-architectures.js','cnn-experiments.js','cnn-session.js']) vm.runInNewContext(fs.readFileSync(new URL(file,import.meta.url),'utf8'),sandbox);
sandbox.GalaxyCNNResults={register(id,p){for(const [key,row] of Object.entries(p.experiments)) sandbox.GALAXY_CNN_EXPERIMENTS.experiments[key].architectures[id]=row;}};vm.runInNewContext(fs.readFileSync(new URL('cnn-results/d2-r.js',import.meta.url),'utf8'),sandbox);
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
act('RUN');roundtrip('review');act('GUIDE_ADD_CONVOLUTION');roundtrip('review');act('RUN');roundtrip('review');act('GUIDE_CONFIRM_COMPARE');act('MODEL_SETTINGS');roundtrip('review');
act('SET_ARCHITECTURE',{architecture:'d1-r'});roundtrip('review');assert.equal(lesson.state.current,null);
act('SET_ARCHITECTURE',{architecture:'d1-r'});act('RUN');act('FINISH');roundtrip('final');
act('HOME');roundtrip('final');
// Every resumable guide stage has an explicit architecture/current contract.
const guided=api.create(data,table), guideAct=(type,extra={})=>guided.dispatch({type,...extra});
guideAct('START');guideAct('LABELS');for(const id of data.childIds)guideAct('SET_LABEL',{id,label:canonical(id)});guideAct('RUN');guideAct('REPAIR');for(const id of data.oldIds)guideAct('SET_LABEL',{id,label:canonical(id)});guideAct('RUN');
const invalidGuide=(mutate)=>{const saved=JSON.parse(JSON.stringify(guided.serialize()));mutate(saved.state);assert.throws(()=>api.create(data,table).restore(saved));checks++;};
invalidGuide(state=>state.architecture='d2-r');
invalidGuide(state=>state.current=null);
guideAct('GUIDE_ADD_CONVOLUTION');invalidGuide(state=>state.current={labelKey:state.baseline.labelKey,architecture:'d2-r'});
guideAct('RUN');invalidGuide(state=>state.current=null);
const valid=JSON.parse(JSON.stringify(lesson.serialize()));
// A legacy review before repair has no repair approval. It keeps labels and its
// table-resolved d1-r result, but must make the learner repair before the guide.
const legacyBeforeRepair=structuredClone(valid);
Object.assign(legacyBeforeRepair.state, {phase:'review',resumePhase:'review',finalSeen:false,architecture:'d2-r',current:{labelKey:valid.state.current.labelKey,architecture:'d2-r'},repairCheckedLabelKey:null,reviewedOldIds:[],modelSettings:false});
delete legacyBeforeRepair.state.cnnGuide;
let migrated=api.create(data,table);migrated.restore(legacyBeforeRepair);migrated.dispatch({type:'RESUME'});
assert.equal(migrated.state.cnnGuide,'intro');assert.equal(migrated.state.architecture,'d1-r');assert.equal(migrated.state.current.architecture,'d1-r');assert.equal(migrated.state.repairCheckedLabelKey,null);assert.deepEqual(Array.from(migrated.state.reviewedOldIds),[]);assert.equal(JSON.stringify(migrated.state.labels),JSON.stringify(valid.state.labels));
migrated.dispatch({type:'REPAIR'});for(const id of data.oldIds)migrated.dispatch({type:'SET_LABEL',id,label:canonical(id)});migrated.dispatch({type:'RUN'});migrated.dispatch({type:'GUIDE_ADD_CONVOLUTION'});assert.equal(migrated.state.cnnGuide,'compare');checks++;
// A legacy completed-repair review returns to the guide and cannot unlock a
// free architecture merely because its saved state used d2-r.
const legacyRepairedReview=structuredClone(valid);
Object.assign(legacyRepairedReview.state, {phase:'review',resumePhase:'review',finalSeen:false,architecture:'d2-r',current:{labelKey:valid.state.current.labelKey,architecture:'d2-r'},modelSettings:false});
delete legacyRepairedReview.state.cnnGuide;
const legacyEditor=structuredClone(legacyRepairedReview);legacyEditor.state.modelSettings=true;
// The replaced goal/change screens resume directly at the unified d1-r workbench.
for(const stage of ['goal','change']){
 const legacyStep=structuredClone(valid);
 Object.assign(legacyStep.state,{phase:'review',resumePhase:'review',finalSeen:false,architecture:'d1-r',current:{labelKey:valid.state.current.labelKey,architecture:'d1-r'},modelSettings:false,cnnGuide:stage});
 migrated=api.create(data,table);migrated.restore(legacyStep);migrated.dispatch({type:'RESUME'});
 assert.equal(migrated.state.cnnGuide,'intro');assert.equal(migrated.state.architecture,'d1-r');assert.equal(migrated.state.current.architecture,'d1-r');assert.equal(JSON.stringify(migrated.state.labels),JSON.stringify(valid.state.labels));
 migrated.dispatch({type:'GUIDE_ADD_CONVOLUTION'});assert.equal(migrated.state.cnnGuide,'compare');checks++;
}
migrated=api.create(data,table);migrated.restore(legacyRepairedReview);
assert.equal(migrated.state.cnnGuide,'intro');assert.equal(migrated.state.architecture,'d1-r');assert.equal(migrated.state.current.architecture,'d1-r');assert.equal(migrated.state.baseline.architecture,valid.state.baseline.architecture);checks++;
migrated=api.create(data,table);migrated.restore(legacyEditor);
assert.equal(migrated.state.cnnGuide,'intro');assert.equal(migrated.state.modelSettings,false);assert.equal(migrated.state.current.architecture,'d1-r');checks++;
// A save made from Home after a genuinely completed final remains complete.
const legacyHomeFinal=structuredClone(valid);delete legacyHomeFinal.state.cnnGuide;
migrated=api.create(data,table);migrated.restore(legacyHomeFinal);migrated.dispatch({type:'RESUME'});
assert.equal(migrated.state.phase,'final');assert.equal(migrated.state.cnnGuide,'complete');checks++;
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
