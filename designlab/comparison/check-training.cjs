/* A player's labels are the complete fit set; heldout geometry is used only
 * for evaluation, and saved claims carry the exact training revision. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const box={Date};box.window=box;vm.createContext(box);
for(const file of ['data.js','model.js','tracking.js','brightness-data.js','brightness-model.js','launch-data.js','launch-model.js','learning-model.js','learning-data.js','training-model.js','archive-data.js','night-model.js'])
 vm.runInContext(fs.readFileSync(path.join(__dirname,file),'utf8'),box);
const N=box.NightModel,clone=value=>JSON.parse(JSON.stringify(value)),checks=[];
const check=(name,run)=>{run();checks.push(name)};
const labels=(session,correction='wrongLink')=>{for(const example of N.examples)N.label(session,example.id,example.id==='5:4:5'?correction:example.expectedLabel)};
check('six measured tracks start unlabeled and all six player labels are required',()=>{
 const session=N.fresh(9);
 assert.equal(N.examples.length,6);assert.equal(N.trainingStatus(session).labeledCount,0);
 assert.throws(()=>N.train(session),/Label all six/);
 for(const example of N.examples.slice(0,5))N.label(session,example.id,example.expectedLabel);
 assert.equal(N.trainingStatus(session).trainable,false);assert.throws(()=>N.train(session));
 N.label(session,N.examples[5].id,'sameObject');
 assert.equal(N.trainingStatus(session).trainable,true);
});
check('fit is based on six user-labeled rows, not a hidden full-field fit',()=>{
 const session=N.fresh(9);labels(session);N.train(session);
 const rows=N.examples.map(example=>box.LearningModel.generate(N.byId('s02').data,box.LEARNING_DATA.pixelScaleArcsec.s02).candidates.find(row=>row.id===example.id));
 const expected=box.LearningModel.fit({candidates:rows});
 assert.deepEqual(clone(session.training.snapshot.scale),clone(expected.scale));
 assert.equal(session.training.snapshot.labels.length,6);
 assert.equal(N.trainingStatus(session).evaluated,false);
});
check('wrong human label changes heldout predictions and evaluation without answer-key fit',()=>{
 const wrong=N.fresh(9),correct=N.fresh(9);labels(wrong,'sameObject');labels(correct);
 N.train(wrong);N.train(correct);
 const before=N.predict(wrong),after=N.predict(correct);
 assert.notEqual(before.acceptedCount,after.acceptedCount);
 assert(before.acceptedCount>after.acceptedCount);
 const badEval=N.evaluate(wrong),goodEval=N.evaluate(correct);
 assert(goodEval.correct>badEval.correct);
 assert(goodEval.falsePositives>0,'even the revised small model still makes mistakes');
 assert.equal(goodEval.controls.length,goodEval.total);
 assert(goodEval.controls.every(row=>!N.examples.some(example=>JSON.stringify(example.points)===JSON.stringify(row.points))));
 assert(goodEval.controls.some(row=>row.verifiedLabel==='sameObject'));
 assert(goodEval.controls.some(row=>row.verifiedLabel==='wrongLink'));
});
check('relabeling clears trained and evaluated state and reopens saved s07',()=>{
 const session=N.fresh(9);labels(session);N.train(session);N.evaluate(session);
 const candidate=N.predict(session).candidates.find(row=>row.id==='5:5:5');assert(candidate);
 const result=N.verify('s07','learning',candidate,session);assert.equal(result.outcome,'moving');
 assert(N.save(session,result));session.finished=true;
 const priorRevision=session.training.revision;
 N.label(session,'5:4:5','sameObject');
 assert.equal(session.training.revision,priorRevision+1);
 assert.equal(N.trainingStatus(session).trained,false);
 assert.equal(N.trainingStatus(session).evaluated,false);
 assert.equal(session.records.some(row=>row.caseId==='s07'),false);
 assert.equal(session.finished,false);
 assert.equal(N.save(session,result),false,'old verified result cannot be saved after edit');
 assert.throws(()=>N.predict(session),/Train/);
 const restored=N.restore(clone(session));
 assert.equal(N.trainingStatus(restored).trained,false);
 assert.equal(N.save(restored,result),false);
 N.train(restored);assert.equal(N.trainingStatus(restored).evaluated,false);
 assert.equal(N.save(restored,result),false,'evaluation and revision are both required');
});
check('valid revision survives reload; legacy ML completion is reopened without losing other records',()=>{
 const session=N.fresh(9);labels(session);N.train(session);N.evaluate(session);
 const result=N.verify('s07','learning',N.predict(session).candidates.find(row=>row.id==='5:5:5'),session);
 assert(N.save(session,result));
 const restored=N.restore(clone(session));
 assert(N.trainingStatus(restored).trained&&N.trainingStatus(restored).evaluated);
 assert.equal(restored.records.filter(row=>row.caseId==='s07').length,1);
 const stale=clone(session);stale.training.labels.find(row=>row.id==='5:4:5').label='sameObject';
 const reopened=N.restore(stale);
 assert.equal(N.trainingStatus(reopened).trained,false);
 assert.equal(reopened.records.some(row=>row.caseId==='s07'),false);
 const legacy=N.fresh(9);legacy.records=[{caseId:'s02',method:'movement',outcome:'moving',summary:'Старый результат',detail:'Сохранённое наблюдение'},
  {caseId:'s07',method:'learning',outcome:'moving',summary:'Старый ИИ',detail:'Без версии меток'}];
 legacy.learningLabel='wrongLink';legacy.learningSeen=true;legacy.finished=true;
 const migrated=N.restore(clone(legacy));
 assert.equal(migrated.records.length,1);assert.equal(migrated.records[0].caseId,'s02');
 assert.equal(migrated.finished,false);assert.equal(N.trainingStatus(migrated).labeledCount,0);
});
console.log(JSON.stringify({count:checks.length,checks},null,2));
