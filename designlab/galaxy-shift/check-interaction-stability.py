#!/usr/bin/env python3
"""Label clicks preserve the mounted photo, zoom and scroll at real UI boundaries."""
from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 b=p.chromium.launch(headless=True)
 for w,h in [(1280,720),(1440,900),(390,844)]:
  page=b.new_page(viewport={'width':w,'height':h},reduced_motion='reduce')
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto((Path(__file__).resolve().parent / 'index.html').as_uri())
  page.wait_for_function('window.galaxyGame')
  page.evaluate("galaxyGame.model.dispatch({type:'START'});galaxyGame.model.dispatch({type:'LABELS'});galaxyGame.render()")
  page.wait_for_function('Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0)')
  page.locator('[data-quest="center"]').click()
  page.locator('[data-quest="zoom"]').click()
  button=page.locator('[data-quest-label]').first
  button.scroll_into_view_if_needed()
  page.wait_for_timeout(350)
  page.evaluate("window.before={photo:document.querySelector('[data-quest-photo]'),scene:document.querySelector('#quest-scene'),scroll:scrollY}")
  button.click()
  assert page.evaluate("before.photo===document.querySelector('[data-quest-photo]')&&before.scene===document.querySelector('#quest-scene')")
  assert page.evaluate("Math.abs(before.scroll-scrollY)<2"),(w,page.evaluate('[before.scroll,scrollY]'))
  assert page.locator('.quest-scene__photo-shell').evaluate("e=>e.classList.contains('is-zoomed')")
  assert page.locator('[data-quest-label][aria-pressed=true]').count()==1
  assert page.locator('[data-quest-observation]').count()==0
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  page.evaluate("""() => {
    for (const id of GALAXY_DATA.childIds)
      galaxyGame.model.dispatch({type:'SET_LABEL',id,label:GALAXY_DATA.images.find(x=>x.id===id).label});
    galaxyGame.model.dispatch({type:'RUN'});
    galaxyGame.model.dispatch({type:'REPAIR'});
    galaxyGame.render();
  }""")
  assert page.locator('[data-quest-label][aria-pressed=true]').count()==0
  assert page.locator('[data-action="run"]').last.is_disabled()
  old_label=page.evaluate('galaxyGame.model.state.labels[GALAXY_DATA.oldIds[0]]')
  page.locator(f'[data-quest-label="{old_label}"]').click()
  assert page.locator('[data-quest-label][aria-pressed=true]').count()==1
  assert page.evaluate('galaxyGame.model.state.reviewedOldIds.includes(GALAXY_DATA.oldIds[0])')
  assert page.locator('[data-action="run"]').last.is_disabled()
  assert not errors,errors
  print('PASS stable label/zoom/scroll at',w,h)
  page.close()
 b.close()
