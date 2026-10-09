#!/usr/bin/env python3
"""Check exact web/ZIP resources and a visible baseline/constructor journey."""
import argparse
import hashlib
import importlib.util
import json
import shlex
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
GAME=ROOT/'designlab/galaxy-shift'
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    loaded=importlib.util.module_from_spec(spec);spec.loader.exec_module(loaded);return loaded

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default='http://192.168.50.12:8080')
    parser.add_argument('--ssh-host',help='Fetch and run browser via a temporary SSH SOCKS tunnel')
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--preservation',type=Path,required=True)
    args=parser.parse_args()
    base=args.base.rstrip('/')+'/'
    manifest=json.loads((GAME/'releases/build.json').read_text())
    documents={name:hashlib.sha256((ROOT/'designlab/comparison/docs'/name).read_bytes()).hexdigest()
               for name in ['galaxy-game-design.html','technical-plan.html','acceptance.html','goal.html','baseline.html','text-review.html','release.html','programme.html','learning-review.html','game-design-foundation.html','goal-20261008.html','release-20261008.html','galaxy-design-offline.zip','galaxy-game-design-20261006.html']}
    expected={'base':base,'manifest':manifest,'zip':hashlib.sha256((GAME/'releases/galaxy-shift.zip').read_bytes()).hexdigest(),
              'documents':documents,'preserve':json.loads(args.preservation.read_text())}
    verifier='''import sys,json,hashlib,urllib.request
expected=json.load(sys.stdin)
def read(path):
 with urllib.request.urlopen(expected['base']+path,timeout=25) as r:return r.read()
manifest=json.loads(read('build.json'));assert manifest==expected['manifest']
for name,digest in manifest['files'].items():assert hashlib.sha256(read(name)).hexdigest()==digest,name
assert hashlib.sha256(read('galaxy-shift.zip')).hexdigest()==expected['zip']
for name,digest in expected['documents'].items():assert hashlib.sha256(read('docs/'+name)).hexdigest()==digest,name
for name,digest in expected['preserve']['files'].items():assert hashlib.sha256(read(name)).hexdigest()==digest,name
count=0
for document,old in expected['preserve']['comments'].items():
 rows=json.loads(read('scenario-comments?document='+document))
 current={str(r['id']):hashlib.sha256(json.dumps(r,ensure_ascii=False,sort_keys=True).encode()).hexdigest() for r in rows}
 assert all(current.get(key)==digest for key,digest in old.items()),document
 count+=len(old)
print(json.dumps({'status':'PASS','resources':len(manifest['files']),'documents':len(expected['documents']),'preservedComments':count,'zipSha256':expected['zip']}))
'''
    command=['python3','-c',verifier] if not args.ssh_host else ['ssh','-o','BatchMode=yes',args.ssh_host,'python3 -c '+shlex.quote(verifier)]
    checked=subprocess.run(command,input=json.dumps(expected),text=True,capture_output=True,timeout=300)
    if checked.returncode:raise RuntimeError(checked.stderr[-3000:])
    assets=json.loads(checked.stdout)
    journey=module('telemetry_flow',ROOT/'tools/galaxy-telemetry/check-integration.py')
    editor=module('constructor_flow',GAME/'check-complete-browser.py')
    original_click=journey.click
    def checked_click(page, action):
        if action=='collect-map': editor.story_frame_visible(page)
        original_click(page, action)
    journey.click=checked_click
    tunnel=None
    try:
        options={}
        if args.ssh_host:
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            tunnel=subprocess.Popen(['ssh','-N','-D',f'127.0.0.1:{port}','-o','ExitOnForwardFailure=yes','-o','BatchMode=yes',args.ssh_host],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            for _ in range(60):
                if tunnel.poll() is not None:raise RuntimeError('SSH tunnel did not start')
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('SSH tunnel timed out')
            options={'proxy':{'server':f'socks5://127.0.0.1:{port}'}}
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,**options)
            context=browser.new_context(viewport={'width':1280,'height':720},reduced_motion='reduce')
            page=context.new_page();errors=[];failures=[];requests=[];responses=[];console=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('requestfailed',lambda request:failures.append({'url':request.url,'reason':request.failure}))
            page.on('request',lambda request:requests.append(request.url))
            page.on('console',lambda message:console.append(message.text) if message.type=='error' else None)
            page.on('response',lambda response:responses.append({'url':response.url,'status':response.status}))
            page.goto(base);page.wait_for_function('window.galaxyGame')
            assert page.evaluate('GALAXY_BUILD_VERSION')==manifest['version']
            data=journey.journey(page)
            baseline=page.evaluate('galaxyGame.model.state.baseline')
            guided=page.evaluate('galaxyGame.model.state.current')
            assert baseline['architecture']=='d1-r' and guided['architecture']=='d2-r'
            page.locator('.research-board > summary').click()
            journey.click(page,'labels');journey.click(page,'run')
            page.wait_for_function("galaxyGame.model.state.phase==='review'")
            journey.click(page,'model-settings')
            config=page.evaluate("GalaxyArchitectures.get('d2-d-bn-r')")
            editor.build_architecture(page,config)
            journey.click(page,'finish');page.wait_for_function("galaxyGame.model.state.phase==='final'")
            page.locator('.final-room').wait_for(state='visible')
            page.wait_for_function("!document.querySelector('.cnn-run-status') && [...document.querySelectorAll('#game img')].every(image => image.complete && image.naturalWidth > 0)")
            final=page.evaluate('galaxyGame.model.state.current')
            page.wait_for_function('GalaxyTelemetry.diagnostics().queued===0',timeout=15000)
            session_id=page.evaluate('GalaxyTelemetry.sessionId')
            telemetry=page.evaluate('GalaxyTelemetry.diagnostics()')
            receipts=[item['status'] for item in responses if urlsplit(item['url']).path=='/telemetry/v1/events']
            unexpected=[item for item in responses if item['status']>=400 and not (urlsplit(base).scheme=='http' and urlsplit(item['url']).path=='/telemetry/v1/events' and item['status']==403)]
            assert not unexpected,unexpected
            if urlsplit(base).scheme=='https':
                assert receipts and all(status==202 for status in receipts),receipts
                assert telemetry['dropped']==0,telemetry
                assert not console,console
            else:
                assert receipts and all(status==403 for status in receipts),receipts
                assert not [line for line in console if '403' not in line],console
            assert not errors,errors
            assert not failures,failures
            assert all(urlsplit(url).netloc==urlsplit(base).netloc for url in requests if url.startswith(('http:','https:')))
            browser.close()
        report={'status':'PASS','base':base,'version':manifest['version'],'transport':'HTTPS with normal certificate verification via '+args.ssh_host if args.ssh_host else 'direct HTTP upstream',
                'assets':assets,'flow':{'baseline':baseline['architecture'],'guided':guided['architecture'],'constructor':final['architecture'],'labelKey':final['labelKey'],'firstReview':baseline['result']['review']['correct'],'finalReview':final['result']['review']['correct'],'final':final['result']['final']['correct'],'errors':errors,'failedRequests':failures,'telemetrySessionId':session_id,'telemetryResponses':receipts,'telemetry':telemetry,'consoleErrors':console,'ingestionScope':'public HTTPS' if urlsplit(base).scheme=='https' else 'LAN origin intentionally denied; public ingestion checked separately'}}
        args.evidence.parent.mkdir(parents=True,exist_ok=True);args.evidence.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))
    finally:
        if tunnel:
            tunnel.terminate()
            try:tunnel.wait(timeout=10)
            except subprocess.TimeoutExpired:tunnel.kill();tunnel.wait()

if __name__=='__main__':main()
