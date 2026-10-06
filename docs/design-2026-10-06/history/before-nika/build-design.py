"""Build the illustrated GDD with embedded Mermaid SVGs and shared comments.
Requires Markdown and Playwright; provide a locally available Mermaid bundle.
"""
import argparse,hashlib,html,json,re,shutil,zipfile
from pathlib import Path
import markdown
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'docs/design-2026-10-06'
PUB=ROOT/'designlab/comparison/docs'
parser=argparse.ArgumentParser();parser.add_argument('--mermaid-bundle',required=True);args=parser.parse_args()
escape=html.escape
images=json.loads((SRC/'assets/galaxies/sources.json').read_text())['images']
for item in images:
 assert hashlib.sha256((SRC/'assets/galaxies'/item['local_file']).read_bytes()).hexdigest()==item['local_file_sha256']
source=(SRC/'game-design.template.md').read_text()
tech=(SRC/'technical-design.md').read_text();tech=tech[tech.index('## 1.'):]
# Embed technical content with one clear heading hierarchy.
tech=re.sub(r'^(#{2,5}) ',lambda m:'#'*(len(m[1])+1)+' ',tech,flags=re.M)
tech=re.sub(r'\[([^\]]+)\]\((\.\./\.\./[^)]+)\)',lambda m:'`'+m[2].removeprefix('../../')+'`',tech)
tech=tech.replace('(../redesign-2026-10-05/first-shift-scenario.md)','(first-shift-scenario.html)')
source=source.replace('<!-- TECHNICAL_DESIGN -->',tech)
source=source.replace('<!-- ROOM_CONCEPT -->','![Концепт комнаты обсерватории](assets/concepts/observatory-room-v1.png)\n\nХудожественный концепт, созданный image_gen; галактики внутри рисунка иллюстративны. Научные снимки показаны отдельно ниже.')
source=source.replace('<!-- ASSISTANT_CONCEPT -->','![Шесть состояний машинного помощника](assets/concepts/assistant-sheet-v1.png)\n\nХудожественный концепт image_gen: шесть состояний одного прибора, не готовый игровой атлас анимаций.')
examples=[]
notes=['Гладкий профиль без различимых рукавов. Это пример видимого облика; не любое гладкое изображение устанавливает эллиптическую природу.','Спиральная структура хорошо видна. Цвет не служит самостоятельным основанием учебной метки.','Диск виден с ребра. Источник описывает объект как спиральную галактику: ракурс и физический тип различаются.','Дополнительный разговор: видимый гладкий облик не определяет всю физическую природу объекта. Не заставляем выбирать «Не уверен» только из-за промежуточного физического типа.']
for item,note in zip(images,notes):
 examples.append(f"### {item['object']} · {item['visible_label']}\n\n![{item['object']}](assets/galaxies/{item['local_file']})\n\n{note}\n\nИсточник: [{item['object']} · ESA/Hubble]({item['source_page']}). Credit: {item['credit']}. [CC BY 4.0](https://esahubble.org/copyright/). Официальный screensize JPEG, без изменений.\n")
source=source.replace('<!-- GALAXY_EXAMPLES -->','\n'.join(examples))
source=source.replace('<!-- ARTIFACT_INDEX -->','''- [Сценарий и реплики](../redesign-2026-10-05/first-shift-scenario.md).
- [Промпты художественных концептов](assets/concepts/PROMPTS.md).
- [Источники, лицензии и SHA-256 научных изображений](assets/galaxies/sources.json).
- Художественные иллюстрации созданы встроенным image_gen; схемы подготовлены в Mermaid; раскладки механик — HTML/CSS.
- Публичный документ содержит общие комментарии без имени; офлайн-копия содержит локальные заметки браузера.
''')
(SRC/'game-design.md').write_text(source.replace('<!-- MECHANIC_DEMO -->','В HTML-версии здесь доступна интерактивная проба трёх раскладок. Это демонстрация управления без обучения и оценки меток.'))
# Source links and images become local published links.
source=source.replace('../redesign-2026-10-05/first-shift-scenario.md','first-shift-scenario.html').replace('](assets/','](gdd-assets/')
svg=[]
with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True);page=browser.new_page();page.set_content('<html><body></body></html>');page.add_script_tag(path=args.mermaid_bundle);page.evaluate("mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme:'neutral'})")
 for i,m in enumerate(re.finditer(r'```mermaid\n(.*?)\n```',source,re.S)):
  svg.append(page.evaluate('async ([id,code]) => (await mermaid.render(id,code)).svg',[f'gddDiagram{i}',m[1]]))
 browser.close()
idx=iter(range(len(svg)));source=re.sub(r'```mermaid\n.*?\n```',lambda m:'\n\nGDDDIAGRAM'+str(next(idx))+'END\n\n',source,flags=re.S)
md=markdown.Markdown(extensions=['tables','fenced_code','toc']);body=md.convert(source)
for i,s in enumerate(svg):body=body.replace(f'<p>GDDDIAGRAM{i}END</p>',f'<figure class="diagram" aria-label="Схема {i+1}">{s}</figure>')
room='''<figure class="concept"><div class="room-map"><img src="gdd-assets/concepts/observatory-room-v1.png" alt="Художественный концепт: архив слева, стол и Помощник в центре, атлас справа"><button class="room-zone" data-zone="archive" type="button">Архив</button><button class="room-zone" data-zone="assistant" type="button">Помощник</button><button class="room-zone" data-zone="desk" type="button">Стол</button><button class="room-zone" data-zone="atlas" type="button">Атлас</button></div><p class="room-tip" role="status">Нажмите на подпись рабочего места: это схема предполагаемых активных зон, не готовая игра.</p><figcaption>Концепт окружения · image_gen · галактики на рисунке иллюстративны. Текст и контролы будут отдельными слоями.</figcaption></figure>'''
body=re.sub(r'<p><img alt="Концепт комнаты обсерватории"[^>]*></p>',lambda m:room,body)
body=re.sub(r'<p><img alt="Шесть состояний машинного помощника"[^>]*></p>','<figure class="concept"><img src="gdd-assets/concepts/assistant-sheet-v1.png" alt="Концепт шести состояний Помощника"><figcaption>Состояния одного персонажа · художественный концепт image_gen, не готовая анимация.</figcaption></figure>',body)
# Keep scientific credits adjacent and visible, including in the demo.
for item,note in zip(images,notes):
 pattern=r'<p><img alt="'+re.escape(item['object'])+r'"[^>]*></p>'
 fig=f'<figure class="science-card"><img loading="lazy" src="gdd-assets/galaxies/{item["local_file"]}" alt="{escape(item["object"])} — реальный снимок ESA/Hubble"><figcaption><strong>{escape(item["object"])}</strong> · {escape(item["visible_label"])}<small>{escape(item["credit"])}</small><a href="{item["source_page"]}">Официальный источник</a> · <a href="https://esahubble.org/copyright/">CC BY 4.0</a></figcaption></figure>'
 body=re.sub(pattern,lambda m:fig,body)
body=body.replace('<!-- MECHANIC_DEMO -->',(SRC/'mechanic-demo.html').read_text())
demo_data=json.dumps(images,ensure_ascii=False).replace('<','\\u003c')
page='''<!doctype html><html lang="ru" data-review-document="galaxy-gdd-v1" data-review-title="Обсуждение дизайн-документа"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Первая смена: атлас галактик — дизайн-документ</title><link rel="stylesheet" href="galaxy-design.css?v=3"><link rel="stylesheet" href="scenario-comments.css?v=5"></head><body><main><header><p class="eyebrow">Science Day · дизайн игры · 6 октября 2026</p><div class="asset-links"><a href="/">Действующая игра</a><a href="first-shift-scenario.html">Сценарий и реплики</a><a href="galaxy-game-design.md" download>Markdown</a><a href="galaxy-design-offline.zip" download>Документ для чтения без сети</a></div><p class="build-note">Проект будущей игры. Иллюстрации — концепты, фотографии — реальные справочные примеры. Демонстраторы показывают управление, не обучают и не оценивают модель.</p></header><aside class="build-note"><strong>Обновление направления:</strong> дневная лаборатория, Кавказ, помощник по Microduck и WebGL. См. раздел 16. Рисунки комнаты и латунного помощника ниже — прежние концепты, снятые с направления.</aside><nav aria-label="Оглавление"><strong>В документе</strong>'''+md.toc+'</nav>'+body+'</main><script id="demo-data" type="application/json">'+demo_data+'</script><script src="galaxy-design-demo.js?v=3"></script><script src="scenario-comments.js?v=5"></script></body></html>'
PUB.mkdir(parents=True,exist_ok=True);(PUB/'galaxy-game-design.html').write_text(page)
shutil.copytree(SRC/'assets',PUB/'gdd-assets',dirs_exist_ok=True)
shutil.copyfile(SRC/'design.css',PUB/'galaxy-design.css');shutil.copyfile(SRC/'design-demo.js',PUB/'galaxy-design-demo.js');(PUB/'galaxy-game-design.md').write_text((SRC/'game-design.md').read_text().replace('](assets/','](gdd-assets/').replace('../redesign-2026-10-05/first-shift-scenario.md','first-shift-scenario.html'))
# Assign fixed comment IDs before browser runtime. Exclude controls and generated art internals.
with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True);p=b.new_page();p.route('**/scenario-comments.js*',lambda r:r.abort());p.route('**/galaxy-design-demo.js*',lambda r:r.abort());p.goto((PUB/'galaxy-game-design.html').as_uri())
 selector='main > p, main > h2, main > h3, main > h4, main > ul > li, main > ol > li, main > blockquote, main > table tbody tr, main > figure > figcaption'
 blocks=p.locator(selector).evaluate_all('es=>Object.fromEntries(es.map((e,i)=>{const id="d1p"+String(i+1).padStart(3,"0");e.dataset.reviewId=id;return [id,e.textContent.trim()]}))')
 previous=ROOT/'tools/scenario-review/gdd-blocks.json'
 if previous.exists() and any(blocks.get(k) != v for k,v in json.loads(previous.read_text()).items() if k.startswith('d1p')):
  raise SystemExit('GDD comment anchors changed: reconcile existing comments and version before publication.')
 # Change presentation after assigning IDs: existing discussions keep their anchors.
 p.evaluate("""() => {
  const main=document.querySelector('main');
  const oldMap=main.querySelector('.room-map');
  const img=oldMap.querySelector('img');oldMap.replaceWith(img);
  main.querySelector('.room-tip').remove();
  for(const prefix of ['4.', '5.']) {
   const start=[...main.querySelectorAll(':scope > h2')].find(h=>h.textContent.startsWith(prefix));
   if(!start) continue;
   const box=document.createElement('details');box.className='superseded-design';
   const label=document.createElement('summary');label.textContent='Прежняя редакция: '+start.textContent+' — заменена новым концептом';
   box.append(label);start.before(box);let n=start;
   do {const next=n.nextElementSibling;box.append(n);n=next;} while(n&&n.tagName!=='H2');
  }
  const notice=main.querySelector(':scope > aside');
  if(notice) notice.remove();
 }""")
 p.locator('main > header').evaluate('(e,markup)=>e.insertAdjacentHTML("afterend",markup)',(SRC/'visual-update.html').read_text())
 blocks.update(p.locator('#visual-v2 h2, #visual-v2 h3, #visual-v2 p:not(.room-tip), #visual-v2 figcaption').evaluate_all('es=>Object.fromEntries(es.map((e,i)=>{const id="d2v"+String(i+1).padStart(3,"0");e.dataset.reviewId=id;return [id,e.textContent.trim()]}))'))
 p.locator('#visual-v2').evaluate('(e,markup)=>e.insertAdjacentHTML("afterend",markup)',(SRC/'navigation-design.rendered.html').read_text())
 blocks.update(p.locator('#navigation-design > h2, #navigation-design > h3, #navigation-design > p, #navigation-design > table tbody tr, #navigation-design .screen-node h4, #navigation-design .screen-node p, #navigation-design .time-card h4').evaluate_all('es=>Object.fromEntries(es.map((e,i)=>{const id="d3n"+String(i+1).padStart(3,"0");e.dataset.reviewId=id;return [id,e.textContent.trim()]}))'))
 if previous.exists() and any(blocks.get(k)!=v for k,v in json.loads(previous.read_text()).items()):
  raise SystemExit('Existing comment anchors changed during visual update.')
 (PUB/'galaxy-game-design.html').write_text(p.content());b.close()
(ROOT/'tools/scenario-review/gdd-blocks.json').write_text(json.dumps(blocks,ensure_ascii=False,indent=2))
# Offline copy uses file:// local notes. Its navigation back to the online game is optional.
with zipfile.ZipFile(PUB/'galaxy-design-offline.zip','w',zipfile.ZIP_DEFLATED) as z:
 for name in ['galaxy-game-design.html','galaxy-game-design.md','galaxy-design.css','galaxy-design-demo.js','scenario-comments.css','scenario-comments.js','first-shift-scenario.html','first-shift-scenario.md']:
  if name.endswith('.html'):
   content=(PUB/name).read_text().replace('href="/"','href="https://sd2026.beetles.family/"').replace('href="galaxy-design-offline.zip"','href="https://sd2026.beetles.family/docs/galaxy-design-offline.zip"')
   z.writestr(name,content)
  else:z.write(PUB/name,arcname=name)
 for p in sorted((PUB/'gdd-assets').rglob('*')):
  if p.is_file():z.write(p,arcname=str(p.relative_to(PUB)))
print(json.dumps({'commentBlocks':len(blocks),'mermaidDiagrams':len(svg),'htmlBytes':(PUB/'galaxy-game-design.html').stat().st_size,'offlineBytes':(PUB/'galaxy-design-offline.zip').stat().st_size}))
