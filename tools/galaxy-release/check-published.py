#!/usr/bin/env python3
"""Verify exact deployed resources, the playable HTTP flow and preservation."""
import argparse,hashlib,importlib.util,json,time,urllib.request,urllib.error
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
GAME=ROOT/'designlab/galaxy-shift'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base',default='http://192.168.50.12:8080')
parser.add_argument('--preservation',action='store_true')
args=parser.parse_args()
base=args.base.rstrip('/')
def read(path):
 for attempt in range(3):
  try:
   with urllib.request.urlopen(base+'/'+path,timeout=10) as response:return response.read()
  except urllib.error.URLError:
   if attempt==2:raise
   time.sleep(1)
manifest=json.loads((GAME/'releases/build.json').read_text())
assert json.loads(read('build.json'))==manifest
for name,digest in manifest['files'].items():assert hashlib.sha256(read(name)).hexdigest()==digest,name
assert hashlib.sha256(read('galaxy-shift.zip')).digest()==hashlib.sha256((GAME/'releases/galaxy-shift.zip').read_bytes()).digest()
assert read('legacy/') and read('night-shift.zip')
preserved=None
if args.preservation:
 previous=json.loads(Path('/home/zhuckoff/projects/msu/science_day/var/scenario-comments/before-galaxy-20261007.json').read_text())
 for name,digest in previous['docs'].items():assert hashlib.sha256(read('docs/'+name)).hexdigest()==digest,name
 count=0
 for document,old in previous['comments'].items():
  rows=json.loads(read('scenario-comments?document='+document))
  current={r['id']:hashlib.sha256(json.dumps(r,ensure_ascii=False,sort_keys=True).encode()).hexdigest() for r in rows}
  assert all(current.get(key)==digest for key,digest in old.items()),document
  count+=len(old)
 preserved={'documents':'exact original hashes','originalComments':count}
spec=importlib.util.spec_from_file_location('browser_checks',GAME/'check-browser.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True)
 context=browser.new_context(viewport={'width':1440,'height':900},reduced_motion='reduce')
 page=context.new_page()
 requests=[]
 page.on('request',lambda request:requests.append(request.url))
 result=module.run(page,base+'/',offline=False)
 assert all(urlsplit(url).netloc==urlsplit(base).netloc for url in requests if url.startswith(('http:','https:')))
 page.goto(base+'/');page.wait_for_function('galaxyWorld.stats().frames>0')
 page.screenshot(path=str(GAME/'evidence/live-intro.png'))
 browser.close()
report={'status':'PASS','base':base,'version':manifest['version'],'resources':len(manifest['files']),'zip':'exact local SHA-256','flow':result,'preserved':preserved}
(GAME/'evidence/published.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
