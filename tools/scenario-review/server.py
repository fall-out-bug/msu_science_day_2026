"""Shared comments for one fixed scenario; stdlib HTTP and SQLite."""
import json, os, sqlite3, uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from pathlib import Path
DB=os.environ.get('COMMENTS_DB','/data/comments.sqlite3')
BLOCKS=json.load(open(os.environ.get('COMMENTS_BLOCKS','/app/blocks.json')))
DOCUMENT='first-shift-v1'
DOCUMENT_BLOCKS={DOCUMENT:BLOCKS}
gdd_path=Path(os.environ.get('COMMENTS_GDD_BLOCKS',str(Path(__file__).with_name('gdd-blocks.json'))))
if gdd_path.exists():
    DOCUMENT_BLOCKS['galaxy-gdd-v1']=json.loads(gdd_path.read_text())
with sqlite3.connect(DB) as db:
    db.execute('CREATE TABLE IF NOT EXISTS comments (id TEXT PRIMARY KEY, document TEXT, block TEXT, quote TEXT, text TEXT, created TEXT)')
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self,status,data):
        payload=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers();self.wfile.write(payload)
    def do_GET(self):
        if urlsplit(self.path).path!='/scenario-comments':return self.reply(404,{'error':'Not found'})
        document=parse_qs(urlsplit(self.path).query).get('document',[DOCUMENT])[0]
        if document not in DOCUMENT_BLOCKS:return self.reply(400,{'error':'Unknown document'})
        with sqlite3.connect(DB) as db:
            db.row_factory=sqlite3.Row
            rows=[dict(r) for r in db.execute('SELECT * FROM comments WHERE document=? ORDER BY created,id',(document,))]
        self.reply(200,rows)
    def do_POST(self):
        if urlsplit(self.path).path!='/scenario-comments':return self.reply(404,{'error':'Not found'})
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.reply(415,{'error':'JSON required'})
        origin=self.headers.get('Origin')
        if origin and urlsplit(origin).netloc!=self.headers.get('Host'):return self.reply(403,{'error':'Origin mismatch'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=20000:return self.reply(413,{'error':'Too large'})
            row=json.loads(self.rfile.read(length))
            if not isinstance(row,dict):raise ValueError()
            for key,limit in [('text',4000),('block',20)]:
                if not isinstance(row.get(key),str) or not 0<len(row[key].strip())<=limit:raise ValueError()
                row[key]=row[key].strip()
            document=row.get('document')
            if not isinstance(document,str) or document not in DOCUMENT_BLOCKS or row['block'] not in DOCUMENT_BLOCKS[document]:raise ValueError()
        except (ValueError,TypeError):return self.reply(400,{'error':'Invalid comment'})
        saved=dict(id=str(uuid.uuid4()),document=document,block=row['block'],quote=DOCUMENT_BLOCKS[document][row['block']],text=row['text'],created=datetime.now(timezone.utc).isoformat())
        with sqlite3.connect(DB,timeout=10) as db:
            db.execute('INSERT INTO comments VALUES (?,?,?,?,?,?)',tuple(saved.values()))
        self.reply(201,saved)
ThreadingHTTPServer((os.environ.get('COMMENTS_BIND','0.0.0.0'),int(os.environ.get('COMMENTS_PORT','8090'))),Handler).serve_forever()
