#!/usr/bin/env python3
"""Exercise visible game controls, rendered images and the extracted offline ZIP."""
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / 'evidence'


def run(page, entry, capture=False, offline=True):
    errors, external = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    if offline:
        for scheme in ['http', 'https']:
            page.route(scheme + '://**/*', lambda route: (external.append(route.request.url), route.abort()))
    page.goto(entry)
    page.wait_for_function('window.galaxyGame && window.GALAXY_DATA && galaxyWorld.stats().frames > 0')
    data = page.evaluate('GALAXY_DATA')
    objects = {image['id']: image for image in data['images']}
    stages = []

    def action(name):
        page.locator(f'[data-action="{name}"]').first.click()
        if name == 'run':
            page.wait_for_function('!galaxyGame.busy && galaxyGame.model.state.phase === "results"')

    def state():
        return page.evaluate('galaxyGame.model.state')

    def choose(item_id, label):
        page.locator(f'[data-label-id="{item_id}"][data-label="{label}"]').click()

    def quest(stage_name, labels_before=None):
        scene = page.locator('.quest-scene')
        scene.evaluate("async el => { await Promise.all(el.closest('.station').getAnimations().map(a => a.finished)); }")
        assert scene.is_visible(), stage_name
        nika = scene.locator('.quest-scene__nika img')
        page.wait_for_function('(img) => img.complete && img.naturalWidth > 0', arg=nika.element_handle())
        assert nika.count() == 1 and nika.evaluate('(img) => img.complete && img.naturalWidth > 0'), stage_name
        assert nika.bounding_box()['height'] >= 290, stage_name
        photo_area = scene.locator('.quest-scene__photo-area').bounding_box()
        conversation = scene.locator('.quest-scene__conversation').bounding_box()
        assert photo_area and conversation and photo_area['y'] + photo_area['height'] <= conversation['y'] + 1, (stage_name, photo_area, conversation)
        observations = [scene.locator(f'[data-quest-observation="{name}"]') for name in ('arms', 'smooth', 'edge')]
        assert all(control.count() == 1 and control.is_visible() for control in observations), stage_name
        center = scene.locator('[data-quest="center"]')
        zoom = scene.locator('[data-quest="zoom"]')
        hint = scene.locator('[data-quest="hint"]')
        assert center.count() == zoom.count() == hint.count() == 1, stage_name
        if labels_before is not None:
            observations[0].click()
            hint.click()
            assert state()['labels'] == labels_before, stage_name
        # Point at the contained image, never in object-fit letterbox space.
        photo = scene.locator('[data-quest-photo]')
        page.wait_for_function('(img) => img.complete && img.naturalWidth > 0', arg=photo.element_handle())
        geometry = photo.evaluate("""img => {
          const r=img.getBoundingClientRect(), scale=Math.min(r.width/img.naturalWidth,r.height/img.naturalHeight);
          const width=img.naturalWidth*scale,height=img.naturalHeight*scale;
          return {left:r.left+(r.width-width)/2,top:r.top+(r.height-height)/2,width,height,elementLeft:r.left,elementTop:r.top};
        }""")
        click = {'x': geometry['left'] + geometry['width'] * .25, 'y': geometry['top'] + geometry['height'] * .4}
        page.mouse.click(click['x'], click['y'])
        page.wait_for_function('galaxyGame.quest && galaxyGame.quest.point')
        point = page.evaluate('galaxyGame.quest.point')
        assert abs(point['x'] - .25) < .02 and abs(point['y'] - .4) < .02, (stage_name, point)
        ring = scene.locator('.quest-scene__ring')
        assert ring.count() == 1, stage_name
        ring_box = ring.bounding_box()
        assert ring_box and abs(ring_box['x'] + ring_box['width'] / 2 - click['x']) < 3 and abs(ring_box['y'] + ring_box['height'] / 2 - click['y']) < 3, (stage_name, ring_box, click)
        # Crop zoom anchors at that exact contained-image pixel and can be returned.
        zoom.click()
        page.wait_for_function("""() => {
          const img=document.querySelector('.quest-scene [data-quest-photo]');
          return img && getComputedStyle(img).transform !== 'none';
        }""")
        zoomed = scene.locator('[data-quest-photo]')
        origin = zoomed.evaluate("img => getComputedStyle(img).transformOrigin")
        transform = zoomed.evaluate("img => getComputedStyle(img).transform")
        assert '2.15' in transform, (stage_name, transform)
        origin_xy = [float(value.replace('px', '')) for value in origin.split()[:2]]
        assert abs(origin_xy[0] - (geometry['left'] - geometry['elementLeft'] + geometry['width'] * .25)) < 3 and abs(origin_xy[1] - (geometry['top'] - geometry['elementTop'] + geometry['height'] * .4)) < 3, (stage_name, origin, geometry)
        scene.locator('[data-quest="zoom"]').click()
        page.wait_for_function("""() => {
          const img=document.querySelector('.quest-scene [data-quest-photo]');
          return img && getComputedStyle(img).transform === 'none';
        }""")
        # The centre control is also keyboard reachable; it intentionally moves to .5/.5.
        center = scene.locator('[data-quest="center"]')
        center.focus()
        assert center.evaluate('(el) => document.activeElement === el'), stage_name
        page.keyboard.press('Enter')
        page.wait_for_function("""() => galaxyGame.quest && galaxyGame.quest.point &&
          Math.abs(galaxyGame.quest.point.x - .5) < .001 && Math.abs(galaxyGame.quest.point.y - .5) < .001""")
        if labels_before is not None:
            assert state()['labels'] == labels_before, stage_name


    def stage(name):
        page.wait_for_function('Array.from(document.images).every(i => i.complete && i.naturalWidth > 0)')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), name
        assert page.evaluate('''Array.from(document.querySelectorAll('button')).every(b => {
          const r = b.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth + 1;
        })'''), name
        stages.append(name)
        if capture:
            page.screenshot(path=str(EVIDENCE / f'{page.viewport_size["width"]}-{name}.png'), full_page=True)

    def dialog(action_name):
        trigger = page.locator(f'[data-action="{action_name}"]').first
        trigger.click()
        assert page.locator('[role="dialog"]').is_visible()
        stage('dialog-' + action_name)
        assert page.evaluate('document.querySelector("#game").inert')
        page.keyboard.press('Shift+Tab')
        assert page.evaluate('document.activeElement.closest("[role=dialog]") !== null')
        page.keyboard.press('Escape')
        assert page.locator('[role="dialog"]').count() == 0
        assert not page.evaluate('document.querySelector("#game").inert')
        assert trigger.evaluate('(button) => document.activeElement === button')

    def collect_sky(item_id, drag=False):
        page.wait_for_selector('.sky-atlas')
        page.wait_for_function('galaxyGame.sky && galaxyGame.sky.snapshot().active')
        if not page.evaluate('(id)=>galaxyGame.sky.state().active===id', item_id):
            page.locator(f'.sky-atlas [data-target="{item_id}"]').click()
        if page.evaluate('!matchMedia("(prefers-reduced-motion: reduce)").matches'):
            page.wait_for_timeout(650)
        snap=page.evaluate('galaxyGame.sky.snapshot()')
        assert not snap['aligned']
        assert page.locator('.sky-atlas__open').is_disabled()
        assert page.evaluate('document.querySelector("#game").inert')
        page.keyboard.press('Tab')
        assert page.evaluate('document.activeElement.closest(".sky-atlas") !== null')
        if drag:
            page.mouse.move(snap['targetPixel']['x'],snap['targetPixel']['y'])
            page.mouse.down()
            page.mouse.move(snap['aim']['x'],snap['aim']['y'],steps=12)
            page.mouse.up()
        else:
            page.mouse.click(snap['targetPixel']['x'],snap['targetPixel']['y'])
        page.wait_for_function('galaxyGame.sky.state().aligned')
        stage('sky-' + item_id)
        page.locator('.sky-atlas__open').click()
        assert item_id in page.evaluate('galaxyGame.found')
        assert not page.evaluate('document.querySelector("#game").inert')

    assert state()['phase'] == 'intro'
    stage('intro')
    bounds = page.evaluate('galaxyWorld.stats().sceneBounds')
    assert bounds['x'] >= -1 and bounds['y'] >= -1, bounds
    assert bounds['x'] + bounds['width'] <= page.viewport_size['width'] + 1, bounds
    assert bounds['y'] + bounds['height'] <= page.viewport_size['height'] + 1, bounds
    assert page.locator('.brand').count() == 0
    assert page.evaluate("""()=>{const buttons=[...document.querySelectorAll('.welcome>button')].map(b=>b.getBoundingClientRect());return buttons.every((b,i)=>!i||b.top>=buttons[i-1].bottom+7)}""")
    assert page.locator('.mentor-portrait img').first.evaluate("img=>getComputedStyle(img).objectFit==='contain' && getComputedStyle(img).transform==='none'")
    action('sky')
    assert page.locator('.sky-atlas__panel.browse').is_visible()
    stage('sky-explore')
    marker = page.evaluate("""() => {
      const item=GALAXY_ARCHIVE.images.find(i=>i.id==='archive_m101');
      const c=galaxyGame.sky.state().camera,w=innerWidth,h=innerHeight;
      const aim=w>=701&&h<=500?[w*.72,h*.55]:w<700?[w*.55,h*.4]:[w/2,h/2];
      const delta=((item.ra-c.ra+180)%360+360)%360-180;
      return {x:aim[0]-delta*c.zoom,y:aim[1]-(item.dec-c.dec)*c.zoom};
    }""")
    page.mouse.click(marker['x'], marker['y'])
    page.wait_for_selector('.modal')
    assert page.locator('.modal h2').inner_text() == 'Messier 101'
    action('close-modal')
    research = page.locator('[data-research-id]').first
    if research.count():
        research.click()
        assert page.locator('.modal img').count() > 0
        assert page.locator('.sky-atlas').evaluate('(el)=>el.inert')
        stage('sky-discovery')
        action('close-modal')
        assert not page.locator('.sky-atlas').evaluate('(el)=>el.inert')
    page.locator('.sky-atlas__close').click()
    action('astronomy')
    assert page.locator('.library-card').count() >= 16
    page.locator('.library-card').first.click()
    stage('illustrated-discovery')
    action('talk')
    assert page.locator('.modal').evaluate('(el)=>el.inert')
    page.locator('[data-nika="story-ai"]').click()
    assert page.locator('.nika-dialogue__head img').get_attribute('data-mood') == 'thinking'
    stage('nika-story')
    page.keyboard.press('Escape')
    assert page.locator('.modal').count() == 1 and not page.locator('.modal').evaluate('(el)=>el.inert')
    action('close-modal')
    action('astronomy'); action('archive')
    assert page.locator('.library-card').count() >= 24
    stage('archive')
    page.locator('.library-card').first.click()
    assert page.locator('.modal img').count() > 0
    action('close-modal')
    dialog('about')
    dialog('astronomy')
    action('start')
    assert state()['phase'] == 'tutorial'
    before_quest_labels = state()['labels'].copy()
    quest('tutorial', before_quest_labels)
    assert page.locator('[data-action="labels"]').last.bounding_box()['y'] + page.locator('[data-action="labels"]').last.bounding_box()['height'] <= page.viewport_size['height']
    assert page.locator('.quest-scene [data-action="talk"]').count() == 0
    stage('tutorial')
    # Full-image viewer remains the footer action; crop zoom stays inline.
    tutorial_zoom = page.locator('.workbench > .station ~ .film-footer [data-action="zoom"], .workbench .film-footer [data-action="zoom"]').first
    assert tutorial_zoom.count() == 1
    dialog('zoom')
    assert state()['labels'] == before_quest_labels
    action('home'); action('start')
    assert state()['phase'] == 'tutorial'
    action('labels')
    collect_sky(data['childIds'][0],drag=True)
    assert state()['phase'] == 'labels'
    assert page.locator('[data-action="run"]').is_disabled()
    first_id = data['childIds'][0]
    before_class = state()['labels'].copy()
    quest('labels', before_class)
    run_box = page.locator('[data-action="run"]').bounding_box()
    assert run_box['y'] + run_box['height'] <= page.viewport_size['height'], ('labels', run_box)
    assert page.locator('.quest-scene [data-action="help"]').count() == 0
    # Only an explicit class button writes a label; pointing or hints must not.
    assert state()['labels'] == before_class
    target = page.locator(f'[data-label-id="{first_id}"][data-label="{objects[first_id]["label"]}"]')
    target.click()
    assert state()['labels'][first_id] == objects[first_id]['label']
    page.keyboard.press('1')
    assert state()['labels'][first_id] == data['classes'][0]['id']
    for index, item_id in enumerate(data['childIds']):
        choose(item_id, objects[item_id]['label'])
        stage('labels-' + str(index + 1))
        if index < len(data['childIds']) - 1:
            action('next')
            assert page.locator('.missing-photo').is_visible()
            page.locator('.missing-photo [data-action=sky]').click()
            collect_sky(data['childIds'][index+1])
    action('home'); action('resume')
    assert state()['phase'] == 'labels'
    assert all(state()['labels'][i] == objects[i]['label'] for i in data['childIds'])
    action('run')
    assert state()['phase'] == 'results'
    baseline = state()['current']
    assert page.locator('[data-action="finish"]').count() == 0
    stage('first-result')
    action('talk')
    page.locator('[data-nika="why"]').click()
    assert page.locator('.nika-dialogue__pair img').count() == 2
    assert objects[baseline['review']['predictions'][0]['neighborId']]['name'] in page.locator('.nika-dialogue').inner_text()
    stage('nika-reason')
    page.locator('[data-nika="change"]').click()
    page.locator('[data-nika="limits"]').click()
    page.keyboard.press('Escape')
    assert state()['current'] == baseline
    dialog('explain')
    old_trace = next((p for p in baseline['review']['predictions'] if p['neighborId'] in data['oldIds']), None)
    if old_trace:
        page.locator(f'[data-action="explain"][data-image-id="{old_trace["id"]}"]').click()
        action('inspect-old')
        assert page.locator(f'[data-label-id="{old_trace["neighborId"]}"]').count() == 3
    else:
        action('repair')
    assert state()['phase'] == 'repair'
    action('run')
    assert state()['current']['key'] == baseline['key']
    assert 'тот же опыт' in state()['notice']
    action('repair')
    assert state()['phase'] == 'repair'
    quest('repair', state()['labels'].copy())
    run_box = page.locator('[data-action="run"]').bounding_box()
    assert run_box['y'] + run_box['height'] <= page.viewport_size['height'], ('repair', run_box)
    for index, item_id in enumerate(data['oldIds']):
        choose(item_id, objects[item_id]['label'])
        if index < len(data['oldIds']) - 1:
            action('next')
    assert state()['current'] is None
    stage('repair')
    action('run')
    corrected = state()['current']
    assert state()['baseline']['key'] == baseline['key']
    stage('comparison')
    assert page.locator('.before-answer').count() == 3
    action('finish')
    assert state()['phase'] == 'final' and state()['finalSeen']
    stage('final')
    if page.locator('[data-action="cnn"]').count():
        action('cnn')
        assert page.locator('.cnn-model').count() == 1
        action('cnn-two')
        assert page.locator('.cnn-model').count() == 2
        action('cnn-one')
        assert page.locator('.cnn-model').count() == 1
        action('cnn-two')
        stage('cnn')
        action('close-cnn')
        assert state()['phase'] == 'final'
    action('home'); action('resume')
    assert state()['phase'] == 'final'
    action('labels')
    item_id = data['childIds'][0]
    other = next(c['id'] for c in data['classes'] if c['id'] != objects[item_id]['label'])
    choose(item_id, other)
    assert state()['current'] is None and state()['repairCheckedKey'] is None
    action('run')
    assert page.locator('[data-action="finish"]').count() == 0
    action('repair'); action('run'); action('finish')
    assert 'повторный просмотр' in state()['notice']
    action('home'); action('resume')
    assert 'повторный просмотр' in state()['notice']
    page.once('dialog', lambda dialog: dialog.accept())
    action('reset')
    assert set(page.evaluate('GALAXY_DATA.childIds')) != set(data['childIds'])
    assert page.evaluate('galaxyGame.found.length') == 0
    assert state()['phase'] == 'intro' and not state()['finalSeen'] and state()['baseline'] is None
    page.reload()
    page.wait_for_function('window.galaxyGame')
    assert state()['phase'] == 'intro'
    assert not errors, errors
    assert not external, external
    return {'first': baseline['review']['correct'], 'corrected': corrected['review']['correct'],
            'final': corrected['final']['correct'], 'total': corrected['review']['total'],
            'stages': stages, 'errors': errors, 'externalRequests': external}


def main():
    EVIDENCE.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, **({'executable_path': os.environ['PW_CHROMIUM']} if os.environ.get('PW_CHROMIUM') else {}))
        records = []
        for width, height in [(1920, 1080), (1440, 900), (1366, 768), (1280, 720)]:
            context = browser.new_context(viewport={'width': width, 'height': height}, reduced_motion='reduce')
            result = run(context.new_page(), (HERE / 'index.html').as_uri(), width == 1440)
            records.append({'viewport': [width, height], **result})
            context.close()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with zipfile.ZipFile(HERE / 'releases/galaxy-shift.zip') as archive:
                archive.extractall(root)
            manifest = json.loads((root / 'build.json').read_text())
            assert {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()} == set(manifest['files']) | {'build.json'}
            for name, digest in manifest['files'].items():
                assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name
            page = browser.new_page(viewport={'width': 1280, 'height': 720})
            run(page, (root / 'index.html').as_uri())
            page.close()
        browser.close()
    report = {'status': 'PASS', 'runs': records, 'offlineZip': 'verified exact resource set, hashes, images and full flow'}
    (EVIDENCE / 'browser.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
