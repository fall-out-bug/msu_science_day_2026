#!/usr/bin/env python3
"""Test the persistent measurement workbench, real inputs and timer lifecycle."""
from pathlib import Path
import json
import os
import sys
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ENTRY = sys.argv[1] if len(sys.argv) > 1 else (HERE / 'index.html').as_uri()
OUT = HERE / 'evidence'
OUT.mkdir(exist_ok=True)
checks, errors = [], []


def check(name, condition):
    assert condition, name
    checks.append(name)


def launch(playwright):
    executable = os.environ.get('PW_CHROMIUM')
    if not executable:
        candidates = sorted((Path.home() / '.cache/ms-playwright').glob('chromium-*/chrome-linux/chrome'))
        executable = str(candidates[-1]) if candidates else None
    options = {'headless': True}
    if executable:
        options['executable_path'] = executable
    return playwright.chromium.launch(**options)


with sync_playwright() as playwright:
    browser = launch(playwright)
    page = browser.new_page(viewport={'width': 1440, 'height': 1050}, reduced_motion='reduce')
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(ENTRY)
    page.wait_for_function('window.journey && window.opening && window.comparisonProbe')

    def snap(name):
        page.screenshot(path=str(OUT / ('bench-' + name + '.png')), full_page=True)

    def click_point(x, y):
        canvas = page.locator('#opening-sky')
        canvas.scroll_into_view_if_needed()
        box = canvas.bounding_box()
        page.mouse.click(box['x'] + (x + .5) / 128 * box['width'],
                         box['y'] + (y + .5) / 128 * box['height'])

    def wait_result(outcome):
        page.wait_for_function('comparisonProbe.state.phase === "result"')
        check('computed opening outcome ' + outcome,
              page.evaluate('comparisonProbe.state.result.outcome') == outcome)

    def reset():
        page.evaluate('journey.reset()')
        page.wait_for_function('journey.state.view === "overview" && !opening.state.active')
        page.locator('#bench-start').click()
        page.wait_for_function('journey.state.view === "opening" && opening.state.active')

    def source_button(x):
        number = page.evaluate('(x)=>COMPARISON_DATA.cases[0].sources[1].findIndex(p=>p.x===x)+1', x)
        return page.locator('#opening-points button').nth(number - 1)

    def raw_frame_matches(epoch):
        return page.evaluate('''epoch=>{
            const d=COMPARISON_DATA.cases[0],s=epoch===0?{...d,arrays:[d.arrays[0],d.arrays[0]]}:d;
            const raw=document.createElement('canvas');raw.width=raw.height=128;
            raw.getContext('2d').putImageData(new ImageData(ComparisonModel.render(s,0,epoch||1).pixels,128,128),0,0);
            const expected=document.createElement('canvas');expected.width=expected.height=640;
            expected.getContext('2d').drawImage(raw,0,0,640,640);
            return expected.toDataURL()===document.getElementById('opening-sky').toDataURL();
        }''', epoch)

    def canvas_value(identifier):
        return page.locator('#' + identifier).evaluate('(canvas)=>canvas.toDataURL()')

    def fits(identifier):
        return page.locator('#' + identifier).evaluate('(node)=>{const r=node.getBoundingClientRect();return r.top>=0 && r.bottom<=innerHeight && r.left>=0 && r.right<=innerWidth;}')

    def result_pixels_match(kind):
        return page.evaluate("""kind=>{
            const motion=kind==='motion', record=motion?comparisonProbe.state.journal[0]:brightnessEpisode.state.attempts.find(a=>a.result.outcome==='faded');
            const data=motion?COMPARISON_DATA.cases.find(c=>c.id===record.caseId):BRIGHTNESS_DATA;
            const expected=document.createElement('canvas');expected.width=motion?384:256;expected.height=128;
            const ctx=expected.getContext('2d');
            for(let epoch=0;epoch<(motion?3:2);epoch++){
                const raw=document.createElement('canvas');raw.width=raw.height=128;
                let pixels;
                if(motion){const source=epoch===0?{...data,arrays:[data.arrays[0],data.arrays[0]]}:data;pixels=new ImageData(ComparisonModel.render(source,0,epoch||1).pixels,128,128);}
                else{pixels=new ImageData(128,128);data.arrays[epoch].forEach((v,i)=>{const t=v<0?0:Math.min(1,Math.asinh(v*.2)/Math.asinh(data.displayTop*.2));[8,14,29].forEach((b,c)=>pixels.data[4*i+c]=b+([204,242,255][c]-b)*t);pixels.data[4*i+3]=255;});}
                raw.getContext('2d').putImageData(pixels,0,0);
                const point=motion?record.result.positions[epoch]:record.selection.point, x=Math.max(0,Math.min(98,point.x-15)),y=Math.max(0,Math.min(98,point.y-15));
                if(motion){
                    ctx.drawImage(raw,128*epoch,0);
                    ctx.strokeStyle='#d9f6ee';ctx.lineWidth=1;ctx.beginPath();ctx.arc(128*epoch+point.x+.5,point.y+.5,6,0,Math.PI*2);ctx.stroke();
                }else{
                    ctx.drawImage(raw,x,y,30,30,128*epoch,0,128,128);
                    ctx.strokeStyle='#d9f6ee';ctx.lineWidth=2;ctx.beginPath();ctx.arc(128*epoch+(point.x+.5-x)/30*128,(point.y+.5-y)/30*128,10,0,Math.PI*2);ctx.stroke();
                }
            }
            return expected.toDataURL()===document.getElementById('bench-'+kind+'-result').toDataURL();
        }""",kind)

    check('default is a workbench containing two real preview canvases',
          page.locator('#bench-start').is_visible() and page.locator('#opening').is_hidden()
          and page.evaluate('journey.state.view === "overview"'))
    check('preview pixels come from actual first and second observations',page.evaluate("""()=>[0,1].every(epoch=>{
        const d=COMPARISON_DATA.cases[0],source=epoch===0?{...d,arrays:[d.arrays[0],d.arrays[0]]}:d;
        const expected=document.createElement('canvas');expected.width=expected.height=128;
        expected.getContext('2d').putImageData(new ImageData(ComparisonModel.render(source,0,epoch||1).pixels,128,128),0,0);
        return expected.toDataURL()===document.getElementById(epoch?'bench-preview-second':'bench-preview-first').toDataURL();
    })"""))
    check('unearned result thumbnails are absent',page.locator('#bench-motion-result').is_hidden() and page.locator('#bench-light-result').is_hidden())
    check('illustration scene and its runtime are removed',page.locator('#observatory-stage').count()==0 and page.locator('script[src*="observatory-art"],link[href*="observatory.css"]').count()==0 and page.locator('#bench-shell svg').count()==0)
    page.evaluate('window.__originalBench=document.getElementById("bench-shell")')
    snap('entry')
    page.locator('#bench-start').focus()
    page.keyboard.press('Enter')
    check('keyboard enters instrument inside the same connected workbench',page.evaluate('document.getElementById("bench-shell")===window.__originalBench && __originalBench.isConnected && document.getElementById("bench-focus").contains(document.getElementById("opening"))') and page.locator('#overview').is_visible() and page.locator('#bench-desk').is_hidden() and page.locator('#opening').is_visible())
    snap('focus')
    check('reduced motion starts with static later exposure',
          page.evaluate('opening.state.epoch === 1 && !opening.state.playing'))
    check('default sky renders second real frame with no third exposure', raw_frame_matches(1))
    check('no action or earned movement before selection',
          page.locator('#opening-action').is_hidden() and page.evaluate('comparisonProbe.state.selection === null && comparisonProbe.state.journal.length === 0'))
    click_point(100, 100)
    check('empty sky does not create target or action',
          page.evaluate('comparisonProbe.state.selection === null') and page.locator('#opening-action').is_hidden()
          and 'нет' in page.locator('#opening-feedback').inner_text())
    page.locator('#opening-earlier').click()
    check('manual earlier control shows first real frame', page.evaluate('opening.state.epoch === 0') and raw_frame_matches(0))
    page.locator('#opening-later').click()
    check('manual later control restores second real frame', page.evaluate('opening.state.epoch === 1') and raw_frame_matches(1))
    click_point(71, 10)
    check('wrong stationary point remains a selectable scientific test',
          page.evaluate('comparisonProbe.state.selection.point.x === 71') and page.locator('#opening-action').is_visible())
    snap('selected')
    page.locator('#opening-action').click()
    wait_result('stationary')
    check('wrong result reveals real third frame without awarding movement',
          page.evaluate('opening.state.epoch === 2 && comparisonProbe.state.journal.length === 0')
          and 'осталась' in page.locator('#opening-feedback').inner_text())
    earlier_attempt = page.evaluate('JSON.stringify(comparisonProbe.state.attempts[0])')
    page.locator('#opening-action').click()
    check('retry returns to two-exposure choice and keeps first attempt',
          page.evaluate('comparisonProbe.state.phase === "search" && comparisonProbe.state.selection === null && opening.state.epoch === 1')
          and page.evaluate('JSON.stringify(comparisonProbe.state.attempts[0])') == earlier_attempt)
    page.locator('#opening-earlier').click()
    origin = page.evaluate('TrackingModel.select(COMPARISON_DATA.cases[0],58,68).origin')
    click_point(origin['x'], origin['y'])
    check('earlier-frame click transfers unambiguous first-to-second match',
          page.evaluate('comparisonProbe.state.selection.point.x === 58 && comparisonProbe.state.selection.point.y === 68 && opening.state.epoch === 1'))
    check('selection does not reveal third exposure',
          page.evaluate('comparisonProbe.state.result === null && opening.state.epoch < 2'))
    page.emulate_media(reduced_motion='no-preference')
    page.locator('#opening-action').click()
    check('checking keeps third hidden and locks comparison controls',
          page.evaluate('comparisonProbe.state.phase === "checking" && opening.state.epoch === 1')
          and all(page.locator('#' + target).is_disabled() for target in ['opening-earlier', 'opening-later', 'opening-play']))
    wait_result('moving')
    check('moving result saves exactly one personal track',
          page.evaluate('comparisonProbe.state.journal.length === 1 && comparisonProbe.state.journal[0].caseId === "s02" && opening.state.epoch === 2'))
    check('failed attempt and post-reveal status are preserved',
          page.evaluate('comparisonProbe.state.attempts.length === 2 && !comparisonProbe.state.attempts[1].firstLook')
          and page.evaluate('JSON.stringify(comparisonProbe.state.attempts[0])') == earlier_attempt)
    check('opening outcome matches shared scientific tracking engine',
          page.evaluate('JSON.stringify(comparisonProbe.state.result) === JSON.stringify(TrackingModel.confirm(COMPARISON_DATA.cases[0],comparisonProbe.state.selection))'))
    snap('caught')
    result_before = page.evaluate('JSON.stringify(comparisonProbe.state)')
    page.locator('#opening-action').click()
    check('continue opens assembly without making another attempt',
          page.locator('#overview').is_visible() and page.evaluate('JSON.stringify(comparisonProbe.state)') == result_before)
    check('bench offers installation immediately after measured result','Добавить поиск движения' in page.locator('#shift-action').inner_text())
    check('return restores same bench with earned three-frame full-image strip',page.locator('#bench-desk').is_visible() and page.locator('#bench-motion-result').is_visible() and page.evaluate('document.getElementById("bench-shell")===__originalBench') and result_pixels_match('motion'))
    check('bench reports computed 1.09-pixel prediction residual', '1.09' in page.locator('#bench-motion-evidence').inner_text() and page.evaluate('comparisonProbe.state.journal[0].result.distancePx.toFixed(2)')=='1.09')
    motion_pixels=canvas_value('bench-motion-result')
    snap('returned')
    page.locator('#shift-action').click()
    check('installation uses earned opening result',
          page.evaluate('journey.state.installed.movement && comparisonProbe.state.journal.length === 1 && comparisonProbe.state.attempts.length === 2'))
    check('installation changes status without measurements or thumbnail changes',page.locator('#bench-motion').get_attribute('data-status')=='installed' and canvas_value('bench-motion-result')==motion_pixels and page.evaluate('JSON.stringify(comparisonProbe.state)')==result_before)
    attempts=page.evaluate('JSON.stringify(comparisonProbe.state.attempts)')
    page.locator('#bench-motion-open').click()
    check('saved motion opens actual result without another attempt',page.evaluate('comparisonProbe.state.result.outcome === "moving"') and page.evaluate('JSON.stringify(comparisonProbe.state.attempts)')==attempts)
    page.locator('#opening-skip').click()
    page.locator('#nav-tracking').click()
    page.locator('#retry').click()
    page.evaluate('comparisonProbe.choose(71,10)')
    page.locator('#follow').click()
    wait_result('stationary')
    page.locator('#nav-overview').click()
    check('failed retry preserves earned full-frame strip and original residual',canvas_value('bench-motion-result')==motion_pixels and '1.09' in page.locator('#bench-motion-evidence').inner_text() and page.locator('#bench-motion-result').is_visible())
    page.locator('#bench-motion-open').click()
    check('inspection restores saved successful result after latest failed attempt',page.evaluate('comparisonProbe.state.result.outcome === "moving" && comparisonProbe.state.attempts.length===3'))
    page.locator('#opening-skip').click()
    page.locator('#shift-action').click()
    canvas=page.locator('#brightness-first');canvas.scroll_into_view_if_needed();box=canvas.bounding_box()
    page.mouse.click(box['x']+65.5/128*box['width'],box['y']+64.5/128*box['height'])
    page.locator('#brightness-measure').click()
    page.wait_for_function('brightnessEpisode.state.phase === "result"')
    page.locator('#brightness-to-overview').click()
    check('brightness result also persists as actual two selected crops',page.locator('#bench-light-result').is_visible() and result_pixels_match('light') and '100 → 34' in page.locator('#bench-light-evidence').inner_text())
    light_pixels=canvas_value('bench-light-result');light_state=page.evaluate('JSON.stringify(brightnessEpisode.state)')
    page.locator('#shift-action').click()
    check('light installation changes status without another measurement',page.locator('#bench-light').get_attribute('data-status')=='installed' and canvas_value('bench-light-result')==light_pixels and page.evaluate('JSON.stringify(brightnessEpisode.state)')==light_state)
    page.locator('#bench-light-open').click()
    check('bench light inspection restores actual saved measurement',page.evaluate('brightnessEpisode.state.result.outcome === "faded" && brightnessEpisode.state.attempts.length===1'))
    page.locator('#brightness-to-overview').click()
    snap('result')
    page.emulate_media(reduced_motion='no-preference')
    page.locator('#journey-reset').click()
    check('reset restores empty desk and clears results and modules',page.locator('#bench-desk').is_visible() and page.locator('#opening').is_hidden() and page.locator('#bench-motion-result').is_hidden() and page.locator('#bench-light-result').is_hidden() and page.locator('#bench-motion').get_attribute('data-status')=='pending' and page.locator('#bench-light').get_attribute('data-status')=='pending' and page.evaluate('comparisonProbe.state.attempts.length===0 && comparisonProbe.state.journal.length===0 && !journey.ready() && !brightnessEpisode.state.earned'))
    page.locator('#bench-start').click()

    # Automatic display rotates first/second only and stops on exit or a preference change.
    check('normal-motion fresh opening starts automatic comparison', page.evaluate('opening.state.playing'))
    epoch_before = page.evaluate('opening.state.epoch')
    page.wait_for_timeout(1450)
    check('automatic comparison switches only first two frames',
          page.evaluate('opening.state.epoch') != epoch_before and page.evaluate('opening.state.epoch < 2'))
    page.locator('#opening-play').click()
    check('pause control stops automatic comparison', not page.evaluate('opening.state.playing'))
    epoch_before = page.evaluate('opening.state.epoch')
    page.wait_for_timeout(1450)
    check('paused exposure remains unchanged', page.evaluate('opening.state.epoch') == epoch_before)
    page.locator('#opening-play').click()
    check('play control restarts comparison', page.evaluate('opening.state.playing'))
    page.emulate_media(reduced_motion='reduce')
    page.wait_for_function('!opening.state.playing')
    check('reduced motion change stops active comparison', not page.evaluate('opening.state.playing'))
    plain = page.locator('#opening-sky').evaluate('(canvas)=>canvas.toDataURL()')
    pixels_before_helper = page.evaluate('JSON.stringify(COMPARISON_DATA.cases[0].arrays)')
    page.locator('.opening-tools summary').click()
    page.wait_for_function('(previous)=>document.getElementById("opening-sky").toDataURL() !== previous', arg=plain)
    check('number overlay alters displayed preview without changing science data',
          plain != page.locator('#opening-sky').evaluate('(canvas)=>canvas.toDataURL()')
          and page.evaluate('JSON.stringify(COMPARISON_DATA.cases[0].arrays)') == pixels_before_helper)
    check('numeric helper exposes real source buttons',
          page.locator('#opening-points button').count() == page.evaluate('COMPARISON_DATA.cases[0].sources[1].length'))
    source_button(58).focus()
    page.keyboard.press('Enter')
    check('keyboard numeric helper selects measured target',
          page.evaluate('comparisonProbe.state.selection.point.x === 58 && !opening.state.playing'))
    attempts_before_empty = page.evaluate('comparisonProbe.state.attempts.length')
    page.locator('#opening-earlier').click()
    click_point(100, 100)
    check('unsupported earlier-frame click clears previous actionable selection',
          page.evaluate('comparisonProbe.state.selection === null') and page.locator('#opening-action').is_hidden()
          and page.evaluate('comparisonProbe.state.attempts.length') == attempts_before_empty)

    # Skip and reset both invalidate a pending third-frame check.
    page.emulate_media(reduced_motion='no-preference')
    source_button(58).click()
    page.locator('#opening-action').click()
    page.locator('#opening-skip').click()
    page.wait_for_timeout(1000)
    check('skip cancels pending third-frame check and display timer',
          page.evaluate('!opening.state.active && !opening.state.playing && comparisonProbe.state.phase === "search" && comparisonProbe.state.attempts.length === 0'))
    check('skip preserves legitimate target without inventing result',
          page.evaluate('comparisonProbe.state.selection.point.x === 58 && comparisonProbe.state.result === null'))
    page.locator('#nav-tracking').click()
    check('old instrument route preserves skipped opening target', page.evaluate('comparisonProbe.state.selection.point.x === 58'))
    reset()
    click_point(58, 68)
    page.locator('#opening-action').click()
    reset()
    page.wait_for_timeout(1000)
    check('reset invalidates pending check and earned result',
          page.evaluate('comparisonProbe.state.phase === "search" && comparisonProbe.state.attempts.length === 0 && comparisonProbe.state.selection === null && comparisonProbe.state.journal.length === 0'))
    page.locator('#opening-skip').click()
    hidden_epoch = page.evaluate('opening.state.epoch')
    page.wait_for_timeout(1450)
    check('hidden opening stops playing and cannot advance exposure',
          page.evaluate('!opening.state.active && !opening.state.playing') and page.evaluate('opening.state.epoch') == hidden_epoch)

    page.emulate_media(reduced_motion='reduce')
    page.evaluate('journey.reset()')
    page.set_viewport_size({'width': 390, 'height': 844})
    check('phone desk has no horizontal overflow', page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
    check('phone desk action fits initial 844-pixel viewport',fits('bench-start'))
    snap('mobile-entry')
    page.locator('#bench-start').focus()
    page.keyboard.press('Enter')
    check('phone focused instrument has no horizontal overflow',page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
    check('real sky is visible within initial phone viewport',
          page.locator('#opening-sky').evaluate('(canvas)=>{const r=canvas.getBoundingClientRect();return r.top>=0 && r.bottom<=innerHeight;}'))
    page.locator('#opening-later').click()
    click_point(58, 68)
    check('phone direct science click selects target', page.evaluate('comparisonProbe.state.selection.point.x === 58'))
    page.evaluate('window.scrollTo(0,0)')
    check('phone selected action fits 844-pixel viewport without scrolling',
          page.locator('#opening-action').evaluate('(button)=>{const r=button.getBoundingClientRect();return r.top>=0 && r.bottom<=innerHeight && r.right<=innerWidth;}'))
    snap('mobile')
    page.locator('#opening-action').focus()
    page.keyboard.press('Enter')
    wait_result('moving')
    check('phone keyboard action earns same single track', page.evaluate('comparisonProbe.state.journal.length === 1'))
    check('phone result action fits viewport',fits('opening-action'))
    page.locator('#opening-action').click()
    check('phone return displays actual result without horizontal overflow',page.locator('#bench-motion-result').is_visible() and result_pixels_match('motion') and page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
    snap('mobile-returned')
    deep=browser.new_page(reduced_motion='reduce')
    deep.on('pageerror',lambda error:errors.append(str(error)))
    deep.goto(ENTRY.split('#')[0]+'#opening')
    deep.wait_for_function('window.journey && opening.state.active')
    check('opening deep link keeps overview visible and focused instrument nested',deep.locator('#overview').is_visible() and deep.locator('#opening').is_visible() and deep.locator('#bench-desk').is_hidden() and deep.evaluate('document.getElementById("bench-focus").contains(document.getElementById("opening"))'))
    deep.close()
    check('opening does not present fixed rules as trained ML', 'ИИ' not in page.locator('#opening-feedback').inner_text())
    check('no runtime errors', not errors)
    browser.close()

report = {'count': len(checks), 'checks': checks, 'engine': 'chromium', 'entry': ENTRY, 'errors': errors}
(OUT / 'opening-browser.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False, indent=2))
