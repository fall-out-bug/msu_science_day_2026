/* The journal cannot affect lesson state. file:// never sends network requests. */
(function(root) {
  'use strict';
  const KEY = 'science-day.telemetry.v1';
  const MAX_EVENTS = 2000, MAX_BYTES = 1024 * 1024, MAX_SESSIONS = 20;
  const BATCH = 20, BODY = 16 * 1024, DAY = 86400000;
  const TYPES = new Set(['session_started','phase_entered','map_target_collected','label_set','old_label_confirmed','help_opened','explanation_opened','architecture_selected','run_opened','result_opened','final_opened','session_reset','known_error']);
  const PHASES = new Set(['intro','story','collect','tutorial','labels','review','repair','model','final','free']);
  const IMAGES = new Set(['tutorial_ic2006','child_m85','child_ic5332','child_ngc5023','old_ngc3610','old_ngc7090','fixed_ngc3318','fixed_ngc691','fixed_ic755','review_m49','review_ngc3982','review_ngc4762','final_ngc2768','final_ngc6814','final_ngc5775']);
  const LABELS = new Set(['smooth','spiral','edge_on']);
  const CODES = new Set(['network_error','timeout','storage_unavailable','queue_overflow','invalid_response']);
  const version = value => typeof value === 'string' && /^[A-Za-z0-9._-]{1,64}$/.test(value);
  const validId = value => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value);
  const blank = () => ({schema:2,sessions:[],queue:[],dropped:0});
  let state, storage = 'memory', warning = null, timer = null, sending = false, attempts = 0;
  function uuid() {
    if (root.crypto?.randomUUID) return root.crypto.randomUUID();
    const bytes = new Uint8Array(16);
    if (root.crypto?.getRandomValues) root.crypto.getRandomValues(bytes);
    else for (let i=0;i<bytes.length;i++) bytes[i] = Math.floor(Math.random()*256);
    bytes[6] = (bytes[6]&15)|64; bytes[8] = (bytes[8]&63)|128;
    const hex = [...bytes].map(value=>value.toString(16).padStart(2,'0')).join('');
    return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
  }
  function architecture(value) {
    const tokens = typeof value === 'string' ? value.split('-') : [];
    return ['d1','d2'].includes(tokens[0]) && tokens.length>=2 && tokens.length<=4 && tokens.slice(1).includes('r') && new Set(tokens.slice(1)).size===tokens.length-1 && tokens.slice(1).every(token=>['r','bn','d'].includes(token));
  }
  function validDetail(detail) {
    if (!detail || Array.isArray(detail) || typeof detail !== 'object') return false;
    return Object.entries(detail).every(([key,value]) => {
      if (key==='phase') return PHASES.has(value);
      if (key==='imageId') return IMAGES.has(value);
      if (['before','after','label'].includes(key)) return LABELS.has(value);
      if (key==='architecture') return architecture(value);
      if (key==='experimentKey') return typeof value==='string' && /^[0-2]{7}$/.test(value);
      if (key==='scope') return ['review','final','comparison'].includes(value);
      if (['correct','total'].includes(key)) return Number.isInteger(value) && value>=0 && value<=99;
      return key==='code' && CODES.has(value);
    });
  }
  function validEvent(event) {
    return event && Object.keys(event).length===10 && event.schema===1 && validId(event.eventId) && validId(event.sessionId) && Number.isInteger(event.seq) && event.seq>=1 && event.seq<=2000000 && Number.isInteger(event.elapsedMs) && event.elapsedMs>=0 && event.elapsedMs<=DAY && version(event.gameVersion) && version(event.protocolVersion) && ['web','zip'].includes(event.channel) && TYPES.has(event.type) && validDetail(event.detail);
  }
  function validJournal(raw) {
    if (!raw || raw.schema!==2 || !Array.isArray(raw.sessions) || raw.sessions.length>MAX_SESSIONS || !Array.isArray(raw.queue) || !Number.isInteger(raw.dropped) || raw.dropped<0) return false;
    const ids = new Set(), sessions = new Set(); let count = 0;
    for (const session of raw.sessions) {
      if (!session || !validId(session.sessionId) || sessions.has(session.sessionId) || !Number.isInteger(session.seq) || session.seq<0 || session.seq>2000000 || !Number.isFinite(session.startedAt) || !version(session.gameVersion) || !version(session.protocolVersion) || !['web','zip'].includes(session.channel) || typeof session.closed!=='boolean' || !Array.isArray(session.events)) return false;
      sessions.add(session.sessionId); let previous = 0;
      for (const event of session.events) {
        if (!validEvent(event) || ids.has(event.eventId) || event.sessionId!==session.sessionId || event.seq<=previous || event.seq>session.seq || event.gameVersion!==session.gameVersion || event.protocolVersion!==session.protocolVersion || event.channel!==session.channel) return false;
        ids.add(event.eventId); previous=event.seq; count++;
      }
    }
    return count<=MAX_EVENTS && raw.queue.length<=MAX_EVENTS && new Set(raw.queue).size===raw.queue.length && raw.queue.every(id=>validId(id)&&ids.has(id));
  }
  function load() {
    if (state) return state;
    try {
      const raw = sessionStorage.getItem(KEY);
      if (raw && new Blob([raw]).size>MAX_BYTES) throw Error('oversize');
      const parsed = raw ? JSON.parse(raw) : blank();
      if (!validJournal(parsed)) throw Error('invalid');
      state=parsed; storage='sessionStorage';
    } catch (_) {
      state=blank(); warning='Предыдущий журнал недоступен. Текущая смена записывается заново.';
    }
    return state;
  }
  function current() { return load().sessions.at(-1); }
  function save() {
    try { sessionStorage.setItem(KEY,JSON.stringify(load())); storage='sessionStorage'; }
    catch (_) { storage='memory'; warning='Журнал доступен только до перезагрузки вкладки.'; }
  }
  function loss(session,count=1) { if (session) session.incomplete=true; load().dropped+=count; }
  function removeSession() {
    const gone=load().sessions.shift(), ids=new Set(gone.events.map(event=>event.eventId));
    load().queue=load().queue.filter(id=>!ids.has(id)); loss(null,gone.events.length);
  }
  function prune() {
    const journal=load();
    while (journal.sessions.length>MAX_SESSIONS) removeSession();
    let count=journal.sessions.reduce((sum,session)=>sum+session.events.length,0);
    // Serialized storage has ASCII-only event fields; byte count includes metadata.
    while (count>MAX_EVENTS || new Blob([JSON.stringify(journal)]).size>MAX_BYTES) {
      const owner=journal.sessions.find(session=>session.events.length);
      if (!owner) break;
      const gone=owner.events.shift(); journal.queue=journal.queue.filter(id=>id!==gone.eventId); loss(owner); count--;
    }
  }
  function meta(input={}) {
    return {gameVersion:version(input.gameVersion)?input.gameVersion:'unknown',protocolVersion:version(input.protocolVersion)?input.protocolVersion:'unknown',channel:location.protocol==='file:'?'zip':'web'};
  }
  function start(input,restore) {
    const old=current(), next=meta(input);
    if (restore && old && !old.closed && old.gameVersion===next.gameVersion && old.protocolVersion===next.protocolVersion && old.channel===next.channel && Date.now()-old.startedAt<DAY) { schedule(); return old.sessionId; }
    if (old) old.closed=true;
    const session={sessionId:uuid(),seq:0,startedAt:Date.now(),closed:false,...next,events:[]};
    load().sessions.push(session); prune(); record('session_started'); return session.sessionId;
  }
  function record(type,detail={}) {
    if (!TYPES.has(type) || !validDetail(detail)) throw Error('Unsupported telemetry event');
    if (!current()) start();
    const session=current();
    const event={schema:1,eventId:uuid(),sessionId:session.sessionId,seq:++session.seq,elapsedMs:Math.max(0,Math.min(DAY,Date.now()-session.startedAt)),gameVersion:session.gameVersion,protocolVersion:session.protocolVersion,channel:session.channel,type,detail:{...detail}};
    session.events.push(event); if (session.channel==='web') load().queue.push(event.eventId);
    prune(); save(); schedule(); return event;
  }
  function schedule(delay=0) {
    if (location.protocol==='file:' || timer!==null || !load().queue.length) return;
    timer=setTimeout(()=>{timer=null;flush();},delay);
  }
  async function flush() {
    if (sending || location.protocol==='file:' || !load().queue.length) return;
    const byId=new Map(load().sessions.flatMap(session=>session.events).map(event=>[event.eventId,event]));
    const events=load().queue.slice(0,BATCH).map(id=>byId.get(id)).filter(Boolean);
    const ids=new Set(events.map(event=>event.eventId)), body=JSON.stringify({events});
    const acknowledge=lost=>{
      const remaining=new Set(load().queue);
      if(lost) for(const event of events) if(remaining.has(event.eventId)) loss(load().sessions.find(session=>session.sessionId===event.sessionId));
      load().queue=load().queue.filter(id=>!ids.has(id));save();
    };
    if (new Blob([body]).size>BODY) { acknowledge(true);schedule();return; }
    sending=true;
    const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),5000);
    try {
      const response=await fetch('/telemetry/v1/events',{method:'POST',credentials:'omit',headers:{'Content-Type':'application/json'},body,signal:controller.signal});
      if (!response.ok) {
        if (response.status>=400 && response.status<500 && response.status!==429) { acknowledge(true);attempts=0;return; }
        throw Error('network');
      }
      acknowledge(false);attempts=0;
    } catch (_) {
      attempts++;
    } finally {
      clearTimeout(timeout);sending=false;
      if (attempts===0) schedule();
      else if (attempts<=4) schedule([1000,5000,30000,120000][attempts-1]);
    }
  }
  addEventListener('online',()=>{attempts=0;schedule();});
  root.GalaxyTelemetry={
    start:input=>start(input,false),restore:input=>start(input,true),record,
    reset(input){return start(input,false);},
    export(){return JSON.stringify({schema:1,exportedAt:new Date().toISOString(),sessions:load().sessions,dropped:load().dropped},null,2);},
    diagnostics(){return {sessionId:current()?.sessionId||null,queued:load().queue.length,dropped:load().dropped,sessions:load().sessions.length,storage,warning};},
    get sessionId(){return current()?.sessionId||null;}
  };
})(globalThis);
