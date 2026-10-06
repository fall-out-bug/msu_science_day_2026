"""Targeted document QA; no production comments or game state are changed."""
import json,mimetypes,os,socket,subprocess,sys,tempfile,time,urllib.request,urllib.error,zipfile
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];PUB=ROOT/'designlab/comparison/docs'
with tempfile.TemporaryDirectory() as tmp:
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 base=f'http://127.0.0.1:{port}'
 env={**os.environ,'COMMENTS_DB':tmp+'/test.sqlite3','COMMENTS_BLOCKS':str(Path(__file__).with_name('blocks.json')),'COMMENTS_GDD_BLOCKS':str(Path(__file__).with_name('gdd-blocks.json')),'COMMENTS_PORT':str(port),'COMMENTS_BIND':'127.0.0.1'}
 proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name('server.py'))],env=env)
 try:
  for _ in range(100):
   try:urllib.request.urlopen(base+'/scenario-comments',timeout=1);break
   except OSError:time.sleep(.03)
  with sync_playwright() as pw:
   b=pw.chromium.launch(headless=True)
   def newpage():
    c=b.new_context();p=c.new_page();errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
    def route(r):
     url=urlsplit(r.request.url)
     if url.path=='/scenario-comments':
      req=urllib.request.Request(base+url.path+'?'+url.query,data=r.request.post_data.encode() if r.request.post_data else None,headers={'Content-Type':'application/json'})
      try:
       with urllib.request.urlopen(req) as response:r.fulfill(status=response.status,content_type='application/json',body=response.read())
      except urllib.error.HTTPError as e:r.fulfill(status=e.code,content_type='application/json',body=e.read())
     else:
      path=PUB/url.path.removeprefix('/docs/')
      assert path.is_relative_to(PUB)
      r.fulfill(content_type=mimetypes.guess_type(str(path))[0] or 'application/octet-stream',body=path.read_bytes())
    p.route('http://review.test/**',route);p.goto('http://review.test/docs/galaxy-game-design.html');return p,errors
   p,errors=newpage();assert 'атлас галактик' in p.title()
   p.locator('img').evaluate_all('es=>es.forEach(e=>e.loading="eager")');p.wait_for_function('[...document.images].filter(i=>i.hasAttribute("src")).every(i=>i.complete&&i.naturalWidth>0)')
   assert p.locator('.diagram svg').count()>=2
   assert p.locator('[data-comment-block^="n4d"]').count()>100
   registry=json.loads(Path(__file__).with_name('gdd-blocks.json').read_text()); current=p.evaluate('window.scenarioCommentBlocks'); assert all(registry[k]==v for k,v in current.items())
   historical=json.loads((ROOT/'docs/design-2026-10-06/history/before-nika/gdd-blocks.json').read_text());assert all(registry[k]==v for k,v in historical.items())
   for width,height in [(1920,1080),(1280,720),(900,600),(390,844)]:
    p.set_viewport_size({'width':width,'height':height});assert p.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,height)
   p.locator('[data-comment-block^="n4d"]').first.click();p.locator('#comment-message').fill('Обсуждение дизайна');p.get_by_role('button',name='Добавить комментарий',exact=True).click();p.get_by_text('Комментарий сохранён.',exact=True).wait_for()
   q,errors2=newpage();q.locator('[data-comment-block^="n4d"]').first.click();q.locator('#comment-panel article').filter(has_text='Обсуждение дизайна').wait_for()
   assert json.load(urllib.request.urlopen(base+'/scenario-comments?document=first-shift-v1'))==[]
   assert len(json.load(urllib.request.urlopen(base+'/scenario-comments?document=galaxy-gdd-v1')))==1
   q.get_by_role('button',name='Закрыть',exact=True).click();q.set_viewport_size({'width':1280,'height':900});q.locator('.screen-flow').scroll_into_view_if_needed();q.screenshot(path='/tmp/gdd-room-desktop.png')
   q.set_viewport_size({'width':390,'height':844});q.locator('#navigation-design').scroll_into_view_if_needed();q.screenshot(path='/tmp/gdd-mechanic-mobile.png')
   assert not errors+errors2,errors+errors2
   out=Path(tmp)/'offline';out.mkdir()
   with zipfile.ZipFile(PUB/'galaxy-design-offline.zip') as z:z.extractall(out)
   offline=b.new_context();o=offline.new_page();external=[];o.route('http://**/*',lambda r:(external.append(r.request.url),r.abort()));o.route('https://**/*',lambda r:(external.append(r.request.url),r.abort()))
   o.goto((out/'galaxy-game-design.html').as_uri());o.locator('img').evaluate_all('es=>es.forEach(e=>e.loading="eager")');o.wait_for_function('[...document.images].filter(i=>i.hasAttribute("src")).every(i=>i.complete&&i.naturalWidth>0)');assert not external
   o.goto((out/'gdd-assets/navigation-nika/preview.html').as_uri());o.get_by_role('button',name='Открыть архив →',exact=True).click();assert 'Один пример' in o.locator('main h2').inner_text();assert not external
   b.close()
  print('PASS: current images/diagrams, 4 viewports, preserved historical anchors, comments across browsers and document isolation, offline ZIP and navigation without external requests.')
 finally:proc.terminate();proc.wait()
