#!/usr/bin/env python3
"""A result image failure must preserve the last usable lesson and allow retry."""
import importlib.util
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get('GALAXY_RECOMPOSE_RESULT_IMAGE_EVIDENCE', HERE.parents[1] / 'docs/design-2026-10-09/evidence/recompose-result-image-loading.json'))


def helper(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def check_failure(page, scope, action):
    image = page.evaluate("scope => GALAXY_DATA.images.find(image => image.id === galaxyGame.model.protocol[scope + 'Ids'][0]).src", scope)
    pattern = '**/' + image
    before = page.evaluate('galaxyGame.model.serialize().state')
    stored = page.evaluate("sessionStorage.getItem('science-day.lesson.v1')")
    page.route(pattern, lambda route: route.abort())
    page.locator(f'[data-action="{action}"]').first.click()
    page.wait_for_selector('.modal')
    assert 'Не удалось загрузить снимок' in page.locator('.modal').inner_text()
    after = page.evaluate('galaxyGame.model.serialize().state')
    for key in ('phase', 'labels', 'architecture', 'current', 'baseline', 'cnnGuide', 'finalSeen'):
        assert before[key] == after[key], key
    assert page.evaluate("sessionStorage.getItem('science-day.lesson.v1')") == stored
    assert not page.locator('[data-core-retry]').count()
    page.locator('[data-action="close-modal"]').click()
    page.unroute(pattern)
    page.locator(f'[data-action="{action}"]').first.click()
    page.wait_for_selector('.final-room' if action == 'finish' else '.score-strip')
    page.locator('#experience-loading').wait_for(state='detached')
    assert not page.locator('.modal').count()
    page.wait_for_selector('.cnn-workbench__results img, .result-grid .result img', state='attached')
    page.wait_for_function("[...document.querySelectorAll('.cnn-workbench__results img, .result-grid .result img')].every(img => img.complete && img.naturalWidth > 0)")
    return {'scope': scope, 'statePreserved': True, 'storagePreserved': True, 'retry': 'PASS'}


def main():
    flow = helper('continuity', 'check-continuity-browser.py')
    browser_checks = helper('browser_checks', 'check-complete-browser.py')
    with browser_checks.local_http() as url, sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 720}, reduced_motion='reduce')
        page.goto(url)
        flow.wait_ready(page)
        data = flow.enter_labels(page)
        flow.label_children(page, data)
        checks = [check_failure(page, 'review', 'run')]
        flow.click(page, 'repair')
        flow.confirm_old(page, data)
        flow.click(page, 'run')
        flow.complete_guide(page)
        checks.append(check_failure(page, 'final', 'finish'))
        page.wait_for_function("galaxyGame.model.state.phase === 'final'")
        browser.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({'status': 'PASS', 'checks': checks}, indent=2) + '\n')
    print(OUT.read_text())


if __name__ == '__main__':
    main()
