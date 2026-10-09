#!/usr/bin/env python3
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; SOURCE=ROOT/'designlab/galaxy-shift/telemetry.js'; records=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 page=browser.new_page(); page.goto((ROOT/'designlab/galaxy-shift/index.html').as_uri()); page.add_script_tag(path=str(SOURCE)); page.evaluate("sessionStorage.setItem('science-day.telemetry.v1','bad');GalaxyTelemetry.start({gameVersion:'test',protocolVersion:'p',channel:'zip'})")
 page.evaluate("for(let i=0;i<2005;i++) GalaxyTelemetry.record('phase_entered',{phase:'labels'})")
 d=page.evaluate('GalaxyTelemetry.diagnostics()'); x=json.loads(page.evaluate('GalaxyTelemetry.export()')); assert d['dropped']>0 and any(s.get('incomplete') for s in x['sessions']);records.append({'zip_overflow':d['dropped']})
 for status in (429,500,400):
  page=browser.new_page(); page.route('http://telemetry.test/**',lambda r:r.fulfill(status=(status if '/telemetry/' in r.request.url else 200),body='{}'));page.goto('http://telemetry.test/');page.add_script_tag(path=str(SOURCE));page.evaluate("window.game=1;GalaxyTelemetry.start({gameVersion:'test',protocolVersion:'p',channel:'web'});GalaxyTelemetry.record('phase_entered',{phase:'intro'})");page.wait_for_timeout(150);q=page.evaluate('GalaxyTelemetry.diagnostics().queued');assert page.evaluate('window.game')==1 and (q>=1 if status!=400 else q==0);records.append({'http':status,'queued':q})
 browser.close()
print(json.dumps({'status':'PASS','cases':records}))
