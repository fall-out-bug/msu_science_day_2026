import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source=fs.readFileSync(new URL('../../designlab/galaxy-shift/telemetry.js',import.meta.url),'utf8');
const meta={gameVersion:'2026.10.08-complete.1',protocolVersion:'2026-10-08-cnn-constructor-v1'};
function environment({protocol='https:',raw=null,blocked=false,status=202}={}){
 let serial=0, time=0, stored=raw;
 const timers=new Map(),requests=[],listeners={};
 const box={Blob,AbortController,Uint8Array,Math,Map,Set,location:{protocol},
  sessionStorage:{getItem(){if(blocked)throw Error('blocked');return stored;},setItem(k,v){if(blocked)throw Error('blocked');stored=v;}},
  setTimeout(fn,delay=0){timers.set(++serial,{fn,at:time+delay});return serial;},clearTimeout(id){timers.delete(id);},
  addEventListener(name,fn){listeners[name]=fn;},fetch:async(url,options)=>{requests.push({url,...options});if(status==='timeout') return new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Error('abort'))));return {ok:status>=200&&status<300,status};}
 };
 vm.runInNewContext(source,box);
 return {api:box.GalaxyTelemetry,box,requests,listeners,timers,stored:()=>stored,
  async advance(delta){const end=time+delta;while(true){const next=[...timers.entries()].filter(([,x])=>x.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;time=next[1].at;timers.delete(next[0]);next[1].fn();for(let i=0;i<8;i++)await Promise.resolve();}time=end;}
 };
}
let checks=0;
const zip=environment({protocol:'file:'});zip.api.start(meta);
for(let i=0;i<2005;i++)zip.api.record('phase_entered',{phase:'labels'});
let journal=JSON.parse(zip.api.export());assert.equal(journal.sessions[0].events.length,2000);assert.equal(journal.dropped,6);assert.equal(journal.sessions[0].incomplete,true);assert.equal(zip.api.diagnostics().queued,0);await zip.advance(200000);assert.equal(zip.requests.length,0);checks++;
assert.ok(new Blob([zip.stored()]).size<=1048576);assert.equal(new Set(journal.sessions[0].events.map(x=>x.eventId)).size,2000);checks++;
const restore=environment({protocol:'file:',raw:zip.stored()});const id=restore.api.restore(meta);assert.equal(id,zip.api.sessionId);assert.equal(JSON.parse(restore.api.export()).sessions[0].events.length,2000);checks++;
for(const raw of ['bad JSON',JSON.stringify({sessions:[{}],queue:[],dropped:0}),JSON.stringify({schema:2,sessions:[{sessionId:'bad'}],queue:[],dropped:0})]){const e=environment({raw});e.api.restore(meta);e.api.record('help_opened');assert.equal(e.api.diagnostics().sessions,1);checks++;}
const blocked=environment({protocol:'file:',blocked:true});blocked.api.start(meta);blocked.api.record('help_opened');assert.equal(blocked.api.diagnostics().storage,'memory');assert.equal(JSON.parse(blocked.api.export()).sessions[0].events.length,2);checks++;
const rollover=environment({protocol:'file:'});for(let i=0;i<25;i++)rollover.api.reset(meta);journal=JSON.parse(rollover.api.export());assert.equal(journal.sessions.length,20);assert.equal(journal.dropped,5);assert.equal(new Set(journal.sessions.map(x=>x.sessionId)).size,20);checks++;
const web=environment();web.api.start(meta);for(let i=0;i<35;i++)web.api.record('help_opened');await web.advance(0);assert.equal(web.api.diagnostics().queued,0);assert.equal(web.requests.length,2);assert.ok(web.requests.every(x=>new Blob([x.body]).size<=16384));const sent=web.requests.flatMap(x=>JSON.parse(x.body).events);assert.equal(sent.length,36);assert.equal(new Set(sent.map(x=>x.eventId)).size,36);checks++;
for(const status of [400,429,500,'timeout']){
 const e=environment({status});e.api.start(meta);e.api.record('help_opened');await e.advance(status==='timeout'?6000:0);
 assert.equal(e.api.diagnostics().queued,status===400?0:2);assert.equal(e.api.diagnostics().dropped,status===400?2:0);
 if(status===400)assert.equal(JSON.parse(e.api.export()).sessions[0].incomplete,true);
 if(status==='timeout')assert.equal(e.requests[0].signal.aborted,true);
 checks++;
}
const retry=environment({status:500});retry.api.start(meta);await retry.advance(500000);assert.equal(retry.requests.length,5);assert.equal(retry.timers.size,0);assert.ok(retry.requests.every(x=>x.body===retry.requests[0].body));checks++;
const inflight=environment();let acknowledge;inflight.box.fetch=(url,options)=>{inflight.requests.push(options);return new Promise(resolve=>{acknowledge=resolve});};inflight.api.start(meta);await inflight.advance(0);for(let i=0;i<2005;i++)inflight.api.record('help_opened');acknowledge({ok:true,status:202});for(let i=0;i<8;i++)await Promise.resolve();assert.equal(inflight.api.diagnostics().queued,2000);checks++;
assert.throws(()=>web.api.record('help_opened',{text:'child name'}));assert.throws(()=>web.api.record('known_error',{code:'some_free_text'}));checks++;
console.log(JSON.stringify({status:'PASS',checks,coverage:['unique ids without secure context','ZIP no network','bounded journal','reload','malformed storage','storage refusal','session rollover','batching','4xx losses','429/500 retry','timeout','bounded backoff','inflight prune','reject arbitrary fields']}));
