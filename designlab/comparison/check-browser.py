#!/usr/bin/env python3
"""Exercise actual input, consequences, replay, and responsive rendering."""
from pathlib import Path
import json
import os
import sys
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[2]
def launch(playwright):
    # PW_CHROMIUM supports a separately installed browser on ARM hosts.
    executable = os.environ.get('PW_CHROMIUM')
    if not executable:
        candidates = sorted((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux/chrome'))
        executable = str(candidates[-1]) if candidates else None
    options = {'headless': True}
    if executable:
        options['executable_path'] = executable
    return playwright.chromium.launch(**options), 'chromium'
HERE = Path(__file__).resolve().parent
ENTRY = sys.argv[1] if len(sys.argv)>1 else (HERE/'index.html').as_uri()
OUT=HERE/'evidence'; OUT.mkdir(exist_ok=True)
checks,errors=[],[]
def check(name, condition):
    assert condition, name
    checks.append(name)
with sync_playwright() as p:
    browser,engine=launch(p)
    context=browser.new_context(viewport={'width':1440,'height':1050},reduced_motion='reduce')
    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(ENTRY)
    page.wait_for_function('window.comparisonProbe && document.querySelector("#game canvas")')
    def snap(name):page.screenshot(path=str(OUT/(name+'.png')),full_page=True)
    def point(x,y,side=1):
        page.locator('#game').scroll_into_view_if_needed()
        box=page.locator('#game canvas').bounding_box()
        narrow=page.evaluate('matchMedia("(max-width:760px)").matches')
        width=480 if narrow else 960
        left=48 if narrow or side==0 else 536
        size=384 if narrow else 376
        page.mouse.click(box['x']+(left+(x+.5)/128*size)/width*box['width'],box['y']+(84+(y+.5)/128*size)/520*box['height'])
    def follow(outcome):
        page.locator('#follow').click()
        page.wait_for_function('comparisonProbe.state.phase==="result"')
        check('computed outcome '+outcome,page.evaluate('comparisonProbe.state.result.outcome')==outcome)
    check('entry gives goal and requires a target',page.locator('#follow').is_disabled() and 'движущийся' in page.locator('h1').inner_text())
    check('third frame not exposed on entry',page.evaluate('comparisonProbe.state.result===null && comparisonProbe.game.scene.scenes[0].rects.length===2'))
    snap('entry')
    point(100,100)
    check('empty sky explains failed selection',page.locator('#follow').is_disabled() and 'не видит' in page.locator('#feedback').inner_text())
    point(58,68,side=0)
    check('first frame cannot choose target',page.locator('#follow').is_disabled())
    point(71,10)
    check('pointer selects measured source',page.evaluate('comparisonProbe.state.selection.point.x')==71)
    snap('selected')
    follow('stationary');snap('stationary')
    check('stationary has explanation and no reward',page.evaluate('comparisonProbe.state.journal.length')==0 and 'осталась' in page.locator('#outcome-title').inner_text())
    saved=page.evaluate('JSON.stringify(comparisonProbe.state.attempts[0])')
    page.locator('#retry').click();point(58,68);follow('moving');snap('moving')
    check('success possible without slider',page.evaluate('comparisonProbe.state.amount===0 && comparisonProbe.state.journal.length===1'))
    check('earlier attempt retained unchanged',saved==page.evaluate('JSON.stringify(comparisonProbe.state.attempts[0])'))
    check('retry recorded as already seen frame',page.evaluate('comparisonProbe.state.attempts[0].firstLook && !comparisonProbe.state.attempts[1].firstLook'))
    check('submitted result deeply frozen',page.evaluate('Object.isFrozen(comparisonProbe.state.attempts[1]) && Object.isFrozen(comparisonProbe.state.attempts[1].selection.point)'))
    check('observed position differs from prediction',page.evaluate('comparisonProbe.state.result.distancePx>0 && comparisonProbe.state.result.positions[2].x===91'))
    page.locator('#next-field').click()
    check('next field retains earned journal',page.evaluate('comparisonProbe.state.field===1 && comparisonProbe.state.journal.length===1'))
    page.locator('#tools summary').click();page.locator('#suppression').fill('100')
    check('helper changes setting without choosing target',page.evaluate('comparisonProbe.state.amount===1 && comparisonProbe.state.selection===null'))
    page.locator('#point-tools summary').click()
    index=page.evaluate('COMPARISON_DATA.cases[1].sources[1].findIndex(s=>s.x===59)+1')
    button=page.get_by_role('button',name=f'Выбрать точку {index}',exact=True)
    button.focus();page.keyboard.press('Enter')
    check('keyboard alternative selects same real point',page.evaluate('comparisonProbe.state.selection.point.x===59'))
    page.emulate_media(reduced_motion='no-preference');page.locator('#follow').click()
    check('check locks editing',page.locator('#suppression').is_disabled())
    page.emulate_media(reduced_motion='reduce');page.wait_for_function('comparisonProbe.state.phase==="result"')
    check('changing motion preference does not freeze check',page.evaluate('comparisonProbe.state.result.outcome==="moving"'))
    check('two field completion saved',page.locator('#journal-count').inner_text()=='2 / 2')
    snap('journal')
    page.locator('#retry').click();point(59,65);follow('moving')
    check('replaying same field does not duplicate reward',page.evaluate('comparisonProbe.state.journal.length===2'))
    page.locator('#restart').click()
    check('restart clears progress and choice',page.evaluate('comparisonProbe.state.journal.length===0 && comparisonProbe.state.attempts.length===0 && comparisonProbe.state.selection===null'))
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_function('comparisonProbe.game.scale.width===480')
    snap('mobile-entry')
    check('phone has no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
    page.locator('#frame-first').click();check('phone can inspect first exposure',page.evaluate('comparisonProbe.state.mobileView===0'))
    page.locator('#frame-second').click();point(58,68)
    check('phone coordinate mapping selects target',page.evaluate('comparisonProbe.state.selection.point.x===58'))
    follow('moving');snap('mobile-result')
    check('phone result preserves progress',page.evaluate('comparisonProbe.state.journal.length===1'))
    page.set_viewport_size({'width':1365,'height':950})
    page.wait_for_function('comparisonProbe.game.scale.width===960')
    check('resize preserves result',page.evaluate('comparisonProbe.state.result.outcome==="moving"'))
    # Replay guards also prevent a stale scheduled check from writing into reset state.
    page.evaluate('comparisonProbe.reset();comparisonProbe.choose(58,68);comparisonProbe.follow();comparisonProbe.reset()')
    page.wait_for_timeout(1000)
    check('reset cancels pending verification',page.evaluate('comparisonProbe.state.phase==="search" && comparisonProbe.state.journal.length===0'))
    check('no runtime errors',not errors)
    browser.close()
report={'count':len(checks),'checks':checks,'engine':engine,'entry':ENTRY,'errors':errors}
(OUT/'browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
