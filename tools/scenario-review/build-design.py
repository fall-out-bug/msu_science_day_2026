"""Build the current Nika GDD/scenario; preserve all historical comment anchors."""
import argparse,hashlib,json,re,shutil,zipfile
from pathlib import Path
import markdown
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];SRC=ROOT/'docs/design-2026-10-06';PUB=ROOT/'designlab/comparison/docs'
parser=argparse.ArgumentParser();parser.add_argument('--mermaid-bundle',required=True);args=parser.parse_args()
images=json.loads((SRC/'assets/galaxies/sources.json').read_text())['images']
examples=[]
for item in images:
 assert hashlib.sha256((SRC/'assets/galaxies'/item['local_file']).read_bytes()).hexdigest()==item['local_file_sha256']
 examples.append(f"### {item['object']} · справочное изображение\n\n![{item['object']}](assets/galaxies/{item['local_file']})\n\nCredit: {item['credit']}. [Источник]({item['source_page']}) · [CC BY 4.0](https://esahubble.org/copyright/). Без изменений; не обучающий или проверочный набор.\n")
tech=(SRC/'technical-design.md').read_text();tech=tech[tech.index('## 1.'):];tech=re.sub(r'^(#{2,5}) ',lambda m:'#'*(len(m[1])+1)+' ',tech,flags=re.M)
source=(SRC/'game-design.template.md').read_text().replace('<!-- TECHNICAL_DESIGN -->',tech).replace('<!-- GALAXY_EXAMPLES -->','\n'.join(examples))
(SRC/'game-design.md').write_text(source.replace('<!-- NAVIGATION -->','[Кликабельные экраны](assets/navigation-nika/preview.html).'))
scenario=(ROOT/'docs/redesign-2026-10-05/first-shift-scenario.md').read_text()
shutil.copytree(SRC/'assets',PUB/'gdd-assets',dirs_exist_ok=True)
shutil.copyfile(SRC/'design.css',PUB/'galaxy-design.css')
# Keep legacy JS/styles for archived pages; current page only needs its lightbox.
legacy=(SRC/'design-demo.js').read_text();lightbox=legacy[legacy.index("(()=>{const box=document.querySelector('#screen-lightbox')"):]
(PUB/'galaxy-design-nika.js').write_text(lightbox)
with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True)
 renderer=browser.new_page();renderer.set_content('<html><body></body></html>');renderer.add_script_tag(path=args.mermaid_bundle);renderer.evaluate("mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme:'neutral'})")
 for name,doc,prefix,registry,raw in [('galaxy-game-design','galaxy-gdd-v1','n4d','gdd-blocks.json',source),('first-shift-scenario','first-shift-v1','n4s','blocks.json',scenario)]:
  raw=raw.replace('../redesign-2026-10-05/first-shift-scenario.md','first-shift-scenario.html').replace('../design-2026-10-06/game-design.md','galaxy-game-design.html').replace('](assets/','](gdd-assets/')
  (PUB/(name+'.md')).write_text(raw.replace('<!-- NAVIGATION -->','[Кликабельные экраны](gdd-assets/navigation-nika/preview.html).'))
  diagrams=[]
  def diagram(match):
   i=len(diagrams);diagrams.append(renderer.evaluate('async([id,code])=>(await mermaid.render(id,code)).svg',[name+str(i),match[1]]));return '\n\nDIAGRAM'+str(i)+'END\n\n'
  text=re.sub(r'```mermaid\n(.*?)\n```',diagram,raw,flags=re.S)
  md=markdown.Markdown(extensions=['tables','fenced_code','toc']);body=md.convert(text)
  for i,svg in enumerate(diagrams):body=body.replace('<p>DIAGRAM'+str(i)+'END</p>','<figure class="diagram">'+svg+'</figure>')
  body=body.replace('<!-- NAVIGATION -->',(SRC/'navigation-design.rendered.html').read_text())
  title='Первая смена: атлас галактик' if name=='galaxy-game-design' else 'Первая смена: Ника и модель'
  page=f'''<!doctype html><html lang="ru" data-review-document="{doc}" data-review-title="Обсуждение редакции: Ника и модель"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><link rel="stylesheet" href="galaxy-design.css?v=nika1"><link rel="stylesheet" href="scenario-comments.css?v=5"></head><body><main><header><p class="eyebrow">Science Day · 6 октября 2026 · актуальная редакция</p><div class="asset-links"><a href="galaxy-game-design.html">Дизайн</a><a href="first-shift-scenario.html">Реплики и стендист</a><a href="{name}-before-nika.html">История и прежние комментарии</a><a href="{name}.md">Markdown</a><a href="galaxy-design-offline.zip">Офлайн-копия</a></div><p class="build-note">Документ и макеты обновлены. Новая игра и рассчитанные опыты ещё не собраны.</p></header><nav aria-label="Оглавление">{md.toc}</nav>{body}</main><script src="galaxy-design-nika.js"></script><script src="scenario-comments.js?v=5"></script></body></html>'''
  path=PUB/(name+'.html');path.write_text(page)
  p=browser.new_page();p.route('**/scenario-comments.js*',lambda r:r.abort());p.goto(path.as_uri())
  blocks=p.locator('main > p, main > h2, main > h3, main > h4, main > ul > li, main > ol > li, main > blockquote, main > table tbody tr, #navigation-design > p, #navigation-design > h2').evaluate_all('(es,prefix)=>Object.fromEntries(es.map((e,i)=>{const id=prefix+String(i+1).padStart(3,"0");e.dataset.reviewId=id;return [id,e.textContent.trim()]}))',prefix)
  reg=ROOT/'tools/scenario-review'/registry;old=json.loads(reg.read_text())
  assert all(old[k]==v for k,v in blocks.items() if k in old),'Current revision anchor changed; create a new revision prefix'
  reg.write_text(json.dumps({**old,**blocks},ensure_ascii=False,indent=2));path.write_text(p.content());p.close()
 browser.close()
# Package current documents and archived discussions; all asset paths remain local.
with zipfile.ZipFile(PUB/'galaxy-design-offline.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(PUB.iterdir()):
  if p.is_file() and p.suffix in ['.html','.md','.css','.js']:
   if p.suffix=='.html':z.writestr(p.name,p.read_text().replace('href="/"','href="https://sd2026.beetles.family/"'))
   else:z.write(p,p.name)
 for p in sorted((PUB/'gdd-assets').rglob('*')):
  if p.is_file():z.write(p,str(p.relative_to(PUB)))
print('Built current GDD, scenario, historical comment registries and offline ZIP')
