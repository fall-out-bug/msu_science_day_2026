import os,sys,tempfile,subprocess,time,json,socket,urllib.request,urllib.error
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory() as tmp:
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 base=f'http://127.0.0.1:{port}'
 env={**os.environ,'COMMENTS_DB':tmp+'/test.sqlite3','COMMENTS_BLOCKS':str(Path(__file__).with_name('blocks.json')),'COMMENTS_PORT':str(port),'COMMENTS_BIND':'127.0.0.1'}
 def start():
  p=subprocess.Popen([sys.executable,str(Path(__file__).with_name('server.py'))],env=env)
  for _ in range(100):
   try:urllib.request.urlopen(base+'/scenario-comments',timeout=1);return p
   except OSError:time.sleep(.03)
  raise RuntimeError('Server failed to start')
 def request(data=None,origin=None):
  headers={'Content-Type':'application/json'}
  if origin:headers['Origin']=origin
  req=urllib.request.Request(base+'/scenario-comments',data=json.dumps(data).encode() if data else None,headers=headers)
  try:
   with urllib.request.urlopen(req) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:return e.code,None
 proc=start()
 try:
  with sync_playwright() as pw:
   b=pw.chromium.launch(headless=True)
   def page():
    ctx=b.new_context();p=ctx.new_page();errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
    def route(r):
     path=r.request.url.split('review.test',1)[1].split('?')[0]
     if path=='/scenario-comments':
      data=r.request.post_data_json if r.request.method=='POST' else None
      code,value=request(data)
      r.fulfill(status=code,content_type='application/json',body=json.dumps(value))
     else:
      name=path.rsplit('/',1)[-1] or 'first-shift-scenario.html'
      mime='text/html' if name.endswith('.html') else 'text/javascript' if name.endswith('.js') else 'text/css'
      r.fulfill(content_type=mime,body=(root/'designlab/comparison/docs'/name).read_bytes())
    p.route('http://review.test/**',route);p.goto('http://review.test/first-shift-scenario.html');return p,errors
   a,errors=page();a.locator('[data-comment-block^="n4s"]').first.click();assert a.locator('input').count()==0
   text='<img src=x onerror=alert(1)> Проверка общего комментария'
   a.locator('#comment-message').fill(text);a.get_by_role('button',name='Добавить комментарий',exact=True).click();a.get_by_text('Комментарий сохранён.',exact=True).wait_for()
   c,errors2=page();c.locator('[data-comment-block^="n4s"]').first.click();c.locator('#comment-panel article').filter(has_text=text).wait_for();assert c.locator('#comment-panel article img').count()==0
   c.get_by_role('button',name='Закрыть',exact=True).click();c.locator('[data-comment-block^="n4s"]').nth(1).click();assert c.locator('#comment-panel article').count()==0
   c.set_viewport_size({'width':390,'height':844});assert c.evaluate('document.documentElement.scrollWidth<=innerWidth');c.screenshot(path='/tmp/scenario-comments-mobile.png')
   assert not errors+errors2
   b.close()
  code,rows=request();assert code==200 and len(rows)==1 and 'author' not in rows[0]
  assert request({'document':'first-shift-v1','block':'bad','text':'test'})[0]==400
  assert request({'document':'first-shift-v1','block':'p001','text':'test'},'https://other.example')[0]==403
  proc.terminate();proc.wait();proc=start();assert len(request()[1])==1
  print('PASS: anonymous submission, cross-browser visibility, block isolation, literal HTML, mobile layout, invalid block/origin rejection, persistence after restart.')
 finally:proc.terminate();proc.wait()
