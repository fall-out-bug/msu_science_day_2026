#!/usr/bin/env python3
"""N08 regression: CNN editor updates retain the visible work surface without a fade-out."""
import json
import importlib.util
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get('GALAXY_RECOMPOSE_FLICKER_DIR', os.environ.get('GALAXY_N08_EVIDENCE', HERE / '../../docs/design-2026-10-09/evidence'))).resolve()


def ready_editor(page):
    if page.url != 'about:blank':
        # A second visible shift reuses the browser cache without injected state.
        page.locator('[data-action="home"]').click()
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('[data-action="reset"]').click()
    page.goto((HERE / 'index.html').as_uri())
    page.wait_for_function('window.galaxyGame && window.GALAXY_DATA')
    spec = importlib.util.spec_from_file_location('continuity', HERE / 'check-continuity-browser.py')
    flow = importlib.util.module_from_spec(spec); spec.loader.exec_module(flow)
    flow.prepare_editor(page)
    page.wait_for_selector('.architecture-editor')


def sample(page, name, action, *, changes_architecture=True, keeps_surface=True):
    page.evaluate("""name => {
      const root=document.querySelector('#game'), station=document.querySelector('.station'), editor=document.querySelector('.architecture-editor'), workbench=document.querySelector('.cnn-workbench'), photo=document.querySelector('[data-action="cnn-image"]');
      window.__n08={name, root, station, editor, workbench, photo, photoBox:photo?.getBoundingClientRect().toJSON(), editorBox:editor?.getBoundingClientRect().toJSON(), scrollY, architecture:galaxyGame.model.state.architecture}; window.__n08frames=[]; window.__n08active=true;
      const take=()=>{ const current=document.querySelector('.station'); window.__n08frames.push({t:performance.now(),opacity:current?Number(getComputedStyle(current).opacity):null,transform:current?getComputedStyle(current).transform:null,visible:!!current && current.getBoundingClientRect().height>0,imagesReady:[...document.querySelectorAll('.cnn-workbench__results img, .result-grid .result img')].every(img=>img.complete&&img.naturalWidth>0)}); if(window.__n08active) requestAnimationFrame(take); }; take();
    }""", name)
    action()
    page.wait_for_timeout(550)
    page.evaluate('window.__n08active=false')
    record = page.evaluate("""() => ({
      name:__n08.name, sameRoot:__n08.root===document.querySelector('#game'), sameStation:__n08.station===document.querySelector('.station'),
      sameEditor:__n08.editor===document.querySelector('.architecture-editor'), samePhotoBox:JSON.stringify(__n08.photoBox)===JSON.stringify(document.querySelector('[data-action="cnn-image"]')?.getBoundingClientRect().toJSON()), sameEditorBox:JSON.stringify(__n08.editorBox)===JSON.stringify(document.querySelector('.architecture-editor')?.getBoundingClientRect().toJSON()), sameEditorFrame:(() => { const next=document.querySelector('.architecture-editor')?.getBoundingClientRect().toJSON(), before=__n08.editorBox; return !!next && !!before && next.x===before.x && next.y===before.y && next.width===before.width; })(), sameWorkbench:__n08.workbench===document.querySelector('.cnn-workbench'), samePhoto:__n08.photo===document.querySelector('[data-action="cnn-image"]'), sameScroll:Math.abs(__n08.scrollY-scrollY)<2,
      minOpacity:Math.min(...__n08frames.map(x=>x.opacity ?? 0)), noBlankFrames:__n08frames.every(x=>x.visible&&x.imagesReady), frames:__n08frames, beforeArchitecture:__n08.architecture, architecture:galaxyGame.model.state.architecture, focus:document.activeElement?.getAttribute('data-action') || document.activeElement?.tagName
    })""")
    assert record['minOpacity'] >= .99 and record['noBlankFrames'], record
    if keeps_surface:
        assert record['sameRoot'] and record['sameStation'] and record['sameWorkbench'] and record['sameEditor'] and record['samePhoto'] and record['samePhotoBox'] and record['sameEditorFrame'] and record['sameScroll'] and (changes_architecture or record['sameEditorBox']), record
    if changes_architecture:
        assert record['architecture'] != record['beforeArchitecture'], record
    assert record['focus'] != 'BODY', record
    return record


def suite(page, reduced):
    ready_editor(page)
    report=[]
    depth = page.locator('[data-action="architecture-depth"][data-depth="2"]'); depth.scroll_into_view_if_needed()
    page.locator('[data-action="architecture-depth"][data-depth="1"]').click()
    depth = page.locator('[data-action="architecture-depth"][data-depth="2"]'); depth.scroll_into_view_if_needed()
    report.append(sample(page, 'depth-1-to-2', lambda: depth.click()))
    add_bn = page.locator('[data-action="layer-add"][data-layer="bn"]'); add_bn.scroll_into_view_if_needed()
    report.append(sample(page, 'add-bn', lambda: add_bn.click()))
    report.append(sample(page, 'add-dropout', lambda: page.locator('[data-action="layer-add"][data-layer="d"]').click()))
    report.append(sample(page, 'reorder-button', lambda: page.locator('li[data-layer="bn"] [data-action="layer-later"]').click()))
    layer = page.locator('li[data-layer="d"]'); layer.focus()
    report.append(sample(page, 'reorder-keyboard', lambda: page.keyboard.press('Alt+ArrowLeft')))
    report.append(sample(page, 'remove-dropout', lambda: page.locator('[data-action="layer-remove"][data-layer="d"]').click()))
    help_button = page.locator('[data-action="layer-info"]').first
    help_button.scroll_into_view_if_needed()
    def help_roundtrip():
        help_button.click(); page.wait_for_selector('.modal'); page.keyboard.press('Escape')
        assert help_button.evaluate('button => button === document.activeElement')
    report.append(sample(page, 'layer-help', help_roundtrip, changes_architecture=False))
    # Drag sends the same public drag route as a mouse user.
    source=page.locator('li[data-layer="bn"]'); target=page.locator('li[data-layer="r"]')
    report.append(sample(page, 'reorder-drag', lambda: source.drag_to(target)))
    # The first run loads an uncached architecture shard; the second uses the
    # already admitted result. Sampling starts before either visible click.
    architecture = page.evaluate('galaxyGame.model.state.architecture')
    assert not page.evaluate('id => Boolean(GalaxyCNNResults.get(id))', architecture)
    save = page.locator('[data-action="architecture-save"]'); save.scroll_into_view_if_needed()
    def run():
        page.locator('[data-action="architecture-save"]').click()
        page.wait_for_function('galaxyGame.model.state.current')
    report.append(sample(page, 'run-cold', run, changes_architecture=False))
    assert page.evaluate('id => Boolean(GalaxyCNNResults.get(id))', architecture)
    metric = page.locator('[data-action="metrics"]'); metric.scroll_into_view_if_needed()
    def open_metrics():
        metric.click(); page.wait_for_selector('.modal details.metrics'); page.keyboard.press('Escape')
    report.append(sample(page, 'metrics-open-close', open_metrics, changes_architecture=False))
    page.locator('[data-action="architecture-save"]').scroll_into_view_if_needed()
    report.append(sample(page, 'run-warm', run, changes_architecture=False))
    assert page.evaluate('id => Boolean(GalaxyCNNResults.get(id))', architecture)
    return report


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    final={'status':'PASS','ordinary':None,'warm':None,'reduced':None,'errors':[]}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        for key, motion in [('ordinary','no-preference'),('reduced','reduce')]:
            page=browser.new_page(viewport={'width':1280,'height':720},reduced_motion=motion)
            errors=[]; page.on('pageerror',lambda error:errors.append(str(error)))
            final[key]=suite(page, motion == 'reduce')
            if key == 'ordinary':
                final['warm'] = suite(page, False)
            final['errors'].extend(errors); assert not errors, errors
            page.close()
        browser.close()
    compact = {**final, **{key: [{k: v for k, v in row.items() if k != 'frames'} for row in final[key]] for key in ('ordinary', 'warm', 'reduced')}}
    (OUT/'flicker-after.json').write_text(json.dumps(compact,ensure_ascii=False,indent=2))
    print('PASS N08', OUT/'flicker-after.json')

if __name__ == '__main__': main()
