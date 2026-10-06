#!/usr/bin/env python3
"""Target 14-inch Full HD and scaled displays; verify visible teaching controls."""
from pathlib import Path
import os,json,sys
from playwright.sync_api import sync_playwright
from browser_support import launch_chromium
HERE=Path(__file__).resolve().parent
ENTRY=sys.argv[1] if len(sys.argv)>1 else (HERE/'night.html').as_uri()
OUT=Path(os.environ.get('NIGHT_EVIDENCE_DIR',str(HERE/'evidence')));OUT.mkdir(exist_ok=True)
checks=[];errors=[]
def check(name,ok):
 if not ok: raise AssertionError(name)
 checks.append(name)
with sync_playwright() as pw:
 browser=launch_chromium(pw)
 for width,height in [(1920,1080),(1536,864),(1280,720),(390,844)]:
  page=browser.new_page(viewport={'width':width,'height':height},reduced_motion='reduce');page.on('pageerror',lambda e:errors.append(str(e)));page.set_default_timeout(6000)
  page.goto(ENTRY);page.locator('#g-start').click()
  page.screenshot(path=str(OUT/f'pedagogy-room-{width}.png'))
  overlaps=page.evaluate('''() => {const selectors=['.room-objective','#g-room-map','#g-room-mosaic','#g-room-observatory','#g-room-instrument','#g-room-board','.room-dialog'];const out=[];for(let i=0;i<selectors.length;i++)for(let j=i+1;j<selectors.length;j++){const a=document.querySelector(selectors[i]).getBoundingClientRect(),b=document.querySelector(selectors[j]).getBoundingClientRect();if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>2&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>2)out.push([selectors[i],selectors[j]]);}return out;}''')
  check(f'room labels do not overlap {width}: {overlaps}',not overlaps)
  page.locator('#g-room-map').click();page.locator('#g-map-focus').click();page.locator('#g-map-capture').click();page.locator('#g-room-instrument').click()
  box=page.locator('#g-sky').bounding_box();page.mouse.click(box['x']+58.5/128*box['width'],box['y']+68.5/128*box['height'])
  for _ in range(3):page.locator('#g-action').click()
  page.locator('#g-room-next').click()
  check(f'workshop starts without seeded labels {width}',page.evaluate('NightModel.trainingStatus(night.session).labeledCount===0'))
  page.screenshot(path=str(OUT/f'pedagogy-label-{width}.png'),full_page=True)
  check(f'training does not overflow horizontally {width}',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
  if width>=1280:
   check(f'both label buttons visible on screen {width}',page.locator('[data-label]').evaluate_all('(items)=>items.every(e=>e.getBoundingClientRect().bottom<=innerHeight)'))
  for ex in page.evaluate('NightModel.examples'):
   page.locator(f'[data-example="{ex["id"]}"]').click();page.locator('[data-label="wrongLink"]').click()
  page.get_by_role('button',name='К обучению модели →',exact=True).click()
  check(f'one-class dataset cannot train {width}',page.locator('#g-train-model').is_disabled())
  page.get_by_role('button',name='1. Разметка 6/6',exact=True).click();page.locator('[data-example="5:4:3"]').click();page.locator('[data-label="sameObject"]').click()
  page.get_by_role('button',name='К обучению модели →',exact=True).click();page.locator('#g-train-model').click()
  check(f'training does not silently evaluate controls {width}',page.evaluate('NightModel.trainingStatus(night.session).trained && !NightModel.trainingStatus(night.session).evaluated'))
  page.locator('#g-test-model').click();page.screenshot(path=str(OUT/f'pedagogy-test-{width}.png'),full_page=True)
  if width>=1280:
   check(f'apply button visible on scaled screen {width}',page.get_by_role('button',name='Применить модель в смене →',exact=True).evaluate('e=>e.getBoundingClientRect().bottom<=innerHeight'))
  check(f'actual control errors are visible {width}','Ложных тревог: 2' in page.locator('.training-score').inner_text())
  check(f'control set remains outside fit {width}',page.evaluate('night.session.training.snapshot.labels.length===6 && night.session.training.evaluation.total===9'))
  page.get_by_role('button',name='Изменить мою разметку',exact=True).click();page.locator('[data-example="5:4:5"]').click();page.locator('[data-label="sameObject"]').click()
  check(f'edit invalidates model and evaluation {width}',page.evaluate('!NightModel.trainingStatus(night.session).trained && !NightModel.trainingStatus(night.session).evaluated'))
  page.close()
 check('no runtime errors',not errors)
 browser.close()
report={'count':len(checks),'checks':checks,'errors':errors,'entry':ENTRY};(OUT/'pedagogy-browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))
