#!/usr/bin/env python3
"""Exercise actual sky aiming, room receipts, persistence, and physical controls."""
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_support import launch_chromium
import json,sys,os
base=Path(__file__).resolve().parent;entry=sys.argv[1] if len(sys.argv)>1 else (base/'night.html').as_uri();out=Path(os.environ.get('NIGHT_EVIDENCE_DIR',str(base/'evidence')));out.mkdir(exist_ok=True);checks=[];errors=[]
def check(name,ok):
 if not ok: raise AssertionError(name)
 checks.append(name)
with sync_playwright() as p:
 browser=launch_chromium(p)
 page=browser.new_page(viewport={'width':1440,'height':1000},reduced_motion='no-preference');page.on('pageerror',lambda e:errors.append(str(e)));page.goto(entry);page.locator('#g-start').click()
 def snap(name):page.screenshot(path=str(out/('world-'+name+'.png')))
 def nav():
  page.locator('#g-room-map').click();page.locator('#g-map-focus').click();page.locator('#g-map-capture').click();page.locator('#g-room-instrument').click()
 def pick(x,y):
  b=page.locator('#g-sky').bounding_box();page.mouse.click(b['x']+(x+.5)/128*b['width'],b['y']+(y+.5)/128*b['height'])
 def act():page.locator('#g-action').click()
 for selector in ['#g-room-map','#g-room-instrument','#g-room-board']:
  b=page.locator(selector).bounding_box();check(selector+' fits viewport',b['x']>=0 and b['y']>=60 and b['x']+b['width']<=1440 and b['y']+b['height']<=1000)
 snap('room-start');page.locator('#g-room-map').click();page.wait_for_timeout(150);snap('sky');b=page.locator('#g-celestial-map').bounding_box()
 page.mouse.move(b['x']+b['width']*.67,b['y']+b['height']*.4);page.mouse.down();page.mouse.move(b['x']+b['width']*.5,b['y']+b['height']*.5,steps=12);page.mouse.up()
 check('manual drag aligns real field without coordinate shortcut',page.locator('#g-map-capture').is_enabled());snap('aimed')
 page.keyboard.press('ArrowRight');check('moving away disables capture',page.locator('#g-map-capture').is_disabled());page.keyboard.press('Home');check('keyboard Home recovers target',page.locator('#g-map-capture').is_enabled())
 page.locator('#g-pause').click();check('map pauses behind modal',page.locator('#g-overlay').is_visible());page.locator('#g-close').click();page.locator('#g-map-capture').click();page.reload();page.locator('#g-resume').click()
 check('reload retains selected field',page.evaluate("night.session.aimedCase==='s02'") and page.locator('#g-room-instrument').is_enabled())
 page.locator('#g-room-instrument').click();pick(58,68);page.locator('#g-room-back').click();page.locator('#g-room-instrument').click();check('room visit keeps unsaved selected point',page.evaluate("night.state.phase==='selected' && night.state.selected.point.x===58"));act();act();act();page.wait_for_timeout(720);snap('first-result')
 check('first result returns to physical room with receipt',page.locator('#g-room').is_visible() and page.locator('#g-room-result').is_visible() and page.evaluate('night.session.records.length===1'))
 page.locator('#g-room-board').click();check('physical board opens real saved observation',page.locator('#g-overlay canvas').count()==3);page.locator('#g-close').click();page.locator('#g-room-next').click();page.locator('#g-candidates button').nth(2).click();act();snap('learned-room');nav();pick(65,64);act();act();act();page.wait_for_timeout(720);snap('two-results')
 check('room preserves two observations and installed instruments',page.evaluate('night.session.installed.movement && night.session.installed.fading && night.session.records.length===2'))
 page.reload();page.locator('#g-resume').click();check('reload targets next field and displays last receipt',page.evaluate("night.session.worldTarget==='s07'") and page.locator('#g-room-result').is_visible())
 for w,h in [(1280,720),(900,600),(390,844)]:
  page.set_viewport_size({'width':w,'height':h});page.wait_for_timeout(720);snap('room-'+str(w))
  for selector in ['#g-room-map','#g-room-instrument','#g-room-board']:
   b=page.locator(selector).bounding_box();check(selector+' fits '+str(w),b['x']>=0 and b['y']>=50 and b['x']+b['width']<=w and b['y']+b['height']<=h)
   check(selector+' is not covered '+str(w),page.locator(selector).evaluate('(e)=>{const r=e.getBoundingClientRect();return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest("button")===e;}'))
  check('room no horizontal overflow '+str(w),page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
 page.locator('#g-room-map').click();page.wait_for_timeout(200);snap('sky-mobile');page.locator('#g-map-focus').click();page.locator('#g-map-capture').click();page.locator('#g-room-instrument').click();page.wait_for_timeout(300);snap('instrument-mobile')
 check('mobile room controls reach instrument',page.locator('#g-game').is_visible());check('runtime error free',not errors)
 (out/'world-browser.json').write_text(json.dumps({'entry':entry,'count':len(checks),'checks':checks,'errors':errors},ensure_ascii=False,indent=2));print(json.dumps({'count':len(checks),'errors':errors}));browser.close()
