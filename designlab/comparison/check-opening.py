#!/usr/bin/env python3
"""Test the playable first exposure, truthful transfer, input and timer lifecycle."""
from pathlib import Path
import json
import os
import sys
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ENTRY = sys.argv[1] if len(sys.argv) > 1 else (HERE / 'index.html').as_uri()
OUT = HERE / 'evidence'
OUT.mkdir(exist_ok=True)
checks, errors = [], []


def check(name, condition):
    assert condition, name
    checks.append(name)


def launch(playwright):
    executable = os.environ.get('PW_CHROMIUM')
    if not executable:
        candidates = sorted((Path.home() / '.cache/ms-playwright').glob('chromium-*/chrome-linux/chrome'))
        executable = str(candidates[-1]) if candidates else None
    options = {'headless': True}
    if executable:
        options['executable_path'] = executable
    return playwright.chromium.launch(**options)


with sync_playwright() as playwright:
    browser = launch(playwright)
    page = browser.new_page(viewport={'width': 1440, 'height': 1050}, reduced_motion='reduce')
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(ENTRY)
    page.wait_for_function('window.journey && window.opening && window.comparisonProbe')

    def snap(name):
        page.screenshot(path=str(OUT / ('opening-' + name + '.png')), full_page=True)

    def click_point(x, y):
        canvas = page.locator('#opening-sky')
        canvas.scroll_into_view_if_needed()
        box = canvas.bounding_box()
        page.mouse.click(box['x'] + (x + .5) / 128 * box['width'],
                         box['y'] + (y + .5) / 128 * box['height'])

    def wait_result(outcome):
        page.wait_for_function('comparisonProbe.state.phase === "result"')
        check('computed opening outcome ' + outcome,
              page.evaluate('comparisonProbe.state.result.outcome') == outcome)

    def reset():
        page.evaluate('journey.reset()')
        page.wait_for_function('journey.state.view === "opening" && opening.state.active')

    def source_button(x):
        number = page.evaluate('(x)=>COMPARISON_DATA.cases[0].sources[1].findIndex(p=>p.x===x)+1', x)
        return page.locator('#opening-points button').nth(number - 1)

    def raw_frame_matches(epoch):
        return page.evaluate('''epoch=>{
            const d=COMPARISON_DATA.cases[0],s=epoch===0?{...d,arrays:[d.arrays[0],d.arrays[0]]}:d;
            const raw=document.createElement('canvas');raw.width=raw.height=128;
            raw.getContext('2d').putImageData(new ImageData(ComparisonModel.render(s,0,epoch||1).pixels,128,128),0,0);
            const expected=document.createElement('canvas');expected.width=expected.height=640;
            expected.getContext('2d').drawImage(raw,0,0,640,640);
            return expected.toDataURL()===document.getElementById('opening-sky').toDataURL();
        }''', epoch)

    check('default starts in actual playable sky without hub step',
          page.locator('#opening').is_visible() and page.locator('#overview').is_hidden()
          and page.locator('#opening-sky').is_visible() and page.evaluate('journey.state.view === "opening"'))
    check('reduced motion starts with static later exposure',
          page.evaluate('opening.state.epoch === 1 && !opening.state.playing'))
    check('default sky renders second real frame with no third exposure', raw_frame_matches(1))
    check('no action or earned movement before selection',
          page.locator('#opening-action').is_hidden() and page.evaluate('comparisonProbe.state.selection === null && comparisonProbe.state.journal.length === 0'))
    snap('entry')
    click_point(100, 100)
    check('empty sky does not create target or action',
          page.evaluate('comparisonProbe.state.selection === null') and page.locator('#opening-action').is_hidden()
          and 'нет' in page.locator('#opening-feedback').inner_text())
    page.locator('#opening-earlier').click()
    check('manual earlier control shows first real frame', page.evaluate('opening.state.epoch === 0') and raw_frame_matches(0))
    page.locator('#opening-later').click()
    check('manual later control restores second real frame', page.evaluate('opening.state.epoch === 1') and raw_frame_matches(1))
    click_point(71, 10)
    check('wrong stationary point remains a selectable scientific test',
          page.evaluate('comparisonProbe.state.selection.point.x === 71') and page.locator('#opening-action').is_visible())
    snap('selected')
    page.locator('#opening-action').click()
    wait_result('stationary')
    check('wrong result reveals real third frame without awarding movement',
          page.evaluate('opening.state.epoch === 2 && comparisonProbe.state.journal.length === 0')
          and 'осталась' in page.locator('#opening-feedback').inner_text())
    earlier_attempt = page.evaluate('JSON.stringify(comparisonProbe.state.attempts[0])')
    page.locator('#opening-action').click()
    check('retry returns to two-exposure choice and keeps first attempt',
          page.evaluate('comparisonProbe.state.phase === "search" && comparisonProbe.state.selection === null && opening.state.epoch === 1')
          and page.evaluate('JSON.stringify(comparisonProbe.state.attempts[0])') == earlier_attempt)
    page.locator('#opening-earlier').click()
    origin = page.evaluate('TrackingModel.select(COMPARISON_DATA.cases[0],58,68).origin')
    click_point(origin['x'], origin['y'])
    check('earlier-frame click transfers unambiguous first-to-second match',
          page.evaluate('comparisonProbe.state.selection.point.x === 58 && comparisonProbe.state.selection.point.y === 68 && opening.state.epoch === 1'))
    check('selection does not reveal third exposure',
          page.evaluate('comparisonProbe.state.result === null && opening.state.epoch < 2'))
    page.emulate_media(reduced_motion='no-preference')
    page.locator('#opening-action').click()
    check('checking keeps third hidden and locks comparison controls',
          page.evaluate('comparisonProbe.state.phase === "checking" && opening.state.epoch === 1')
          and all(page.locator('#' + target).is_disabled() for target in ['opening-earlier', 'opening-later', 'opening-play']))
    wait_result('moving')
    check('moving result saves exactly one personal track',
          page.evaluate('comparisonProbe.state.journal.length === 1 && comparisonProbe.state.journal[0].caseId === "s02" && opening.state.epoch === 2'))
    check('failed attempt and post-reveal status are preserved',
          page.evaluate('comparisonProbe.state.attempts.length === 2 && !comparisonProbe.state.attempts[1].firstLook')
          and page.evaluate('JSON.stringify(comparisonProbe.state.attempts[0])') == earlier_attempt)
    check('opening outcome matches shared scientific tracking engine',
          page.evaluate('JSON.stringify(comparisonProbe.state.result) === JSON.stringify(TrackingModel.confirm(COMPARISON_DATA.cases[0],comparisonProbe.state.selection))'))
    snap('caught')
    result_before = page.evaluate('JSON.stringify(comparisonProbe.state)')
    page.locator('#opening-action').click()
    check('continue opens assembly without making another attempt',
          page.locator('#overview').is_visible() and page.evaluate('JSON.stringify(comparisonProbe.state)') == result_before)
    check('hub offers installation immediately rather than another motion test',
          'Установить поиск движения' in page.locator('#shift-action').inner_text())
    page.locator('#shift-action').click()
    check('installation uses earned opening result',
          page.evaluate('journey.state.installed.movement && comparisonProbe.state.journal.length === 1 && comparisonProbe.state.attempts.length === 2'))
    page.locator('#episode-directory summary').click()
    page.locator('#overview-tracking-story').click()
    check('opening-earned track retains actual asteroid history',
          page.locator('#tracking-story').is_visible() and 'Amosov' in page.locator('#tracking-story-title').inner_text())
    page.locator('#nav-overview').click()
    page.locator('#journey-reset').click()
    check('new shift resets directly to opening with cleared scientific state',
          page.locator('#opening').is_visible() and page.evaluate('comparisonProbe.state.attempts.length === 0 && comparisonProbe.state.journal.length === 0 && !journey.state.installed.movement'))

    # Automatic display rotates first/second only and stops on exit or a preference change.
    check('normal-motion fresh opening starts automatic comparison', page.evaluate('opening.state.playing'))
    epoch_before = page.evaluate('opening.state.epoch')
    page.wait_for_timeout(1450)
    check('automatic comparison switches only first two frames',
          page.evaluate('opening.state.epoch') != epoch_before and page.evaluate('opening.state.epoch < 2'))
    page.locator('#opening-play').click()
    check('pause control stops automatic comparison', not page.evaluate('opening.state.playing'))
    epoch_before = page.evaluate('opening.state.epoch')
    page.wait_for_timeout(1450)
    check('paused exposure remains unchanged', page.evaluate('opening.state.epoch') == epoch_before)
    page.locator('#opening-play').click()
    check('play control restarts comparison', page.evaluate('opening.state.playing'))
    page.emulate_media(reduced_motion='reduce')
    page.wait_for_function('!opening.state.playing')
    check('reduced motion change stops active comparison', not page.evaluate('opening.state.playing'))
    plain = page.locator('#opening-sky').evaluate('(canvas)=>canvas.toDataURL()')
    pixels_before_helper = page.evaluate('JSON.stringify(COMPARISON_DATA.cases[0].arrays)')
    page.locator('.opening-tools summary').click()
    page.wait_for_function('(previous)=>document.getElementById("opening-sky").toDataURL() !== previous', arg=plain)
    check('number overlay alters displayed preview without changing science data',
          plain != page.locator('#opening-sky').evaluate('(canvas)=>canvas.toDataURL()')
          and page.evaluate('JSON.stringify(COMPARISON_DATA.cases[0].arrays)') == pixels_before_helper)
    check('numeric helper exposes real source buttons',
          page.locator('#opening-points button').count() == page.evaluate('COMPARISON_DATA.cases[0].sources[1].length'))
    source_button(58).focus()
    page.keyboard.press('Enter')
    check('keyboard numeric helper selects measured target',
          page.evaluate('comparisonProbe.state.selection.point.x === 58 && !opening.state.playing'))
    attempts_before_empty = page.evaluate('comparisonProbe.state.attempts.length')
    page.locator('#opening-earlier').click()
    click_point(100, 100)
    check('unsupported earlier-frame click clears previous actionable selection',
          page.evaluate('comparisonProbe.state.selection === null') and page.locator('#opening-action').is_hidden()
          and page.evaluate('comparisonProbe.state.attempts.length') == attempts_before_empty)

    # Skip and reset both invalidate a pending third-frame check.
    page.emulate_media(reduced_motion='no-preference')
    source_button(58).click()
    page.locator('#opening-action').click()
    page.locator('#opening-skip').click()
    page.wait_for_timeout(1000)
    check('skip cancels pending third-frame check and display timer',
          page.evaluate('!opening.state.active && !opening.state.playing && comparisonProbe.state.phase === "search" && comparisonProbe.state.attempts.length === 0'))
    check('skip preserves legitimate target without inventing result',
          page.evaluate('comparisonProbe.state.selection.point.x === 58 && comparisonProbe.state.result === null'))
    page.locator('#nav-tracking').click()
    check('old instrument route preserves skipped opening target', page.evaluate('comparisonProbe.state.selection.point.x === 58'))
    reset()
    click_point(58, 68)
    page.locator('#opening-action').click()
    reset()
    page.wait_for_timeout(1000)
    check('reset invalidates pending check and earned result',
          page.evaluate('comparisonProbe.state.phase === "search" && comparisonProbe.state.attempts.length === 0 && comparisonProbe.state.selection === null && comparisonProbe.state.journal.length === 0'))
    page.locator('#opening-skip').click()
    hidden_epoch = page.evaluate('opening.state.epoch')
    page.wait_for_timeout(1450)
    check('hidden opening stops playing and cannot advance exposure',
          page.evaluate('!opening.state.active && !opening.state.playing') and page.evaluate('opening.state.epoch') == hidden_epoch)

    page.emulate_media(reduced_motion='reduce')
    reset()
    page.set_viewport_size({'width': 390, 'height': 844})
    check('phone opening has no horizontal overflow', page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
    check('real sky is visible within initial phone viewport',
          page.locator('#opening-sky').evaluate('(canvas)=>{const r=canvas.getBoundingClientRect();return r.top>=0 && r.bottom<=innerHeight;}'))
    page.locator('#opening-later').click()
    click_point(58, 68)
    check('phone direct science click selects target', page.evaluate('comparisonProbe.state.selection.point.x === 58'))
    page.evaluate('window.scrollTo(0,0)')
    check('phone selected action fits 844-pixel viewport without scrolling',
          page.locator('#opening-action').evaluate('(button)=>{const r=button.getBoundingClientRect();return r.top>=0 && r.bottom<=innerHeight && r.right<=innerWidth;}'))
    snap('mobile')
    page.locator('#opening-action').focus()
    page.keyboard.press('Enter')
    wait_result('moving')
    check('phone keyboard action earns same single track', page.evaluate('comparisonProbe.state.journal.length === 1'))
    check('opening does not present fixed rules as trained ML', 'ИИ' not in page.locator('#opening-feedback').inner_text())
    check('no runtime errors', not errors)
    browser.close()

report = {'count': len(checks), 'checks': checks, 'engine': 'chromium', 'entry': ENTRY, 'errors': errors}
(OUT / 'opening-browser.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False, indent=2))
