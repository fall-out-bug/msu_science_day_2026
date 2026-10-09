#!/usr/bin/env python3
"""First player transition must show its text and next action without scrolling."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
VIEWPORTS = ((1280, 720), (1366, 768), (1440, 900), (1920, 1080), (853, 480))


def inspect_frame(page):
    return page.evaluate('''() => {
      const card=document.querySelector('.route-story__card');
      const button=document.querySelector('[data-action="collect-map"]');
      const rect=el=>{const r=el.getBoundingClientRect();return {left:r.left,top:r.top,right:r.right,bottom:r.bottom}};
      const r=button.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
      const overflow=[card,...card.querySelectorAll('*')].filter(el=>el.scrollHeight>el.clientHeight+1&&['auto','scroll'].includes(getComputedStyle(el).overflowY));
      return {viewport:[innerWidth,innerHeight],pageHeight:document.documentElement.scrollHeight,pageWidth:document.documentElement.scrollWidth,
        card:{...rect(card),clientHeight:card.clientHeight,scrollHeight:card.scrollHeight},button:rect(button),
        buttonHit:hit===button||button.contains(hit),internalScroll:overflow.map(el=>el.className),scrollY,
        text:card.innerText};
    }''')


def check(page, url, keyboard=False):
    page.goto(url)
    if keyboard:
        for _ in range(20):
            if page.evaluate('document.activeElement?.matches("[data-action=start-route]")'):
                break
            page.keyboard.press('Tab')
        else:
            raise AssertionError('Start action is not keyboard-reachable')
        page.keyboard.press('Enter')
    else:
        page.locator('[data-action="start-route"]').click()
    page.locator('.route-story__card').wait_for(state='visible')
    state=inspect_frame(page)
    w,h=state['viewport']
    failures=[]
    if state['pageHeight']>h+1 or state['pageWidth']>w+1:failures.append('page scroll')
    if state['internalScroll'] or state['card']['scrollHeight']>state['card']['clientHeight']+1:failures.append('card scroll')
    if state['card']['top']<0 or state['card']['bottom']>h+1:failures.append('card outside frame')
    if not state['buttonHit']:failures.append('next action obscured')
    for text in ['Найдём галактики','Волосы Вероники','M85','Euclid','Источник']:
        if text not in state['text']:failures.append('missing '+text)
    if page.locator('.route-story__terms').count():failures.append('premature dictionary block')
    del state['text']
    state['failures']=failures
    state['status']='FAIL' if failures else 'PASS'
    if not failures:
        # A direct pointer click cannot rescue an offscreen button by auto-scrolling.
        r=state['button'];page.mouse.click((r['left']+r['right'])/2,(r['top']+r['bottom'])/2)
        page.locator('.sky-atlas').wait_for(state='visible')
    return state


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--baseline',help='Check the pre-fix game.js/CSS from this commit')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='night-story-frame-') as temp:
        folder=Path(temp)
        if args.baseline:
            for path in HERE.iterdir():
                if path.name in ('game.js','galaxy.css'):
                    rel=path.relative_to(HERE.parents[1]).as_posix()
                    (folder/path.name).write_bytes(subprocess.check_output(['git','show',args.baseline+':'+rel],cwd=HERE))
                else:(folder/path.name).symlink_to(path,target_is_directory=path.is_dir())
        else:folder=HERE
        rows=[];errors=[]
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            for viewport in VIEWPORTS:
                for motion in ('reduce','no-preference'):
                    page=browser.new_page(viewport=dict(zip(('width','height'),viewport)),reduced_motion=motion)
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    row=check(page,(folder/'index.html').as_uri(),keyboard=motion=='reduce')
                    row['motion']=motion;rows.append(row);page.close()
            browser.close()
    report={'status':'FAIL' if errors or any(r['status']=='FAIL' for r in rows) else 'PASS','baseline':args.baseline,'checks':rows,'browserErrors':errors}
    args.evidence.parent.mkdir(parents=True,exist_ok=True)
    args.evidence.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'checks':len(rows),'failures':sum(r['status']=='FAIL' for r in rows),'evidence':str(args.evidence)}))
    if report['status']!='PASS':raise SystemExit(1)

if __name__=='__main__':main()
