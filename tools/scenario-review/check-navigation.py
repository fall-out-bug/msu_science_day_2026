"""Current navigation mockup checks; no production comments or game results."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];PUB=ROOT/'designlab/comparison/docs'
with sync_playwright() as w:
 b=w.chromium.launch();p=b.new_page(viewport={'width':1280,'height':900});errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
 p.goto((PUB/'galaxy-game-design.html').as_uri());cards=p.locator('[data-screen-image]');assert cards.count()==8
 for i in range(cards.count()):
  cards.nth(i).click();box=p.locator('#screen-lightbox');assert box.is_visible()
  p.wait_for_function('document.querySelector("#screen-lightbox img").naturalWidth===1920')
  assert box.locator('img').evaluate('(i)=>i.naturalHeight')==1080
  p.keyboard.press('Escape');assert not box.is_visible()
 cards.first.click();p.keyboard.press('ArrowRight');assert '02' in p.locator('#screen-lightbox-title').inner_text();p.keyboard.press('Escape')
 for width in [1920,1280,390]:
  p.set_viewport_size({'width':width,'height':900});assert p.evaluate('document.documentElement.scrollWidth<=innerWidth')
 p.goto((PUB/'gdd-assets/navigation-nika/preview.html').as_uri());p.get_by_role('button',name='Открыть архив →',exact=True).click();p.get_by_role('button',name='К самостоятельным меткам →',exact=True).click();p.get_by_role('button',name='Видна спираль',exact=True).click()
 p.locator('#home').click();p.get_by_role('button',name='Продолжить работу →',exact=True).click();assert p.locator('.selected').inner_text()=='Видна спираль'
 p.get_by_role('button',name='Открыть макет проверки →',exact=True).click();p.get_by_role('button',name='Проверить старые подписи →',exact=True).click();p.get_by_role('button',name='Видна спираль',exact=True).click();p.get_by_role('button',name='Открыть повторную проверку →',exact=True).click()
 p.get_by_role('button',name='Завершить смену →',exact=True).click();assert 'Готовимся' in p.locator('h1').inner_text()
 p.locator('#back').click();p.get_by_role('button',name='Попробовать два варианта CNN →',exact=True).click();assert 'отдельный подготовленный набор' in p.locator('main').inner_text().lower()
 p.get_by_role('button',name='Добавить второй блок',exact=True).click();assert 'Вариант B' in p.locator('main').inner_text();p.get_by_role('button',name='Убрать второй блок',exact=True).click();assert 'Вариант A' in p.locator('main').inner_text()
 p.get_by_role('button',name='К итогу →',exact=True).click();p.get_by_role('button',name='Вернуться к разметке',exact=True).click();assert p.locator('.selected').inner_text()=='Видна спираль'
 p.locator('#help').click();assert p.locator('#hint').is_visible();p.keyboard.press('Escape')
 for width,height in [(1920,1080),(1280,720),(390,844)]:
  p.set_viewport_size({'width':width,'height':height})
  for screen in ['morning','archive','label','experiment','review','compare','cnn','evening']:
   p.evaluate('(s)=>navigationPreview.go(s)',screen);assert p.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,screen)
 p.set_viewport_size({'width':1280,'height':720});p.evaluate('navigationPreview.go("label")');p.screenshot(path='/tmp/nika-label-1280.png')
 assert not errors,errors;b.close()
print('PASS: 8 Full HD images, lightbox/keyboard, all screens at 3 sizes, retained labels, optional CNN/bypass, return and help')
