/* Campaign-level checks. These assert player-visible scientific promises, not
 * implementation details of the individual instruments. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const box={Date}; box.window=box; vm.createContext(box);
for(const file of ['data.js','model.js','tracking.js','brightness-data.js','brightness-model.js','launch-data.js','launch-model.js','learning-model.js','learning-data.js','training-model.js','archive-data.js','night-model.js']) vm.runInContext(fs.readFileSync(path.join(__dirname,file),'utf8'),box);
const N=box.window.NightModel, checks=[]; const check=(name,fn)=>{fn();checks.push(name)};
const C=id=>N.byId(id), clone=x=>JSON.parse(JSON.stringify(x));
const moving=()=>N.motion('s02',box.window.TrackingModel.select(C('s02').data,58,68));
const faded=()=>N.light('brightness-01',box.window.BrightnessModel.select(C('brightness-01').data,65,64));

check('campaign has a coherent 3/6/9 inventory with nine distinct observations',()=>{
 assert.equal(N.cases.length,9); assert.equal(new Set(N.cases.map(c=>c.id)).size,9);
 for(const size of [3,6,9]) { const s=N.fresh(size); assert.equal(s.length,size); assert.equal(s.caseId,'s02'); assert.deepEqual(clone(s.records),[]); }
 assert.equal(JSON.stringify(N.cases.map(c=>c.id)),JSON.stringify(['s02','brightness-01','s07','launch-variable','archive-steady','s04','archive-brightening','archive-small-change','archive-track']));
});
check('real movement is saved and installs only after a three-epoch confirmation',()=>{
 const session=N.fresh(3), result=moving(); assert.equal(result.outcome,'moving'); assert.equal(result.positions.length,3); assert(N.save(session,result)); assert(session.installed.movement); assert.equal(session.records.length,1);
});
check('stationary or unresolved apparent tracks cannot unlock movement',()=>{
 const session=N.fresh(3), stationary=N.motion('s02',box.window.TrackingModel.select(C('s02').data,71,10));
 assert.equal(stationary.outcome,'stationary'); assert.equal(N.save(session,stationary),false); assert.equal(session.installed.movement,false);
 const unresolved=N.motion('s04',box.window.TrackingModel.select(C('s04').data,63,64)); assert.equal(unresolved.outcome,'unresolved'); assert.equal(N.save(session,unresolved),true); assert.equal(session.installed.movement,false);
});
check('real photometry is gated by a science measurement and stable controls',()=>{
 const session=N.fresh(3), result=faded(); assert.equal(result.outcome,'faded'); assert.equal(result.product,'difference'); assert.deepEqual(clone(result.ratios),[100,34]); assert(N.save(session,result)); assert(session.installed.fading);
 const edge=N.light('brightness-01',box.window.BrightnessModel.select(C('brightness-01').data,1,1)); assert.equal(edge.outcome,'unresolved'); assert.equal(N.save(N.fresh(3),edge),false);
});
check('empty scans say what failed rather than claiming empty sky',()=>{
 const scan=N.scan('archive-steady','fading',N.fresh(6)); const result=N.empty('archive-steady','fading',scan);
 assert.equal(result.outcome,'unresolved'); assert.equal(result.inspectedCount,scan.inspectedCount); assert.match(result.detail,/не значит, что на небе ничего не происходит|отказался от вывода/);
});
check('one saved record per field: replacement does not duplicate the shift log',()=>{
 const session=N.fresh(6), first=moving(); assert(N.save(session,first)); const changed={...first,summary:'повторная проверка'}; assert(N.save(session,changed)); assert.equal(session.records.length,1); assert.equal(session.records[0].summary,'повторная проверка');
});
check('restore rejects duplicate/unknown records and derives instruments from evidence',()=>{
 const valid=N.fresh(6); N.save(valid,moving()); const restored=N.restore(clone(valid)); assert(restored.installed.movement); assert(!restored.installed.fading);
 const duplicate=clone(valid); duplicate.records.push(clone(duplicate.records[0])); assert.throws(()=>N.restore(duplicate));
 const forged=clone(valid); forged.installed={movement:false,fading:true}; const repaired=N.restore(forged); assert(repaired.installed.movement); assert(!repaired.installed.fading);
});
check('player labels train Gianni proposals and wrong links still fail geometry',()=>{
 const session=N.fresh(9);for(const example of N.examples)N.label(session,example.id,example.expectedLabel);
 N.train(session);const evaluation=N.evaluate(session),proposals=N.learning(session,'s07');
 assert(evaluation.falsePositives>0);assert(proposals.acceptedCount>0);
 const bad=proposals.candidates.filter(candidate=>N.verify('s07','learning',candidate,session).outcome!=='moving').slice(0,2);
 assert.equal(bad.length,2);for(const candidate of bad){const verified=N.verify('s07','learning',candidate,session);assert.equal(verified.outcome,'unresolved');assert.match(verified.detail,/не выдержала проверки|остаётся на месте/);}
});
check('manual brightening does not pretend a fading-only scan discovered it',()=>{
 const field=C('archive-brightening').data; const scan=N.scan('archive-brightening','fading',N.fresh(9));
 const source=field.sources[1].find(p=>p.x>12&&p.x<115&&p.y>12&&p.y<115); assert(source); const result=N.photometry('archive-brightening',{x:source.x,y:source.y});
 assert(['brightened','unresolved'].includes(result.outcome)); if(result.outcome==='brightened') assert.match(result.detail,/пропустил бы этот случай/);
});
check('a wrong tool does not resolve a specifically asked motion or light question',()=>{
 const session=N.fresh(6);
 for(const [id,method] of [['s07','fading'],['launch-variable','movement']]) {
  const result=N.empty(id,method,N.scan(id,method,session));
  assert.equal(N.save(session,result),false);
 }
 assert.equal(session.records.length,0);
});
check('common field brightening is removed before judging a smaller target change',()=>{
 const field=C('archive-steady').data, arrays=field.arrays,sources=field.sources;
 const point={x:60,y:29};
 try {
  field.arrays=[arrays[0],arrays[0].map((v,i)=>v*1.24*(Math.hypot(i%128-point.x,Math.floor(i/128)-point.y)<=4?1.2:1)),arrays[0]];
  field.sources=[sources[0],sources[0].map(p=>({...p,peak:p.peak*1.24})),sources[0]];
  const result=N.photometry(field.id,point);
  assert(result.ratios[1]>135,'raw aperture looks more than 35 percent brighter');
  assert.equal(result.outcome,'unresolved','field-corrected 20 percent change is below diagnostic gate');
 } finally {field.arrays=arrays;field.sources=sources;}
});
check('later investigations require evidence for their stated question',()=>{
 const s=N.fresh(9);
 const background=N.motion('s04',box.window.TrackingModel.select(C('s04').data,111,91));
 assert.equal(background.outcome,'stationary');assert.equal(N.save(s,background),false);
 const single=N.motion('s04',box.window.TrackingModel.select(C('s04').data,63,64));
 const old=N.fresh(6);old.records=[moving(),faded(),background];old.finished=true;old.caseId='s04';
 const restored=N.restore(clone(old));assert.equal(restored.records.length,3);assert.equal(restored.finished,false);
 assert.equal(single.reason,'several_possible_origins');assert.equal(N.save(s,single),true);
 const ordinary=N.photometry('archive-brightening',{x:105,y:74});
 assert.equal(ordinary.outcome,'unresolved');assert.equal(N.save(s,ordinary),false);
 const bright=N.photometry('archive-brightening',{x:64,y:63});
 assert.equal(bright.outcome,'brightened');assert.equal(N.save(s,bright),true);
 const small=N.photometry('archive-small-change',{x:63,y:63});
 assert.equal(small.outcome,'unresolved');assert.deepEqual(clone(small.ratios),[100,82,101]);assert.equal(N.save(s,small),true);
 const edge=N.photometry('archive-small-change',{x:1,y:1});assert.equal(N.save(s,edge),false);
 for(const method of ['fading','movement']){
  const result=N.empty('archive-track',method,N.scan('archive-track',method,s));
  assert.equal(N.save(s,result),method==='movement');
 }
});
console.log(JSON.stringify({count:checks.length,checks},null,2));
