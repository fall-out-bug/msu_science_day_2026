#!/usr/bin/env python3
"""Exercise optional sky activities through the rendered canvas and ordinary UI."""
from pathlib import Path
from urllib.parse import urlparse
import json, os, sys
from playwright.sync_api import sync_playwright
from browser_support import launch_chromium
HERE=Path(__file__).resolve().parent
ENTRY=sys.argv[1] if len(sys.argv)>1 else (HERE/'night.html').as_uri()
OUT=Path(os.environ.get('NIGHT_EVIDENCE_DIR',str(HERE/'evidence'))); OUT.mkdir(exist_ok=True)
checks=[]; errors=[]; external=[]
def check(name,value):
 if not value: raise AssertionError(name)
 checks.append(name)
with sync_playwright() as pw:
 browser=launch_chromium(pw)
 page=browser.new_page(viewport={'width':1280,'height':720},reduced_motion='reduce')
 page.set_default_timeout(6000)
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.on('request',lambda r:external.append(r.url) if r.url.startswith(('http:','https:')) and urlparse(r.url).netloc!=urlparse(ENTRY).netloc else None)
 page.add_init_script('''window.skyText=[];const ft=CanvasRenderingContext2D.prototype.fillText,cl=CanvasRenderingContext2D.prototype.fillRect;CanvasRenderingContext2D.prototype.fillText=function(t,x,y,...args){if(this.canvas.id==='g-celestial-map')skyText.push({t:String(t),x,y});return ft.call(this,t,x,y,...args);};CanvasRenderingContext2D.prototype.fillRect=function(...args){if(this.canvas.id==='g-celestial-map'&&args[0]===0&&args[1]===0)skyText=[];return cl.apply(this,args);};''')
 page.goto(ENTRY);page.locator('#g-meet').click()
 check('Nika can introduce herself before starting', 'Карачаево-Черкесии' in page.locator('#g-overlay').inner_text())
 page.locator('#g-close').click();page.locator('#g-start').click()
 def close():page.locator('#g-close').click()
 def shot(name):page.screenshot(path=str(OUT/('exploration-'+name+'.png')))
 def tap_text(text):
  page.wait_for_timeout(80)
  labels=page.evaluate('(t)=>skyText.filter(l=>l.t===t)',text)
  check('canvas draws '+text,bool(labels))
  l=labels[-1];box=page.locator('#g-celestial-map').bounding_box()
  page.mouse.click(box['x']+l['x'],box['y']+l['y']-4)
 def open_explore():
  if page.locator('.sky-explore').get_attribute('open') is None:page.locator('.sky-explore summary').click()
 # Character questions are written dialogue, with distinct answers.
 page.locator('#g-nika-talk').click();page.get_by_role('button',name='Ты уже что-нибудь открыла?',exact=True).click()
 check('Nika has a concrete past mistake', 'след самолёта' in page.locator('#g-overlay').inner_text());shot('nika');close()
 page.locator('#g-algorithm').click()
 check('ordinary rules, learning and verification are explained',page.locator('.algorithm-steps li').count()==3 and 'учится на твоей метке' in page.locator('#g-overlay').inner_text());close()
 page.locator('#g-discoveries').click()
 for title in ['Тысяча астероидов в старых снимках','Программа позвала другой телескоп','Восьмая планета у далёкой звезды']:
  # Use data-defined exact title for the third card to avoid making typography a contract.
  if title.startswith('Восьмая'): title=page.evaluate('NIGHT_STORIES.discoveries[2].title')
  page.get_by_role('button',name=title,exact=True).click()
  check('source link for '+title,page.locator('#g-overlay a').first.get_attribute('href').startswith('https://'))
  if page.locator('.discovery-photo img').count():
   page.wait_for_function("document.querySelector('.discovery-photo img').naturalWidth>1000")
   check('local credited Hubble image for '+title,'CC BY 4.0' in page.locator('figcaption').inner_text())
  if 'другой телескоп' in title:check('illustration is distinguished from ZTF target','другая сверхновая' in page.locator('#g-overlay').inner_text())
 page.get_by_role('button',name='Тысяча астероидов в старых снимках',exact=True).click();shot('hubble');close()
 page.locator('#g-room-mosaic').click();check('all twelve mosaic destinations',page.locator('.zodiac-grid button').count()==12);shot('mosaic')
 page.get_by_role('button',name='♉ Телец',exact=True).click()
 check('88 real constellation patterns loaded',page.evaluate('NIGHT_CONSTELLATIONS.length')==88)
 tap_text('Телец');check('constellation name opens its card',page.locator('#g-overlay').is_visible());close()
 open_explore();page.get_by_role('button',name='Вега',exact=True).click();close()
 page.locator('.sky-explore summary').click()
 # Vega is at the center after the destination jump; use the actual canvas as the pointer target.
 box=page.locator('#g-celestial-map').bounding_box();page.mouse.click(box['x']+box['width']/2,box['y']+box['height']/2)
 check('clicking a star opens its story','Лиры' in page.locator('#g-overlay').inner_text());close()
 check('visits do not duplicate',page.evaluate("night.session.exploration.visited.filter(x=>x==='vega').length")==1)
 for width,height in [(1280,720),(390,844)]:
  page.set_viewport_size({'width':width,'height':height});open_explore();page.locator('#g-pattern-start').click();shot('pattern-'+str(width))
  tap_text('3');check('wrong point does not advance '+str(width),'Готово: 0 из 5' in page.locator('#g-pattern-text').inner_text())
  for number in range(1,6):tap_text(str(number))
  check('five actual sky clicks complete '+str(width),'Получилось!' in page.locator('#g-pattern-text').inner_text())
  check('exploration did not create research evidence '+str(width),page.evaluate('night.session.records.length')==0)
  check('map fits screen '+str(width),page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
 page.reload();page.locator('#g-resume').click();check('activity survives reload',page.evaluate("night.session.exploration.patterns.includes('Кассиопея')"))
 page.locator('#g-room-map').click();open_explore();page.locator('#g-pattern-start').click()
 for i in range(1,6):page.get_by_role('button',name='Соединить звезду '+str(i),exact=True).click()
 check('keyboard alternative completes the same activity','Получилось!' in page.locator('#g-pattern-text').inner_text())
 page.locator('#g-map-focus').click();page.locator('#g-map-capture').click();shot('room-mobile')
 for id in ['g-room-map','g-room-mosaic','g-room-instrument','g-room-board']:
  check(id+' remains reachable on mobile',page.locator('#'+id).evaluate('e=>{const r=e.getBoundingClientRect();return r.y>=60&&r.bottom<=innerHeight&&document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest("button")===e}'))
 page.locator('#g-room-instrument').click()
 check('research target survives the excursion',page.evaluate("night.session.caseId==='s02' && night.state.stage==='game'"))
 page.locator('#g-guide').click();check('help highlights a reachable action',page.locator('#g-blink').evaluate('e=>e.classList.contains("guide-target")'));shot('guide-mobile')
 check('no browser errors',not errors);check('all runtime resources are local',not external)
 browser.close()
report={'count':len(checks),'checks':checks,'errors':errors,'externalRequests':external,'entry':ENTRY}
(OUT/'exploration-browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2))
