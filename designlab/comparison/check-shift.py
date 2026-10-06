#!/usr/bin/env python3
"""Replay the assembled observatory through DOM input and inspect scientific outputs."""
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
    page.wait_for_function('window.journey && window.launchEpisode && document.querySelector("#game canvas")')

    def snap(name):
        page.screenshot(path=str(OUT / ('shift-' + name + '.png')), full_page=True)

    def nav(route):
        page.locator('#nav-' + route).click()

    def scan():
        page.locator('#launch-run').click()
        page.wait_for_function('launchEpisode.state.phase === "result" && launchEpisode.state.scan')

    def mode(value):
        page.locator('input[name="launch-mode"][value="' + value + '"]').check()

    def field(value):
        page.locator('#launch-field').select_option(value)

    def canvas_point(canvas, x, y):
        canvas.scroll_into_view_if_needed()
        box = canvas.bounding_box()
        page.mouse.click(box['x'] + (x + .5) / 128 * box['width'],
                         box['y'] + (y + .5) / 128 * box['height'])

    def prepare_tools():
        page.locator('#shift-action').click()
        page.locator('#opening-later').click()
        canvas_point(page.locator('#opening-sky'), 58, 68)
        check('real bench canvas selects measured target',
              page.evaluate('comparisonProbe.state.selection.point.x === 58'))
        page.locator('#opening-action').click()
        page.wait_for_function('comparisonProbe.state.phase === "result"')
        check('one personal track earns movement tool without using launch field',
              page.evaluate('comparisonProbe.state.result.outcome === "moving" && comparisonProbe.state.journal.length === 1 && comparisonProbe.state.journal[0].caseId === "s02"'))
        page.locator('#opening-action').click()
        check('test outcome returns to installation',
              page.locator('#overview').is_visible() and not page.evaluate('journey.state.installed.movement'))
        page.locator('#shift-action').click()
        check('movement installation changes actual observatory state',
              page.evaluate('journey.state.installed.movement && !journey.state.installed.fading')
              and page.locator('#bench-motion').get_attribute('data-status') == 'installed')
        page.locator('#shift-action').click()
        canvas_point(page.locator('#brightness-first'), 65, 64)
        page.locator('#brightness-measure').click()
        page.wait_for_function('brightnessEpisode.state.phase === "result"')
        check('personal light test measures real fading',
              page.evaluate('brightnessEpisode.state.result.outcome === "faded"')
              and page.locator('#brightness-value-second').inner_text() == '34')
        page.locator('#brightness-to-overview').click()
        check('passing light test does not silently install tool',
              not page.evaluate('journey.state.installed.fading'))
        page.locator('#shift-action').click()
        check('both installations unlock independent launch',
              page.evaluate('journey.ready()')
              and page.locator('#bench-light').get_attribute('data-status') == 'installed')

    check('default entry offers actual observations before installing tools',page.locator('#bench-start').is_visible() and page.locator('#opening').is_hidden())
    check('entry presents partner and one next action',
          page.locator('#overview').is_visible() and page.locator('#nika-line').is_visible()
          and not page.locator('#episode-directory').evaluate('(node)=>node.open'))
    check('tools initially uninstalled and no completed shift',
          page.evaluate('!journey.ready() && !journey.state.finished && launchEpisode.state.records.length === 0'))
    snap('entry')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.evaluate('window.scrollTo(0, 0)')
    check('first mobile action fits initial viewport without scrolling',
          page.locator('#bench-start').evaluate('(button)=>{const rect=button.getBoundingClientRect();return rect.top>=0 && rect.bottom<=innerHeight && rect.left>=0 && rect.right<=innerWidth;}'))
    snap('entry-mobile')
    page.set_viewport_size({'width': 1440, 'height': 1050})
    nav('launch')
    check('launch visibly locked before earned installations',
          page.locator('#launch-locked').is_visible() and page.locator('#launch-workspace').is_hidden())
    nav('overview')
    prepare_tools()
    snap('installed')
    page.locator('#shift-action').click()
    check('assembled observatory opens independent scan',
          page.locator('#launch-workspace').is_visible() and page.evaluate('launchEpisode.state.active'))
    check('independent fields exclude personal training images',
          page.evaluate('LAUNCH_DATA.cases.every(c=>!COMPARISON_DATA.cases.slice(0,1).some(t=>JSON.stringify(c.dates)===JSON.stringify(t.dates)) && !BRIGHTNESS_DATA.dates.every((d,i)=>c.dates[i]===d))'))

    # Same actual field, different real methods; an empty scan remains research.
    field('launch-variable')
    mode('movement')
    scan()
    check('motion scan in light field has no manufactured candidate',
          page.evaluate('launchEpisode.state.scan.candidates.length === 0 && launchEpisode.state.result === null')
          and page.locator('#launch-empty').is_visible())
    check('empty result cannot show completed verification', page.locator('#launch-evidence').is_hidden())
    page.locator('#launch-save-empty').click()
    check('empty scan is recorded honestly without confirmation',
          page.evaluate('launchEpisode.state.records.length === 1 && launchEpisode.state.records[0].result === null'))
    check('one investigated field cannot finish shift', page.locator('#launch-finish').is_hidden())
    page.locator('#launch-switch-mode').click()
    check('empty result switches method and returns keyboard focus to launch',
          page.evaluate('launchEpisode.state.mode === "fading" && document.activeElement.id === "launch-run"'))
    check('method change clears stale scan and selected result',
          page.evaluate('launchEpisode.state.scan === null && launchEpisode.state.selected === null && launchEpisode.state.result === null'))
    scan()
    check('complementary method finds actual light proposal on same field',
          page.evaluate('launchEpisode.state.scan.candidates.length === 1 && launchEpisode.state.scan.inspectedCount > 1'))
    snap('scan')
    page.locator('#launch-candidates button').first.focus()
    page.keyboard.press('Enter')
    check('keyboard proposal opens computed fading verification',
          page.evaluate('launchEpisode.state.result.outcome === "faded"') and page.locator('#launch-evidence').is_visible())
    check('third light date correctly names rebrightening',
          page.evaluate('launchEpisode.state.result.thirdOutcome === "rebrightened" && launchEpisode.state.result.sustainedFade === false')
          and 'снова ярче' in page.locator('#launch-evidence-heading').inner_text()
          and len(page.locator('#launch-evidence-frames figure').all()) == 3)
    check('repeated two-frame measurement is not sold as independent confirmation',
          page.evaluate('launchEpisode.state.result.independentConfirmation === false')
          and 'не является независимой' in page.locator('#launch-evidence-detail').inner_text())
    page.locator('#launch-save').click()
    check('saved verification disables duplicate action', page.locator('#launch-save').is_disabled())
    page.evaluate('launchEpisode.save()')
    check('duplicate save guard retains exactly two records', page.evaluate('launchEpisode.state.records.length === 2'))
    check('two methods on one field do not inflate field completion',
          page.locator('#launch-log-count').inner_text() == '1 / 2 участка' and page.locator('#launch-finish').is_hidden())
    snap('result')
    records_before_next = page.evaluate('JSON.stringify(launchEpisode.state.records)')
    page.locator('#launch-next-field').click()
    check('next field preserves selected method and exact saved records',
          page.evaluate('launchEpisode.state.caseId === "launch-motion" && launchEpisode.state.mode === "fading"')
          and page.evaluate('JSON.stringify(launchEpisode.state.records)') == records_before_next)
    check('next field returns keyboard focus to launch action',
          page.evaluate('document.activeElement.id === "launch-run"'))
    check('field change clears stale light selection',
          page.evaluate('launchEpisode.state.selected === null && launchEpisode.state.result === null && launchEpisode.state.scan === null')
          and page.locator('#launch-evidence').is_hidden())
    mode('movement')
    scan()
    check('other field yields independent moving-source proposal',
          page.evaluate('launchEpisode.state.scan.candidates.length === 1 && launchEpisode.state.scan.candidates[0].point.x === 59'))
    page.locator('#launch-candidates button').first.click()
    check('third actual image verifies independently selected mover',
          page.evaluate('launchEpisode.state.result.outcome === "moving" && launchEpisode.state.result.distancePx > 0'))
    check('known asteroid appears only after verified observation',
          page.locator('#launch-history').is_visible() and 'Gianni' in page.locator('#launch-history').inner_text())
    page.locator('#launch-save').click()
    check('two researched fields offer ending driven by records',
          page.locator('#launch-finish').is_visible() and page.locator('#launch-log-count').inner_text() == '2 / 2 участка')
    count = page.evaluate('launchEpisode.state.records.length')
    page.locator('#launch-log-list button').nth(1).click()
    check('saved reopening restores specific measurement without new record',
          page.evaluate('launchEpisode.state.caseId === "launch-variable" && launchEpisode.state.result.thirdOutcome === "rebrightened"')
          and page.evaluate('launchEpisode.state.records.length') == count)
    page.locator('#launch-finish').click()
    check('ending returns to observatory with honest record counters',
          page.evaluate('journey.state.finished') and page.locator('#journey-finished').is_visible()
          and 'Сохранено проверок: 3' in page.locator('#shift-summary').inner_text()
          and 'Подтверждённых изменений: 2' in page.locator('#shift-summary').inner_text())
    snap('ending')

    page.set_viewport_size({'width': 390, 'height': 844})
    for route in ['overview', 'tracking', 'brightness', 'launch']:
        nav(route)
        check(route + ' has no horizontal overflow at 390 pixels',
              page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
    snap('mobile')
    page.locator('input[value="movement"]').focus()
    page.keyboard.press('Space')
    check('keyboard radio chooses actual search method', page.evaluate('launchEpisode.state.mode === "movement"'))
    page.locator('#launch-field').focus()
    page.keyboard.press('Home')
    page.keyboard.press('Enter')
    check('keyboard selects independent field', page.evaluate('launchEpisode.state.caseId === "launch-motion"'))
    page.set_viewport_size({'width': 1440, 'height': 1050})
    page.emulate_media(reduced_motion='no-preference')
    page.locator('#launch-run').click()
    check('animated scan locks field and mode controls',
          page.locator('#launch-field').is_disabled() and page.locator('input[value="fading"]').is_disabled())
    nav('overview')
    page.wait_for_timeout(1050)
    check('leaving cancels scan and retains existing records',
          page.evaluate('launchEpisode.state.phase === "idle" && launchEpisode.state.scan === null && !launchEpisode.state.active')
          and page.evaluate('launchEpisode.state.records.length') == count)
    nav('launch')
    page.locator('#launch-run').click()
    page.evaluate('journey.reset()')
    page.wait_for_timeout(1050)
    check('reset cancels pending scan and clears whole shift',
          page.evaluate('launchEpisode.state.records.length === 0 && launchEpisode.state.scan === null && launchEpisode.state.selected === null && !journey.ready() && !journey.state.finished && comparisonProbe.state.journal.length === 0 && !brightnessEpisode.state.earned'))
    check('reset returns to cleared workbench',page.locator('#bench-desk').is_visible() and page.locator('#opening').is_hidden())
    check('reset restores uninstalled stage and hides ending',
          page.locator('#bench-motion').get_attribute('data-status') == 'pending'
          and page.locator('#journey-finished').is_hidden())

    # A complete research shift with no confirmed change must remain possible.
    page.emulate_media(reduced_motion='reduce')
    prepare_tools()
    page.locator('#shift-action').click()
    field('launch-variable')
    mode('movement')
    scan()
    page.locator('#launch-save-empty').click()
    field('launch-motion')
    mode('fading')
    scan()
    check('unstable photometric controls are distinguished from no change',
          page.evaluate('launchEpisode.state.scan.reason === "insufficient_stable_field_controls"')
          and 'не может надёжно' in page.locator('#launch-empty p').inner_text())
    page.locator('#launch-save-empty').click()
    page.locator('#launch-finish').click()
    check('zero-confirmation ending is honest and complete',
          page.evaluate('journey.state.finished && launchEpisode.state.records.every(r=>r.result === null)')
          and 'Подтверждённых изменений: 0' in page.locator('#shift-summary').inner_text())
    check('fixed-rule search is not presented as trained ML',
          'не обучается' in page.locator('#launch-episode footer').inner_text())
    check('no runtime errors', not errors)
    browser.close()

report = {'count': len(checks), 'checks': checks, 'engine': 'chromium', 'entry': ENTRY, 'errors': errors}
(OUT / 'shift-browser.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False, indent=2))
