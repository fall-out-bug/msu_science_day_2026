#!/usr/bin/env python3
"""Prove the visible finale, animation pause, and reduced-motion behavior via UI."""
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_support import launch_chromium
import json, os, sys

HERE = Path(__file__).resolve().parent
ENTRY = sys.argv[1] if len(sys.argv) > 1 else (HERE / 'night.html').as_uri()
OUT = Path(os.environ.get('NIGHT_EVIDENCE_DIR', str(HERE / 'evidence')))
OUT.mkdir(exist_ok=True)
checks, errors = [], []

def check(name, ok):
    if not ok:
        raise AssertionError(name)
    checks.append(name)

with sync_playwright() as pw:
    browser = launch_chromium(pw)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000}, reduced_motion='no-preference')
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(ENTRY)
    page.locator('input[value="3"]').check()
    page.locator('#g-start').click()

    def picture():
        return page.locator('#g-room-scene canvas').evaluate('e=>e.toDataURL()')

    def sky_red():
        return page.locator('#g-room-scene canvas').evaluate('e=>e.getContext("2d").getImageData(Math.round(e.width*.6),Math.round(e.height*.39),1,1).data[0]')

    def nav():
        page.locator('#g-room-map').click()
        page.locator('#g-map-focus').click()
        page.locator('#g-map-capture').click()
        page.locator('#g-room-instrument').click()

    def pick(x, y):
        box = page.locator('#g-sky').bounding_box()
        page.mouse.click(box['x']+(x+.5)/128*box['width'], box['y']+(y+.5)/128*box['height'])

    def action():
        page.locator('#g-action').click()

    def train():
        page.locator('#g-room-next').click()
        check('scene route opens training workshop', page.evaluate("night.state.stage==='training'"))
        for ex in page.evaluate('NightModel.examples.map(e=>({id:e.id,label:e.expectedLabel}))'):
            page.locator(f".training-picker [data-example='{ex['id']}']").click()
            page.locator(f".training-decision [data-label='{ex['label']}']").click()
        page.get_by_role('button',name='2. Обучение').click()
        page.locator('#g-train-model').click();page.locator('#g-test-model').click()
        check('scene route evaluates trained model',page.evaluate('NightModel.trainingStatus(night.session).evaluated'))
        page.get_by_role('button',name='Применить модель в смене →').click()

    page.wait_for_timeout(250)
    before = picture(); page.wait_for_timeout(300)
    check('room character has visible idle motion', before != picture())
    page.locator('#g-pause').click()
    page.wait_for_timeout(80)
    before = picture(); page.wait_for_timeout(300)
    check('pause freezes the actual rendered canvas', before == picture())
    page.locator('#g-close').click()
    page.wait_for_timeout(100)
    before = picture(); page.wait_for_timeout(300)
    check('closing pause resumes the room', before != picture())
    page.emulate_media(reduced_motion='reduce')
    page.wait_for_timeout(100)
    before = picture(); page.wait_for_timeout(300)
    check('reduced motion makes the room still', before == picture())
    page.emulate_media(reduced_motion='no-preference')

    nav(); pick(58, 68); action(); action(); action()
    check('saved observation changes Nika reaction', page.locator('#g-room-scene').get_attribute('data-expression') == 'pleased')
    page.wait_for_timeout(900)
    page.screenshot(path=str(OUT/'scene-first-success.png'))
    train()
    nav(); pick(65, 64); action(); action(); action()
    nav(); page.locator("[data-tool='learning']").click(); action()
    page.wait_for_function("night.state.phase !== 'scanning'")
    page.locator('#g-candidates button').first.click(); action(); action()
    page.wait_for_timeout(250)
    night_red = sky_red()
    page.locator('#g-room-next').click()
    check('finale immediately exposes its actions', page.locator('#g-ending').is_visible() and page.locator('#g-ending-journal').is_enabled())
    page.wait_for_timeout(250)
    mid_red = sky_red()
    page.wait_for_timeout(1450)
    dawn_red = sky_red()
    check('dawn actually brightens the painted sky over time', dawn_red > night_red+70 and night_red < mid_red < dawn_red)
    check('ending keeps the room visible', page.locator('#g-room-scene').evaluate('e=>getComputedStyle(e).filter') == 'none')
    check('ending names the algorithm the player constructed', 'выборку из шести примеров' in page.locator('#g-ending-copy').inner_text() and 'Ложных тревог:' in page.locator('#g-ending-copy').inner_text())
    page.screenshot(path=str(OUT/'scene-ending-dawn.png'))

    for width, height in [(1280, 720), (900, 600), (390, 844)]:
        page.set_viewport_size({'width': width, 'height': height})
        page.wait_for_timeout(100)
        for selector in ['#g-continue', '#g-ending-journal', '#g-export', '#g-new']:
            check(f'{selector} is reachable at {width}', page.locator(selector).evaluate('e=>{const r=e.getBoundingClientRect();return r.y>=0 && r.bottom<=innerHeight && document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest("button")===e;}'))
        check(f'ending fits {width}', page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        page.screenshot(path=str(OUT/f'scene-ending-{width}.png'))
    page.locator('#g-ending-journal').click()
    check('final board opens the three real records', page.locator('#g-overlay .observation-card').count() == 3)
    page.wait_for_timeout(80)
    before = picture(); page.wait_for_timeout(250)
    check('reading ending evidence freezes character animation', before == picture())
    page.locator('#g-close').click()
    page.locator('#g-continue').click()
    check('continuation stays in the same morning', page.evaluate("night.state.stage==='room' && night.session.daylight && night.session.length===6"))
    page.reload(); page.locator('#g-resume').click()
    page.wait_for_timeout(1600)
    check('morning survives a page reload', page.locator('#g-room-scene').get_attribute('data-daylight') == 'true')
    check('no runtime errors', not errors)
    (OUT/'scene-browser.json').write_text(json.dumps({'entry': ENTRY, 'count': len(checks), 'checks': checks, 'errors': errors}, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'count': len(checks), 'errors': errors}))
    browser.close()
