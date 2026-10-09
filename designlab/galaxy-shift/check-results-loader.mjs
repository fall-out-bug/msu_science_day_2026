import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const read=file=>fs.readFileSync(new URL(file,import.meta.url),'utf8');
function setup(){
 const scripts=[],timers=new Map();let serial=0;
 const box={Map,Promise,Error,setTimeout(fn){timers.set(++serial,fn);return serial;},clearTimeout(id){timers.delete(id);},document:{createElement(){return {remove(){this.removed=true}}},head:{append(script){scripts.push(script)}}}};
 vm.runInNewContext(read('cnn-architectures.js'),box);
 // Small synthetic tables exercise admission/transport only, never lesson results.
 box.GALAXY_CNN_EXPERIMENTS={source:{protocolSha256:'p',cnnPrepareSha256:'c',generatorSha256:'g'},protocol:{protocolVersion:'test',datasetVersion:'test',classes:['a','b'],editableIds:['x'],trainingIds:['x'],reviewIds:['y'],finalIds:['z']},experiments:{0:{architectures:{'d1-r':{key:'0',architectureId:'d1-r',blocks:1}}},1:{architectures:{'d1-r':{key:'1',architectureId:'d1-r',blocks:1}}}}};
 vm.runInNewContext(read('cnn-results-loader.js'),box);
 const payload=id=>({architectureId:id,source:{...box.GALAXY_CNN_EXPERIMENTS.source},protocol:{...box.GALAXY_CNN_EXPERIMENTS.protocol},experiments:{0:{key:'0',architectureId:id,blocks:1},1:{key:'1',architectureId:id,blocks:1}}});
 return {box,api:box.GalaxyCNNResults,scripts,timers,payload};
}
let checks=0;
const e=setup();await e.api.ensure('d1-r');assert.equal(e.scripts.length,0);checks++;
const first=e.api.ensure('d1-r-bn'),again=e.api.ensure('d1-r-bn');assert.equal(first,again);assert.equal(e.scripts.length,1);
e.api.register('d1-r-bn',e.payload('d1-r-bn'));e.scripts[0].onload();await first;assert.equal(e.box.GALAXY_CNN_EXPERIMENTS.experiments['1'].architectures['d1-r-bn'].key,'1');checks++;
await assert.rejects(()=>e.api.ensure('d3-r'));assert.equal(e.scripts.length,1);checks++;
for(const kind of ['network','empty','timeout']){
 const x=setup(), p=x.api.ensure('d1-r-d');const rejected=assert.rejects(p);
 if(kind==='network')x.scripts[0].onerror();else if(kind==='empty')x.scripts[0].onload();else [...x.timers.values()][0]();await rejected;
 assert.equal(x.scripts[0].removed,true);
 const retry=x.api.ensure('d1-r-d');assert.equal(x.scripts.length,2);x.api.register('d1-r-d',x.payload('d1-r-d'));x.scripts[1].onload();await retry;checks++;
}
for(const mutate of [p=>p.source.cnnPrepareSha256='stale',p=>delete p.source,p=>p.protocol.protocolVersion='stale',p=>delete p.experiments['1'],p=>p.experiments['1'].key='wrong',p=>p.experiments['1'].blocks=2,p=>p.experiments['1'].architectureId='d2-r']){
 const x=setup(),p=x.payload('d1-bn-r');mutate(p);assert.throws(()=>x.api.register('d1-bn-r',p));assert.equal(x.box.GALAXY_CNN_EXPERIMENTS.experiments['0'].architectures['d1-bn-r'],undefined);checks++;
}
console.log(JSON.stringify({status:'PASS',checks,coverage:['inline baseline','shared request','unknown configuration','network retry','empty file retry','timeout retry','atomic admission','stale protocol','incomplete table','invalid row']}));
