#!/usr/bin/env python3
"""Browser playthrough for the complete Night Shift campaign."""
from pathlib import Path
from urllib.parse import urlparse
import json, os, sys
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ENTRY = sys.argv[1] if len(sys.argv) > 1 else (HERE / "night.html").as_uri()
OUT = Path(os.environ.get("NIGHT_EVIDENCE_DIR", str(HERE / "evidence")))
OUT.mkdir(exist_ok=True)
checks, errors, requests = [], [], []
entry_origin = urlparse(ENTRY).scheme + "://" + urlparse(ENTRY).netloc if urlparse(ENTRY).netloc else None

def check(name, ok):
    if not ok:
        raise AssertionError(name)
    checks.append(name)

def chrome(pw):
    cached = sorted((Path.home()/".cache/ms-playwright").glob("chromium-*/chrome-linux/chrome"))
    return pw.chromium.launch(headless=True, executable_path=os.environ.get("PW_CHROMIUM") or str(cached[-1]))

with sync_playwright() as pw:
    browser = chrome(pw)
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
    page = ctx.new_page()
    page.set_default_timeout(5000)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("request", lambda r: requests.append(r.url) if r.url.startswith(("http://", "https://"))
            and not (entry_origin and r.url.startswith(entry_origin + "/")) else None)
    page.goto(ENTRY)
    page.wait_for_function("window.night && typeof NightModel !== 'undefined'")

    def snap(name):
        page.screenshot(path=str(OUT / ("night-" + name + ".png")), full_page=True)

    def canvas(x, y):
        box = page.locator("#g-sky").bounding_box()
        page.mouse.click(box["x"] + (x+.5)/128*box["width"], box["y"] + (y+.5)/128*box["height"])

    map_keyboard_checked = False

    def world(view=page):
        """Follow the same room/map/instrument buttons available to the player."""
        global map_keyboard_checked
        if view.evaluate("night.state.stage") != "room":
            return
        target = view.evaluate("night.session.worldTarget")
        check(f"{target}: room replaces the research controls", view.locator("#g-room").is_visible()
              and view.locator("#g-game").is_hidden())
        if view.evaluate("night.session.installed.movement && !night.session.learningSeen"):
            view.locator("#g-room-next").click()
            check("room opens the pending correction lesson", view.evaluate("night.state.stage === 'game' && night.state.phase === 'learning'"))
            return
        complete = view.evaluate("night.session.records.filter(NightModel.canSave).length >= night.session.length")
        if complete:
            view.locator("#g-room-next").click()
            check("completed room opens the shift ending", view.locator("#g-ending").is_visible())
            check("ending stays in the observatory at dawn", view.evaluate("night.state.stage === 'ending' && night.session.daylight === true")
                  and view.locator("#g-room-scene").get_attribute("data-mode") == "ending"
                  and view.locator("#g-room-scene").get_attribute("data-daylight") == "true"
                  and view.locator("#g-room-scene canvas").is_visible()
                  and view.locator("#g-game").is_hidden())
            return
        view.locator("#g-room-map").click()
        check(f"{target}: map opens with capture locked before aiming", view.locator("#g-map").is_visible()
              and view.locator("#g-map-capture").is_disabled() and view.locator("#g-game").is_hidden())
        view.locator("#g-map-focus").click()
        check(f"{target}: coordinate aiming unlocks archive capture", view.locator("#g-map-capture").is_enabled())
        if not map_keyboard_checked:
            view.locator("#g-celestial-map").focus()
            view.keyboard.press("ArrowLeft")
            check("keyboard navigation moves the sky away from the telescope axis", view.locator("#g-map-capture").is_disabled())
            view.keyboard.press("Home")
            check("keyboard Home restores aimed capture", view.locator("#g-map-capture").is_enabled())
            snap("map-aimed")
            map_keyboard_checked = True
        view.locator("#g-map-capture").click()
        check(f"{target}: captured archive returns to the room", view.locator("#g-room").is_visible()
              and view.evaluate("night.session.aimedCase === night.session.worldTarget")
              and view.locator("#g-room-instrument").is_enabled())
        view.locator("#g-room-instrument").click()
        check(f"{target}: instrument opens the aimed observation", view.locator("#g-game").is_visible()
              and view.evaluate("night.session.caseId === night.session.aimedCase"))

    def action():
        page.locator("#g-action").click()
        world()

    def save_next():
        action()
        check("result is saved", page.evaluate("night.state.phase") == "saved")
        action()

    def scan():
        action()
        page.wait_for_function("night.state.phase !== 'scanning'")
        check("automatic scan completes", page.evaluate("night.state.phase") in ["scanned", "result"])

    def choose_from_list():
        page.locator("#g-source-picker summary").click()
        for index in range(page.locator("#g-points button").count()):
            page.locator("#g-points button").nth(index).click()
            if page.evaluate("night.state.phase") == "selected":
                return
        raise AssertionError("no visible source selected")

    check("welcome is initial and 6 is selected", page.locator("#g-welcome").is_visible() and page.locator("input[value='6']").is_checked())
    check("welcome does not overflow 1440", page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
    snap("welcome")
    page.locator("#g-start").click()
    check("start enters the observatory room", page.evaluate("night.state.stage === 'room'"))
    check("fresh shift begins before dawn", page.evaluate("!night.session.daylight")
          and page.locator("#g-room-scene").get_attribute("data-daylight") == "false")
    snap("room-first")
    world()
    check("start opens the first real observation", page.locator("#g-game").is_visible() and page.locator("#g-title").inner_text() == "Поймать движение")

    # Amosov: a real click on the second frame drives the model.
    canvas(58, 68)
    check("Amosov point selection enables check", page.evaluate("night.state.phase") == "selected" and page.locator("#g-action").is_enabled())
    action()
    check("third frame validates moving target", page.evaluate("night.state.result.outcome") == "moving")
    snap("amosov")
    action()
    check("movement instrument is installed", page.evaluate("night.session.installed.movement && night.state.phase === 'saved'"))
    action()
    check("learning correction scene begins", page.evaluate("night.state.phase") == "learning")
    snap("learning-compare")
    page.locator("#g-candidates button").nth(0).click()
    check("matching first point remains a question, not a label", page.evaluate("night.session.learningLabel === null && night.state.phase === 'learning'"))
    page.locator("#g-candidates button").nth(1).click()
    check("matching second point remains a question, not a label", page.evaluate("night.session.learningLabel === null && night.state.phase === 'learning'"))
    page.locator("#g-candidates button").nth(2).click()
    check("third differing point labels the wrong link", page.evaluate("night.session.learningLabel === 'wrongLink' && night.state.phase === 'learned'"))
    page.locator("#g-secondary").click()
    check("undo button removes the temporary learning label without removing the track", page.evaluate("night.session.learningLabel === null && night.state.phase === 'learning' && night.session.records.length === 1"))
    page.locator("#g-candidates button").nth(2).click()
    check("wrong-link label can be re-applied through the distinct point", page.evaluate("night.session.learningLabel === 'wrongLink' && night.state.phase === 'learned'"))
    action()
    check("after examples the second investigation is opened", page.evaluate("night.session.caseId === 'brightness-01'"))
    check("main game does not expose raw candidate-count arithmetic", "991" not in page.locator("#g-game").inner_text())

    # SN: genuine click/measure/install.
    canvas(65, 64)
    action()
    check("SN measurement is faded", page.evaluate("night.state.result.outcome") == "faded")
    action()
    check("fading instrument is installed", page.evaluate("night.session.installed.fading && night.state.phase === 'saved'"))
    snap("supernova")
    action()
    check("independent Gianni field is next", page.evaluate("night.session.caseId === 's07'"))
    record_count = page.evaluate("night.session.records.length")
    page.locator("[data-tool='fading']").click()
    scan()
    if page.locator("#g-candidates button").count():
        page.locator("#g-candidates button").first.click()
    action()
    check("wrong light method cannot complete Gianni", page.evaluate("night.session.records.length") == record_count
          and page.evaluate("night.state.phase") == "choose")
    page.locator("[data-tool='learning']").click()
    check("learning tool is selected in independent field", page.evaluate("night.state.method === 'learning'"))
    scan()
    check("learning produces two visual triptych versions for Gianni", page.locator("#g-candidates button").count() == 2
          and page.locator("#g-candidates canvas").count() == 2)
    snap("gianni-cards")
    page.locator("#g-candidates button").nth(1).click()
    check("second Gianni version is rejected by the third observation", page.evaluate("night.state.result.outcome") == "unresolved")
    snap("gianni-error")
    action()
    check("rejecting a false candidate returns to the same list without rescan", page.evaluate("night.state.phase") == "scanned"
          and page.locator("#g-candidates button").count() == 2)
    page.locator("#g-candidates button").nth(0).click()
    check("first learning proposal is a geometrically checked mover", page.evaluate("night.state.result.outcome") == "moving")
    save_next()
    check("weakmid field follows Gianni", page.evaluate("night.session.caseId === 'launch-variable'"))
    page.locator("[data-tool='fading']").click()
    scan()
    page.locator("#g-candidates button").first.click()
    check("third observation exposes rebrightening case", "вернулся" in page.locator("#g-feedback").inner_text().lower() or page.evaluate("night.state.result.outcome") in ["faded", "brightened"])
    save_next()

    # A steady field: an empty automatic scan is a saveable finding.
    check("steady field follows variable field", page.evaluate("night.session.caseId === 'archive-steady'"))
    page.locator("[data-tool='movement']").click()
    scan()
    check("steady field has no manufactured candidates", page.locator("#g-candidates button").count() == 0
          and page.evaluate("night.state.result.reason") == "no_unique_motion_candidate")
    save_next()

    # Artifact: use the visible point list with a real button, not a model call.
    check("artifact field follows steady field", page.evaluate("night.session.caseId === 's04'"))
    page.locator("#g-source-picker summary").click()
    stationary_index = page.evaluate("NightModel.byId('s04').data.sources[1].findIndex(p=>p.x===111&&p.y===91)")
    page.locator("#g-points button").nth(stationary_index).click()
    check("artifact source can be selected through keyboard-accessible list", page.evaluate("night.state.phase") == "selected")
    action()
    check("artifact does not become a moving discovery", page.evaluate("night.state.result.outcome") != "moving")
    action()
    check("a stationary background star does not resolve the single-signal question", page.evaluate("night.session.records.length === 5 && night.state.phase === 'choose'"))
    canvas(63, 64); action()
    check("single signal preserves the actual ambiguity of its origins", page.evaluate("night.state.result.outcome === 'unresolved' && night.state.result.reason === 'several_possible_origins'"))
    action()
    check("artifact unresolved observation is saved honestly", page.evaluate("night.state.phase") == "saved")
    action()
    check("six-case path reaches a finished shift", page.locator("#g-ending").is_visible())
    snap("ending-six-scene")
    page.locator("#g-ending-journal").click()
    check("ending journal keeps six observation cards and real epoch images", page.locator("#g-overlay").evaluate("e=>e.open")
          and page.locator("#g-overlay .observation-card").count() == 6
          and page.locator("#g-overlay canvas").count() >= 14)
    page.locator("#g-close").click()
    check("closing the ending journal restores the room finale", page.locator("#g-ending").is_visible()
          and not page.locator("#g-overlay").evaluate("e=>e.open"))
    with page.expect_download() as download_info:
        page.locator("#g-export").click()
    download = download_info.value
    check("player receives an HTML journal, not a raw data file", download.suggested_filename == "my-sky-journal.html")
    journal_path = OUT / "night-export-check.html"
    download.save_as(str(journal_path))
    journal_page = ctx.new_page()
    journal_requests = []
    journal_page.on("request", lambda r: journal_requests.append(r.url) if r.url.startswith(("http://", "https://")) else None)
    journal_page.goto(journal_path.resolve().as_uri())
    check("downloaded journal opens independently with all embedded pictures", journal_page.locator("article").count() == 6
          and journal_page.evaluate("[...document.images].length >= 14 && [...document.images].every(i=>i.complete && i.naturalWidth === 256)")
          and not journal_requests)
    check("downloaded SN evidence retains its real light ratio", "Свет: 34" in journal_page.locator("[data-case-id='brightness-01']").inner_text())
    journal_page.set_viewport_size({"width": 390, "height": 844})
    check("standalone journal fits a phone", journal_page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
    journal_page.close()
    # A saved photometry observation remains the same observation when reopened.
    page.locator("#g-ending-journal").click()
    page.locator("#g-overlay [data-case-id='brightness-01'] button").click()
    check("ending card reopens saved SN evidence without another measurement", page.evaluate("night.state.phase === 'saved' && night.state.result.point.x === 65 && night.session.records.length === 6"))
    snap("reopened-light")
    page.locator("#g-journal-open").click()
    check("journal shows all saved observations with images", page.locator("#g-overlay .observation-card").count() == 6
          and page.locator("#g-overlay canvas").count() >= 14)
    snap("journal")
    page.locator("#g-close").click(); action()
    snap("ending-six")
    page.locator("#g-continue").click()
    check("archive continuation retains the dawn already reached", page.evaluate("night.session.daylight === true && JSON.parse(localStorage.getItem('science-day-night-v1')).daylight === true")
          and page.locator("#g-room-scene").get_attribute("data-daylight") == "true")
    world()
    check("ending extends the archive to nine", page.locator("#g-game").is_visible() and page.evaluate("night.session.length === 9"))

    # The three continuation investigations are distinct questions, not a replay of a card.
    check("manual brightening investigation opens", page.evaluate("night.session.caseId === 'archive-brightening'"))
    canvas(105, 74); action()
    check("an ordinary star does not earn the brightening reward", page.evaluate("night.state.result.outcome === 'unresolved'")
          and page.locator("#g-reward").is_hidden())
    action()
    check("ordinary star keeps the brightening investigation open", page.evaluate("night.session.records.length === 6 && night.state.phase === 'choose'"))
    canvas(63, 63); action()
    check("manual photometry produces a recorded comparison", page.evaluate("night.state.result !== null"))
    save_next()
    check("small-change investigation opens", page.evaluate("night.session.caseId === 'archive-small-change'"))
    canvas(63, 63); action()
    check("small-change produces a measured or open result", page.evaluate("night.state.result !== null"))
    save_next()
    check("artifact-track investigation opens", page.evaluate("night.session.caseId === 'archive-track'"))
    page.locator("[data-tool='fading']").click(); scan(); action()
    check("fading search cannot close a question about motion", page.evaluate("night.session.records.length === 8 && night.state.phase === 'choose'"))
    page.locator("[data-tool='movement']").click(); scan()
    if page.locator("#g-candidates button").count():
        page.locator("#g-candidates button").first.click()
    check("artifact-track produces an inspectable automatic result", page.evaluate("night.state.result !== null"))
    save_next()
    check("nine-case path reaches final ending", page.locator("#g-ending").is_visible() and page.evaluate("night.session.records.length === 9"))
    snap("ending-nine")

    # Persisted full work is restored after an actual browser reload.
    page.reload()
    page.wait_for_function("window.night")
    check("reload restores persisted shift", page.locator("#g-resume").is_visible() and page.evaluate("night.session.records.length === 9"))
    page.locator("#g-resume").click()
    world()
    check("resume restores completed shift", page.locator("#g-ending").is_visible())
    check("resumed completed shift restores its dawn", page.evaluate("night.session.daylight === true")
          and page.locator("#g-room-scene").get_attribute("data-daylight") == "true")
    page.evaluate("""() => { const s=JSON.parse(localStorage.getItem('science-day-night-v1')); const r=s.records.find(r=>r.caseId==='archive-brightening'); r.outcome='unresolved'; r.ratios=[100,97,102]; r.summary='Яркость почти не изменилась'; localStorage.setItem('science-day-night-v1',JSON.stringify(s)); }""")
    page.reload(); page.wait_for_function("window.night"); page.locator("#g-resume").click()
    check("old premature completion preserves observations but reopens its question", page.evaluate("night.session.records.length === 9 && !night.session.finished"))
    world()
    check("resumed shift returns to the unanswered brightening question", page.evaluate("night.session.caseId === 'archive-brightening' && night.state.phase === 'choose'"))
    canvas(63, 63); action(); save_next()
    check("repairing an old result finishes without duplicating journal records", page.locator("#g-ending").is_visible()
          and page.evaluate("night.session.records.length === 9"))

    # A new three-investigation mode starts cleanly and limits its archive honestly.
    page.locator("#g-new").click(); page.locator("#g-overlay .primary").click()
    check("handing off the shift resets the room to night", page.evaluate("night.session === null")
          and page.locator("#g-room-scene").get_attribute("data-daylight") == "false")
    page.locator("input[value='3']").check(); page.locator("#g-start").click()
    check("new three-case shift resets daylight", page.evaluate("!night.session.daylight")
          and page.locator("#g-room-scene").get_attribute("data-daylight") == "false")
    world()
    check("new 3-case shift resets state and archive scope", page.evaluate("night.session.length === 3 && night.session.records.length === 0")
          and page.locator("#g-archive button").count() == 3)

    # A complete short session is also real interaction, not a selector-only check.
    canvas(58, 68); action(); action(); action(); page.locator("#g-candidates button").nth(2).click(); action()
    check("three-case path reaches the light investigation", page.evaluate("night.session.caseId === 'brightness-01'"))
    canvas(65, 64); action(); action(); action()
    check("three-case path reaches independent automatic field", page.evaluate("night.session.caseId === 's07'"))
    page.locator("[data-tool='movement']").click()
    page.emulate_media(reduced_motion="no-preference")
    action()
    check("motion scan begins before pause", page.evaluate("night.state.phase") == "scanning")
    page.locator("#g-pause").click()
    check("pause cancels a real active scan", page.evaluate("night.state.phase") == "choose" and page.locator("#g-overlay").evaluate("e=>e.open"))
    page.locator("#g-close").click(); page.emulate_media(reduced_motion="reduce")
    scan(); page.locator("#g-candidates button").first.click(); save_next()
    check("short three-case path reaches its ending", page.locator("#g-ending").is_visible() and page.evaluate("night.session.records.length === 3"))

    # A valid old saved session with the formerly allowed positive correction must repair, not reset.
    page.locator("#g-new").click(); page.locator("#g-overlay .primary").click()
    check("another fresh shift clears the previous dawn", page.locator("#g-room-scene").get_attribute("data-daylight") == "false")
    page.locator("#g-start").click()
    world()
    canvas(58, 68); action(); action(); action(); page.locator("#g-candidates button").nth(2).click(); action()
    canvas(65, 64); action(); action(); action()
    check("legacy fixture has two real records before migration", page.evaluate("night.session.caseId === 's07' && night.session.records.length === 2"))
    page.evaluate("""() => { const s=JSON.parse(localStorage.getItem('science-day-night-v1')); s.learningLabel='sameObject'; s.learningSeen=true; s.caseId='s07'; localStorage.setItem('science-day-night-v1', JSON.stringify(s)); }""")
    page.reload(); page.wait_for_function("window.night")
    page.locator("#g-resume").click()
    world()
    check("old positive correction restores and offers repair", page.evaluate("night.session.records.length === 2 && night.session.learningLabel === 'sameObject'")
          and "Разобрать" in page.locator("#g-action").inner_text())
    action()
    check("old correction opens the visual repair lesson", page.evaluate("night.state.phase === 'learning'"))
    page.locator("#g-candidates button").nth(2).click(); action()
    check("repair preserves prior records and returns to Gianni", page.evaluate("night.session.caseId === 's07' && night.session.records.length === 2 && night.session.learningLabel === 'wrongLink'"))
    snap("learning-repair")

    # Mobile keyboard source picker, pause cancelling a real scan, sound state, layout.
    mobile_ctx = browser.new_context(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
    mobile = mobile_ctx.new_page()
    mobile.on("pageerror", lambda e: errors.append(str(e)))
    mobile.on("request", lambda r: requests.append(r.url) if r.url.startswith(("http://", "https://"))
              and not (entry_origin and r.url.startswith(entry_origin + "/")) else None)
    mobile.set_viewport_size({"width": 390, "height": 844})
    mobile.goto(ENTRY); mobile.wait_for_function("window.night")
    check("mobile has no horizontal overflow", mobile.evaluate("document.documentElement.scrollWidth <= innerWidth"))
    mobile.locator("#g-start").click()
    check("mobile start enters the room", mobile.evaluate("night.state.stage === 'room'"))
    check("mobile room has no horizontal overflow", mobile.evaluate("document.documentElement.scrollWidth <= innerWidth"))
    mobile.screenshot(path=str(OUT / "night-mobile-room.png"), full_page=True)
    world(mobile)
    mobile.locator("#g-source-picker summary").focus(); mobile.keyboard.press("Enter")
    check("mobile keyboard opens point list", mobile.locator("#g-source-picker").evaluate("e=>e.open"))
    mobile.locator("#g-sound").click()
    check("sound toggle states pressed", mobile.locator("#g-sound").get_attribute("aria-pressed") == "true")
    mobile.locator("#g-pause").click()
    check("pause opens an actual modal", mobile.locator("#g-overlay").evaluate("e=>e.open"))
    mobile.locator("#g-close").click()
    # The mobile run yields screenshots of the actionable, selected and measured states.
    mobile.screenshot(path=str(OUT / "night-mobile-study.png"), full_page=True)
    box = mobile.locator("#g-sky").bounding_box(); mobile.mouse.click(box["x"] + 58.5/128*box["width"], box["y"] + 68.5/128*box["height"])
    mobile.screenshot(path=str(OUT / "night-mobile-selected.png"), full_page=True)
    mobile.locator("#g-action").click(); mobile.screenshot(path=str(OUT / "night-mobile-result.png"), full_page=True)
    primary_box = mobile.locator("#g-action").bounding_box()
    check("mobile primary action stays in the viewport after selection", mobile.locator("#g-action").is_visible()
          and primary_box["width"] >= 250 and primary_box["y"] + primary_box["height"] <= 844)
    mobile_ctx.close()
    check("no runtime errors", not errors)
    check("offline game does not request network resources", not requests)
    report = {"count": len(checks), "checks": checks, "errors": errors, "externalRequests": requests, "entry": ENTRY}
    (OUT/"night-browser.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    browser.close()
