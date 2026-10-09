#!/usr/bin/env python3
import importlib.util,json,os,tempfile,threading,unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen
HERE=Path(__file__).parent; spec=importlib.util.spec_from_file_location('telemetry_server',HERE/'server.py'); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
class TelemetryServerTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); os.environ['TELEMETRY_DB']=str(Path(self.tmp.name)/'events.sqlite3'); mod.DB=os.environ['TELEMETRY_DB']; self.server=mod.create_server('127.0.0.1',0); self.thread=threading.Thread(target=self.server.serve_forever); self.thread.start(); self.url=f'http://127.0.0.1:{self.server.server_port}/telemetry/v1/events'
 def tearDown(self): self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
 def event(self): return {'schema':1,'eventId':'123e4567-e89b-42d3-a456-426614174000','sessionId':'123e4567-e89b-42d3-a456-426614174001','seq':1,'elapsedMs':0,'gameVersion':'test','protocolVersion':'protocol','channel':'web','type':'architecture_selected','detail':{'architecture':'d1-bn-r'}}
 def post(self,body,headers=None): return urlopen(Request(self.url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json',**(headers or {})}))
 def test_accepts_duplicate_without_storing_twice(self):
  with self.post({'events':[self.event()]}) as one:self.assertEqual(one.status,202)
  with self.post({'events':[self.event()]}) as two:self.assertEqual(two.status,202)
  db=mod.connect()
  try:self.assertEqual(db.execute('select count(*) from events').fetchone()[0],1)
  finally:db.close()
 def test_rejects_free_text_and_get(self):
  event=self.event();event['detail']={'note':'child name'}
  with self.assertRaises(HTTPError) as err:self.post({'events':[event]})
  self.assertEqual(err.exception.code,400)
  err.exception.close()
  with self.assertRaises(HTTPError) as err:urlopen(self.url)
  self.assertEqual(err.exception.code,405)
  err.exception.close()
 def test_rejects_malformed_root_arrays_origin_and_bool(self):
  bad=[[],{'events':[self.event()],'extra':1},{'events':[self.event(),[]]},{'events':[self.event()]*21}]
  for body in bad:
   with self.assertRaises(HTTPError) as err:self.post(body)
   self.assertEqual(err.exception.code,400)
   err.exception.close()
  event=self.event();event['seq']=True
  with self.assertRaises(HTTPError) as err:self.post({'events':[event]})
  self.assertEqual(err.exception.code,400)
  err.exception.close()
  with self.assertRaises(HTTPError) as err:self.post({'events':[self.event()]},{'Origin':'https://evil.example'})
  self.assertEqual(err.exception.code,403)
  err.exception.close()
 def test_conflict_is_atomic_and_payload_order_irrelevant(self):
  first=self.event()
  with self.post({'events':[first]}) as r:self.assertEqual(r.status,202)
  with self.post({'events':[dict(reversed(list(first.items())))]}) as r:self.assertEqual(r.status,202)
  conflict={**first,'elapsedMs':100}
  second={**first,'seq':2,'eventId':'123e4567-e89b-42d3-a456-426614174002'}
  with self.assertRaises(HTTPError) as err:self.post({'events':[second,conflict]})
  self.assertEqual(err.exception.code,409);err.exception.close()
  db=mod.connect()
  try:self.assertEqual(db.execute('select count(*) from events').fetchone()[0],1)
  finally:db.close()
 def test_validator_total_and_unavailable_db(self):
  for name in self.event():
   malformed={**self.event(),name:[]}
   self.assertFalse(mod.valid(malformed))
  mod.DB=str(Path(self.tmp.name)/'missing/events.sqlite3')
  with self.assertRaises(HTTPError) as err:self.post({'events':[self.event()]})
  self.assertEqual(err.exception.code,503);err.exception.close()
 def test_idle_retention(self):
  db=mod.connect(); db.execute('insert into events values (?,?,?,?)',('123e4567-e89b-42d3-a456-426614174001',1,1,'{}'));db.commit();db.close()
  mod.cleanup(mod.RETENTION+2)
  db=mod.connect()
  try:self.assertEqual(db.execute('select count(*) from events').fetchone()[0],0)
  finally:db.close()
if __name__=='__main__':unittest.main()
