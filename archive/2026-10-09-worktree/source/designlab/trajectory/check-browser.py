"""Bounded file:// smoke check; uses the workspace's existing Playwright runtime."""
from pathlib import Path
import hashlib
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from verify_common import chromium_executable
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE / 'evidence'
OUT.mkdir(exist_ok=True)
checks = []
def check(name, value):
    checks.append({'name': name, 'passed': bool(value)})
    assert value, name

def click_source(page, point):
    page.wait_for_timeout(80)
    box = page.locator('canvas').bounding_box()
    page.mouse.click(box['x'] + (4 + (point['x'] + .5) * 4) * box['width'] / 520,
                     box['y'] + (36 + (point['y'] + .5) * 4) * box['height'] / 552)

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=chromium_executable(), headless=True)
    page = browser.new_page(viewport={'width':1000,'height':1100})
    errors, remote = [], []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('request', lambda r: remote.append(r.url) if r.url.startswith(('http:', 'https:')) else None)
    page.goto((HERE / 'index.html').as_uri())
    page.wait_for_function('window.trajectoryProbe?.ready')
    check('Pinned Phaser 4.2.1 loads via file URL', page.evaluate('Phaser.VERSION') == '4.2.1')
    check('Third image initially concealed', page.locator('[data-epoch="2"]').is_disabled())
    page.locator('#blink').click()
    page.wait_for_function('trajectoryProbe.state.epoch === 1')
    page.locator('#blink').click()
    check('Blink changes the real displayed epoch', page.evaluate('trajectoryProbe.state.epoch') == 1)
    page.locator('#blend').fill('50')
    page.locator('#blend').dispatch_event('input')
    check('Blend input changes visible frame layers', page.evaluate('trajectoryProbe.state.blend') == 50)
    click_source(page, {'x':20,'y':20})
    check('Composite view cannot silently write an epoch mark', page.evaluate('trajectoryProbe.sessions[0].marks.every(p => p === null)'))
    page.locator('[data-epoch="0"]').click()
    click_source(page, {'x':70,'y':10})
    page.locator('[data-epoch="1"]').click()
    click_source(page, {'x':70,'y':10})
    check('Two pointer marks enable testing', page.locator('#test').is_enabled())
    page.locator('#test').click()
    frozen = page.evaluate('JSON.stringify(trajectoryProbe.sessions[0].frozen)')
    check('Wrong association produces actual miss', not page.evaluate('trajectoryProbe.sessions[0].result(true).withinTolerance'))
    page.screenshot(path=str(OUT / 'wrong-association.png'), full_page=True)
    truth = page.evaluate('TRAJECTORY_DATA[0].truth.targets')
    page.locator('[data-epoch="0"]').click()
    click_source(page, truth[0])
    page.locator('[data-epoch="1"]').click()
    click_source(page, truth[1])
    page.locator('#test').click()
    check('Revised player measurements recover', page.evaluate('trajectoryProbe.sessions[0].result().withinTolerance'))
    check('First forecast stays frozen after revision', frozen == page.evaluate('JSON.stringify(trajectoryProbe.sessions[0].frozen)'))
    check('Unequal timestamps govern extrapolation', abs(page.evaluate('trajectoryProbe.sessions[0].prediction.ratio') - 1) > .5)
    page.screenshot(path=str(OUT / 'revised-forecast.png'), full_page=True)
    page.locator('[data-case="1"]').click()
    check('Second real case has its own hidden third frame', page.locator('[data-epoch="2"]').is_disabled())
    page.locator('#help').click()
    check('Help is explicit and records assistance', page.evaluate('trajectoryProbe.sessions[1].assisted && trajectoryProbe.state.helpVisible'))
    truth2 = page.evaluate('TRAJECTORY_DATA[1].truth.targets')
    click_source(page, truth2[0])
    page.locator('[data-epoch="1"]').click()
    click_source(page, truth2[1])
    # Move the mark through a pointer drag and restore it by another drag.
    box = page.locator('canvas').bounding_box()
    def screen(q):
        return (box['x']+(4+(q['x']+.5)*4)*box['width']/520,
                box['y']+(36+(q['y']+.5)*4)*box['height']/552)
    start = screen(truth2[1]); moved = (start[0]+20,start[1]+12)
    before = page.evaluate('trajectoryProbe.sessions[1].prediction.x')
    page.mouse.move(*start); page.mouse.down(); page.mouse.move(*moved,steps=4); page.mouse.up()
    check('Dragging changes player-derived forecast', abs(page.evaluate('trajectoryProbe.sessions[1].prediction.x') - before) > 2)
    page.mouse.move(*moved); page.mouse.down(); page.mouse.move(*start,steps=4); page.mouse.up()
    page.locator('#test').click()
    check('s07 forecast verifies with actual third frame', page.evaluate('trajectoryProbe.sessions[1].result().withinTolerance'))
    page.locator('[data-epoch="0"]').click()
    page.locator('canvas').focus()
    page.keyboard.press('ArrowRight'); page.keyboard.press('Enter')
    check('Keyboard places a measured mark', page.evaluate('trajectoryProbe.sessions[1].marks[0].x === trajectoryProbe.state.cursor.x'))
    check('No runtime HTTP(S) request', not remote)
    check('No browser script error', not errors)
    narrow = browser.new_page(viewport={'width':390,'height':844}, has_touch=True, is_mobile=True)
    narrow.goto((HERE / 'index.html').as_uri()); narrow.wait_for_function('window.trajectoryProbe?.ready')
    narrow.locator('[data-epoch="0"]').click()
    b = narrow.locator('canvas').bounding_box()
    narrow.touchscreen.tap(b['x']+b['width']*.4,b['y']+b['height']*.6)
    check('Narrow touchscreen places mark', narrow.evaluate('trajectoryProbe.sessions[0].marks[0] !== null'))
    check('Narrow layout has no horizontal overflow', narrow.evaluate('document.documentElement.scrollWidth <= innerWidth'))
    narrow.screenshot(path=str(OUT / 'narrow-touch.png'), full_page=True)
    info = {'browser':'Chromium with existing workspace Playwright executable', 'url_scheme':'file',
            'phaser':'4.2.1', 'checks': checks, 'remote_requests':remote, 'page_errors':errors,
            'limits':'Mobile viewport/touch emulation; no physical iOS/Android test, no player test, no performance claim.'}
    (OUT / 'browser.json').write_text(json.dumps(info,ensure_ascii=False,indent=2))
    browser.close()
print(f'{len(checks)} browser checks passed; evidence at {OUT}')
