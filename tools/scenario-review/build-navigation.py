"""Render the Nika navigation mockup; archived art/screens remain untouched."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];SRC=ROOT/'docs/design-2026-10-06';OUT=SRC/'assets/navigation-nika'
screens=[('morning','01 · Утро. Задача Ники','Новый поток данных → архив'),('archive','02 · Один пример вместе','Разобрать признак → свои метки'),('label','03 · Разметка','Три подписи → первая проверка'),('experiment','04 · Первая проверка','Ошибка на другом снимке → старые подписи'),('review','05 · Исправление данных','Изменение подписи → повторный опыт'),('compare','06 · До и после','Завершить / попробовать CNN'),('cnn','07 · Два варианта CNN','Отдельный подготовленный опыт → итог'),('evening','08 · Вечер. Итог','Новая подборка → польза для Ники')]
with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True);p=b.new_page(viewport={'width':1920,'height':1080},device_scale_factor=1)
 for key,title,action in screens:
  p.goto((OUT/'preview.html').as_uri()+'?screen='+key)
  p.evaluate('async()=>{await document.fonts.ready;await Promise.all([...document.images].map(i=>i.decode()))}')
  p.screenshot(path=str(OUT/(key+'.png')))
 b.close()
def thumb(k,t):
 return f'<button type="button" data-screen-image="gdd-assets/navigation-nika/{k}.png" data-screen-title="{t}" aria-label="Открыть {t} в Full HD"><img loading="lazy" src="gdd-assets/navigation-nika/{k}.png" alt="{t}"></button>'
cards=''.join(f'<article class="screen-node">{thumb(k,t)}<h4>{t}</h4><p>{a}</p><small>1920 × 1080 · нажмите для увеличения</small></article>' for k,t,a in screens)
(SRC/'navigation-design.rendered.html').write_text((SRC/'navigation-design.html').read_text().replace('SCREEN_CARDS',cards))
print('Rendered 8 Nika interface mockups at 1920x1080; no model metrics')
