#!/usr/bin/env python3
"""Regression for welcome overlap, uncropped portraits and enlarged text."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
HERE=Path(__file__).resolve().parent
records=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    for width,height,text_size in [(390,844,100),(754,684,100),(844,390,100),(1280,720,100),(1280,720,200)]:
        page=browser.new_page(viewport={'width':width,'height':height},reduced_motion='reduce')
        page.goto((HERE/'index.html').as_uri())
        page.wait_for_function('galaxyWorld.stats().frames>0 && galaxyGame')
        if text_size!=100:page.evaluate('(size)=>document.documentElement.style.fontSize=size+"%"',text_size)
        page.wait_for_function('Array.from(document.images).every(i=>i.complete&&i.naturalWidth)')
        result=page.evaluate('''()=>{
          const rect=el=>{const r=el.getBoundingClientRect();return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height}};
          const buttons=[...document.querySelectorAll('.welcome>button')].map(rect);
          const portrait=document.querySelector('.welcome .mentor-portrait img'),css=getComputedStyle(portrait);
          return {buttons,portrait:rect(portrait),objectFit:css.objectFit,transform:css.transform,overflow:document.documentElement.scrollWidth>innerWidth};
        }''')
        assert not result['overflow'],result
        assert result['objectFit']=='contain' and result['transform']=='none',result
        for index,button in enumerate(result['buttons']):
            assert button['left']>=0 and button['right']<=width+1 and button['top']>=0 and button['bottom']<=height+1,result
            if index:assert button['top']>=result['buttons'][index-1]['bottom']+7,result
        portrait=result['portrait']
        assert portrait['left']>=0 and portrait['right']<=width+1 and portrait['top']>=0 and portrait['bottom']<=height+1,result
        page.screenshot(path=str(HERE/f'evidence/nika-layout-{width}-{height}-{text_size}.png'))
        records.append({'viewport':[width,height],'textPercent':text_size,'status':'PASS','buttonGap':result['buttons'][1]['top']-result['buttons'][0]['bottom']})
        page.close()
    browser.close()
report={'status':'PASS','cases':records}
(HERE/'evidence/nika-layout.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report))
