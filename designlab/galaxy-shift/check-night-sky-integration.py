#!/usr/bin/env python3
"""N06 integration: real player route reaches the sky; every card opens its real modal."""
import importlib.util
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CHROMIUM = Path('/home/zhuckoff/.cache/ms-playwright/chromium-1234/chrome-linux/chrome')
TELEMETRY_CHECK = ROOT / 'tools' / 'galaxy-telemetry' / 'check-integration.py'
spec = importlib.util.spec_from_file_location('telemetry_integration', TELEMETRY_CHECK)
telemetry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(telemetry)


def close_modal(page):
    page.locator('.modal [data-action="close-modal"]').click()
    page.wait_for_selector('.modal', state='detached')


def open_one(page, expected_title, opened):
    page.wait_for_selector('.modal')
    assert page.locator('.modal h2').inner_text() == expected_title
    opened.add(expected_title)
    close_modal(page)


def open_all_visible(page, opened):
    """Use the rendered buttons and group choices, never a callback or dispatch."""
    notes = page.locator('.sky-atlas__note')
    for index in range(notes.count()):
        expected = notes.nth(index).locator('strong').inner_text()
        notes.nth(index).click()
        open_one(page, expected, opened)
    groups = page.locator('.sky-atlas__marker')
    for index in range(groups.count()):
        group = groups.nth(index)
        group.click()
        if page.locator('.modal').count():
            # A single material opens immediately.
            title = page.locator('.modal h2').inner_text()
            opened.add(title)
            close_modal(page)
            continue
        choice = page.locator('.sky-atlas__choice')
        assert choice.count() == 1
        choices = choice.locator('[data-choice]')
        for choice_index in range(choices.count()):
            expected = choices.nth(choice_index).inner_text()
            choices.nth(choice_index).click()
            open_one(page, expected, opened)
        choice.locator('.sky-atlas__choice-close').click()


def check_map(page, expected_titles):
    page.locator('.final-summary [data-action="sky"]').click()
    page.wait_for_selector('.sky-atlas')
    assert page.locator('[data-filter], [data-research-id], .sky-atlas__research-list').count() == 0
    assert page.locator('.sky-atlas__note').count() == 9
    ids = page.evaluate("""() => ({ expected:[...GALAXY_ARCHIVE.images,...GALAXY_DISCOVERIES].filter(item=>Number.isFinite(item.ra)&&Number.isFinite(item.dec)&&item.id !== 'btsbot-supernova').map(item=>item.id).sort(), actual:[...document.querySelectorAll('.sky-atlas__marker')].flatMap(node=>node.dataset.materialIds.split(',')).sort(), finite:[...document.querySelectorAll('.sky-atlas__marker')].every(node=>Number.isFinite(parseFloat(node.style.left))&&Number.isFinite(parseFloat(node.style.top))) })""")
    assert ids['actual'] == ids['expected'] and ids['finite'], ids
    overlaps = page.evaluate("""() => { const items=[...document.querySelectorAll('.sky-atlas__marker')].map(node=>({id:node.dataset.materialIds,r:node.getBoundingClientRect()})); return items.flatMap((a,index)=>items.slice(index+1).map(b=>({a:a.id,b:b.id,area:Math.max(0,Math.min(a.r.right,b.r.right)-Math.max(a.r.left,b.r.left))*Math.max(0,Math.min(a.r.bottom,b.r.bottom)-Math.max(a.r.top,b.r.top))}))).filter(item=>item.area); }""")
    assert not overlaps, {'overlaps': overlaps, 'markers': page.locator('.sky-atlas__marker').evaluate_all("nodes => nodes.map(n => ({id:n.dataset.materialIds, left:n.style.left, top:n.style.top, r:n.getBoundingClientRect().toJSON()}))")}
    before = page.evaluate('galaxyGame.sky.state().camera')
    first = page.locator('.sky-atlas__note').first
    title = first.locator('strong').inner_text()
    first.click(); open_one(page, title, set())
    assert page.evaluate('galaxyGame.sky.state().camera') == before, 'closing a card changed the camera'
    opened = {title}
    # The first note has already been tested for camera persistence.
    notes = page.locator('.sky-atlas__note')
    for index in range(1, notes.count()):
        expected = notes.nth(index).locator('strong').inner_text()
        notes.nth(index).click(); open_one(page, expected, opened)
    open_all_visible(page, opened)
    # BTSbot is outside the first whole-sky viewport. Pan using keyboard, then
    # click its newly rendered marker; no synthetic position is assigned.
    page.locator('.sky-atlas__canvas').click(position={'x': 640, 'y': 360})
    for _ in range(12): page.keyboard.press('ArrowUp')
    marker = page.locator('.sky-atlas__marker[data-material-ids*="btsbot-supernova"]')
    assert marker.count() == 1 and all(float(value.replace('px','')) == float(value.replace('px','')) for value in [marker.evaluate("node => node.style.left"), marker.evaluate("node => node.style.top")])
    marker.click()
    if page.locator('.modal').count():
        opened.add(page.locator('.modal h2').inner_text()); close_modal(page)
    else:
        choice = page.locator('.sky-atlas__choice')
        for index in range(choice.locator('[data-choice]').count()):
            expected = choice.locator('[data-choice]').nth(index).inner_text()
            choice.locator('[data-choice]').nth(index).click(); open_one(page, expected, opened)
        choice.locator('.sky-atlas__choice-close').click()
    assert opened == expected_titles, {'missing': sorted(expected_titles-opened), 'unexpected': sorted(opened-expected_titles)}
    return len(opened)


def check_layout(page, width, height, zoom):
    page.set_viewport_size({'width': width, 'height': height})
    page.goto((HERE / 'index.html').as_uri())
    page.wait_for_function('window.GalaxySky && window.GALAXY_DISCOVERIES')
    page.evaluate("zoom => { document.body.style.zoom = zoom; GalaxySky.open({onArchive:()=>{}, onDiscovery:()=>{}}); }", str(zoom))
    page.wait_for_selector('.sky-atlas')
    assert page.locator('.sky-atlas__note').count() == 9
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    # At 150%, every illustrated note retains a visible textual title.
    titles = page.locator('.sky-atlas__note strong')
    assert all(titles.nth(i).bounding_box()['height'] > 0 for i in range(titles.count()))
    note = page.locator('.sky-atlas__notes').bounding_box()
    marker_boxes = page.locator('.sky-atlas__marker').evaluate_all("nodes => nodes.map(node => ({id:node.dataset.materialIds,r:node.getBoundingClientRect().toJSON()}))")
    for index, first in enumerate(marker_boxes):
        for second in marker_boxes[index + 1:]:
            overlap = max(0, min(first['r']['right'], second['r']['right']) - max(first['r']['left'], second['r']['left'])) * max(0, min(first['r']['bottom'], second['r']['bottom']) - max(first['r']['top'], second['r']['top']))
            assert overlap == 0, {'first': first['id'], 'second': second['id'], 'overlap': overlap}
    for index in range(page.locator('.sky-atlas__marker').count()):
        marker = page.locator('.sky-atlas__marker').nth(index).bounding_box()
        overlap = max(0, min(marker['x'] + marker['width'], note['x'] + note['width']) - max(marker['x'], note['x'])) * max(0, min(marker['y'] + marker['height'], note['y'] + note['height']) - max(marker['y'], note['y']))
        assert overlap == 0, {'marker': marker, 'notes': note, 'overlap': overlap}


def main():
    launch = {'headless': True, 'executable_path': str(CHROMIUM)} if CHROMIUM.exists() else {'headless': True}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch)
        context = browser.new_context(viewport={'width': 1280, 'height': 720}, reduced_motion='reduce')
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto((HERE / 'index.html').as_uri())
        page.wait_for_function('window.galaxyGame && window.GalaxySky')
        data = telemetry.journey(page)
        expected = set(page.evaluate("""() => [
          ...GALAXY_DISCOVERIES.map(item => item.title),
          ...GALAXY_ARCHIVE.images.map(item => item.name)
        ]"""))
        assert len(expected) == 43, expected
        opened = check_map(page, expected)
        assert not errors, errors
        context.close()
        for width, height, zoom in ((1280,720,1), (1366,768,1), (1440,900,1), (1920,1080,1), (1280,720,1.5)):
            context = browser.new_context(viewport={'width': width, 'height': height}, reduced_motion='reduce')
            check_layout(context.new_page(), width, height, zoom)
            context.close()
        browser.close()
    print({'status': 'PASS', 'route': 'visible start-to-final-to-sky', 'openedRealModals': opened, 'viewports': 4, 'zoom': '150%'})

if __name__ == '__main__':
    main()
