#!/usr/bin/env python3
"""Private-by-default receipt endpoint for anonymous Science Day event batches."""
import json, os, re, sqlite3, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
DB = os.environ.get('TELEMETRY_DB', '/data/telemetry.sqlite3')
MAX_BODY, RETENTION = 16 * 1024, 30 * 86400
TYPES = {'session_started','phase_entered','map_target_collected','label_set','old_label_confirmed','help_opened','explanation_opened','architecture_selected','run_opened','result_opened','final_opened','session_reset','known_error'}
IMAGES={'tutorial_ic2006','child_m85','child_ic5332','child_ngc5023','old_ngc3610','old_ngc7090','fixed_ngc3318','fixed_ngc691','fixed_ic755','review_m49','review_ngc3982','review_ngc4762','final_ngc2768','final_ngc6814','final_ngc5775'}
LABELS={'smooth','spiral','edge_on'}
PHASES={'intro','story','collect','tutorial','labels','review','repair','model','final','free'}
UUID=re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
VERSION=re.compile(r'^[A-Za-z0-9._-]{1,64}$')
def architecture(value):
    tokens=value.split('-') if isinstance(value,str) else []
    return bool(tokens and tokens[0] in {'d1','d2'} and 2<=len(tokens)<=4 and 'r' in tokens[1:] and len(set(tokens[1:]))==len(tokens)-1 and set(tokens[1:]) <= {'r','bn','d'})
def valid_detail(detail):
    if not isinstance(detail,dict): return False
    for key,value in detail.items():
        if isinstance(value,(list,dict,set)): return False
        if key=='phase' and value in PHASES: continue
        if key=='imageId' and isinstance(value,str) and value in IMAGES: continue
        if key in {'before','after','label'} and value in LABELS: continue
        if key=='architecture' and architecture(value): continue
        if key=='experimentKey' and isinstance(value,str) and len(value)==7 and set(value)<={'0','1','2'}: continue
        if key=='scope' and value in {'review','final','comparison'}: continue
        if key in {'correct','total'} and type(value) is int and 0<=value<=99: continue
        if key=='code' and value in {'network_error','timeout','storage_unavailable','queue_overflow','invalid_response'}: continue
        return False
    return True
def connect(path=None):
    path = path or DB
    db=sqlite3.connect(path, timeout=5)
    try:
        db.execute('CREATE TABLE IF NOT EXISTS events (session_id TEXT NOT NULL, seq INTEGER NOT NULL, received INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY(session_id,seq))')
        return db
    except sqlite3.Error:
        db.close(); raise
def valid(event):
    required={'schema','eventId','sessionId','seq','elapsedMs','gameVersion','protocolVersion','channel','type','detail'}
    if not isinstance(event,dict) or set(event)!=required or type(event.get('schema')) is not int or event['schema']!=1 or not isinstance(event.get('type'),str) or event['type'] not in TYPES: return False
    if not isinstance(event.get('sessionId'),str) or not UUID.fullmatch(event['sessionId']) or not isinstance(event.get('eventId'),str) or not UUID.fullmatch(event['eventId']): return False
    if type(event.get('seq')) is not int or not 1 <= event['seq'] <= 2_000_000 or type(event.get('elapsedMs')) is not int or not 0 <= event['elapsedMs'] <= 86_400_000: return False
    if event['channel'] != 'web' or not valid_detail(event['detail']): return False
    return all(isinstance(event[x],str) and VERSION.fullmatch(event[x]) for x in ('gameVersion','protocolVersion'))
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self,status,data):
        raw=json.dumps(data,separators=(',',':')).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        if self.path != '/health': return self.reply(405,{'error':'POST only'})
        try:
            db=connect(); db.execute('SELECT 1'); db.close()
        except sqlite3.Error: return self.reply(503,{'ready':False})
        self.reply(200,{'ready':True})
    def do_POST(self):
        if self.path != '/telemetry/v1/events': return self.reply(404,{'error':'not found'})
        origin=self.headers.get('Origin')
        if origin and origin != 'https://sd2026.beetles.family': return self.reply(403,{'error':'origin mismatch'})
        if self.headers.get('Content-Type','').split(';')[0] != 'application/json': return self.reply(415,{'error':'json required'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 1 <= length <= MAX_BODY: raise ValueError()
            data=json.loads(self.rfile.read(length)); events=data.get('events') if isinstance(data,dict) and set(data)=={'events'} else None
            if not isinstance(events,list) or not 1 <= len(events) <= 20 or not all(valid(e) for e in events): raise ValueError()
        except (ValueError,TypeError,json.JSONDecodeError): return self.reply(400,{'error':'invalid event batch'})
        now=int(time.time())
        try: db=connect()
        except sqlite3.Error: return self.reply(503,{'error':'storage unavailable'})
        try:
            db.execute('DELETE FROM events WHERE received < ?', (now-RETENTION,))
            for event in events:
                body=json.dumps(event,separators=(',',':'),sort_keys=True)
                old=db.execute('SELECT body FROM events WHERE session_id=? AND seq=?',(event['sessionId'],event['seq'])).fetchone()
                if old and old[0] != body: return self.reply(409,{'error':'conflicting duplicate'})
                if not old: db.execute('INSERT INTO events VALUES (?,?,?,?)',(event['sessionId'],event['seq'],now,body))
            db.commit()
        except sqlite3.Error: return self.reply(503,{'error':'storage unavailable'})
        finally: db.close()
        self.reply(202,{'accepted':len(events)})
def cleanup(now=None):
    db=connect()
    try: db.execute('DELETE FROM events WHERE received < ?', ((int(time.time()) if now is None else now)-RETENTION,)); db.commit()
    finally: db.close()
class Server(ThreadingHTTPServer):
    def __init__(self, address):
        super().__init__(address,Handler)
        self.stop_cleanup=threading.Event()
        self.reaper=threading.Thread(target=self.maintain,daemon=True)
        self.reaper.start()
    def maintain(self):
        while not self.stop_cleanup.is_set():
            try: cleanup()
            except sqlite3.Error: pass
            self.stop_cleanup.wait(3600)
    def server_close(self):
        self.stop_cleanup.set(); self.reaper.join(timeout=6)
        super().server_close()
def create_server(host='127.0.0.1',port=8091):
    return Server((host,port))
if __name__ == '__main__': create_server(os.environ.get('TELEMETRY_BIND','0.0.0.0'),int(os.environ.get('TELEMETRY_PORT','8091'))).serve_forever()
