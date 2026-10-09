#!/usr/bin/env python3
"""Артефактная группа приёмки: архивы, установщик, телефон, PDF, источники, данные.

Проверяет РЕЗУЛЬТАТЫ сборки, а не исходники:
  dist/linux.zip, dist/apple-silicon.zip, dist/phone.html, dist/print/*.pdf,
  docs/runbook.md, копия CREDITS.md и LICENSES.txt в поставке,
  контракт реальных данных app/data.js против манифеста наблюдений
  (assets/observations) и офлайн-воспроизводимость tools/generate_data.py.

Запуск (обычно из check_release.py):
  tools/check_artifacts.py [--dist DIR] [--out DIR] [--data-dump FILE] [--only-data]

Результаты: <out>/artifacts-results.json; пути для браузерной группы — <out>/paths.json.
Код выхода: 0 — все проверки прошли, 1 — есть провалы, 2 — данных для сверки нет.
"""
from __future__ import annotations

import argparse
import base64
import io
import importlib.util
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from verify_common import (APP, ASSETS_REAL, CREDITS, DIST, ROOT, CheckResults,  # noqa: E402
                           CORE_RELEASE_FILES, fresh_dir, js_runner, pdf_tools, run)

ALLOWED_EXTRA_PREFIXES = ("science-day/real/", "science-day/docs/", "science-day/fonts/")
MACHO_MAGICS = (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xce",
                b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe")


def zip_names(zf: zipfile.ZipFile) -> set[str]:
    return {i.filename for i in zf.infolist() if not i.is_dir()}


# ---------------------------------------------------------------- архивы

def check_linux_zip(res: CheckResults, dist: Path, extract_root: Path) -> Path | None:
    zpath = dist / "linux.zip"
    if not res.add("linux.zip существует", zpath.is_file(), str(zpath)):
        return None
    out = fresh_dir(extract_root / "linux")
    try:
        with zipfile.ZipFile(zpath) as zf:
            names = zip_names(zf)
            res.add("все члены лежат под science-day/, без абсолютных путей и '..'",
                    all(n.startswith("science-day/") and ".." not in n.split("/")
                        and not n.startswith("/") for n in names),
                    str(sorted(names)[:5]))
            missing = [f for f in CORE_RELEASE_FILES if f not in names]
            res.add("ядро приложения и install.sh в архиве", not missing, f"нет: {missing}")
            extras = {n for n in names
                      if n not in CORE_RELEASE_FILES
                      and n != "science-day/LICENSES.txt"
                      and not n.startswith(ALLOWED_EXTRA_PREFIXES)}
            res.add("нет файлов вне разрешённого состава (без прототипа и мусора)",
                    not extras, f"лишнее: {sorted(extras)[:10]}")
            res.add("сопроводительные файлы в поставке (CREDITS, LICENSES, runbook, real/)",
                    any(n.endswith("CREDITS.md") for n in names)
                    and any(n.endswith("LICENSES.txt") for n in names)
                    and any(n.endswith("runbook.md") for n in names)
                    and any(n.endswith(".jpg") for n in names),
                    "real JPG + CREDITS.md + LICENSES.txt + runbook.md")
            res.add("нет prototype-файлов по именам",
                    not any("prototype" in n.lower() for n in names))
            info = {i.filename: i for i in zf.infolist()}
            mode = (info["science-day/install.sh"].external_attr >> 16) & 0o777 if "science-day/install.sh" in info else 0
            res.add("install.sh помечен исполняемым в архиве (0755)",
                    bool(mode & 0o111), f"mode={oct(mode)}")
            zf.extractall(out)
    except zipfile.BadZipFile as e:
        res.add("linux.zip читается как ZIP", False, str(e))
        return None

    index = out / "science-day" / "index.html"
    if res.add("science-day/index.html извлечён", index.is_file()):
        html = index.read_text(encoding="utf-8")
        order = re.findall(r'<script[^>]+src="([^"]+)"', html)
        res.add("порядок скриптов: общие данные, модули ночной смены, оба интерфейса",
                order == ["data.js", "sky-data.js", "discovery-data.js", "content.js",
                          "model.js", "sky-map.js", "nightshift-evidence.js",
                          "nightshift-content.js", "nightshift-model.js", "nightshift-art.js",
                          "game.js", "nightshift.js"], str(order))
        styles = re.findall(r'<link\s+rel="stylesheet"\s+href="([^"]+)"', html)
        res.add("стили обоих режимов включены в порядке game, sky-map, nightshift",
                styles == ["game.css", "sky-map.css", "nightshift.css"], str(styles))
        res.add("index.html не ссылается на prototype-файлы",
                not re.search(r'(?:src|href)="[^"]*prototype', html))
    sky_js = out / "science-day" / "sky-data.js"
    if res.add("science-day/sky-data.js извлечён", sky_js.is_file()):
        sky_text = sky_js.read_text(encoding="utf-8", errors="replace")
        res.add("sky-data.js задаёт window.SKY_DATA с текстурой-dataURI",
                "window.SKY_DATA" in sky_text and "data:image" in sky_text,
                sky_text[:80])
    disc_js = out / "science-day" / "discovery-data.js"
    res.add("science-day/discovery-data.js извлечён", disc_js.is_file(), str(disc_js))
    return out / "science-day"


def check_installer(res: CheckResults, science_day: Path | None, extract_root: Path,
                    zpath: Path | None = None) -> dict:
    paths = {}
    if science_day is None:
        res.add("install.sh проверяется (есть извлечённый архив)", False, "архив не извлечён")
        return paths
    # Права исполнения сохраняет только настоящий unzip; переизвлекаем им.
    if zpath and shutil.which("unzip"):
        unzipped = fresh_dir(extract_root / "install-unzip")
        proc = run(["unzip", "-q", "-o", str(zpath), "-d", str(unzipped)], timeout=120)
        if res.add("unzip извлекает linux.zip (с правами файлов)", proc.returncode == 0,
                   proc.stderr[-200:]):
            science_day = unzipped / "science-day"
    install_sh = science_day / "install.sh"
    if not res.add("install.sh существует и исполняемый после распаковки",
                   install_sh.is_file() and os.access(install_sh, os.X_OK),
                   str(install_sh)):
        return paths
    text = install_sh.read_text(encoding="utf-8", errors="replace")
    res.add("install.sh без sudo/curl/wget/apt (офлайн, без root)",
            not re.search(r"\b(sudo|curl|wget|apt-get|apt|pip3? install|npm )\b", text))

    base = fresh_dir(extract_root / "install")

    # A: домашний каталог с пробелами, XDG_DATA_HOME не задан → путь по умолчанию.
    home_a = base / "Дом с пробелом A"
    env = dict(os.environ)
    env["HOME"] = str(home_a)
    env.pop("XDG_DATA_HOME", None)
    proc = run(["bash", "install.sh"], cwd=science_day, env=env, timeout=120)
    ok = proc.returncode == 0
    res.add("install.sh (HOME с пробелом, без аргумента) завершается успешно", ok,
            proc.stderr[-300:] if not ok else "")
    dest_a = home_a / ".local" / "share" / "science-day"
    installed_ok = all((dest_a / Path(f).relative_to("science-day")).is_file()
                       for f in CORE_RELEASE_FILES)
    res.add("файлы установлены в $HOME/.local/share/science-day", installed_ok, str(dest_a))
    desktop_a = home_a / ".local" / "share" / "applications"
    desktops = list(desktop_a.glob("*.desktop")) if desktop_a.is_dir() else []
    res.add("ярлык создан в $HOME/.local/share/applications", bool(desktops), str(desktop_a))
    if desktops:
        line = ""
        for d in desktops:
            for ln in d.read_text(encoding="utf-8", errors="replace").splitlines():
                if ln.startswith("Exec="):
                    line = ln
                    break
        target = str(dest_a / "index.html")
        points_at_target = target.replace("\\", "") in line.replace('\\"', '"').replace("\\ ", " ")
        needs_quotes = " " in target
        res.add("Exec ярлыка указывает на установленный файл и цитирует путь с пробелом",
                "science-day" in line and points_at_target
                and (needs_quotes <= (('"') in line or "\\" in line)),
                line)
    paths["installed_dir"] = str(dest_a) if installed_ok else None

    # B: явный путь назначения с пробелами.
    dest_b = base / "Путь Б" / "наука 0+"
    env_b = dict(os.environ)
    env_b["HOME"] = str(base / "дом B")
    proc_b = run(["bash", "install.sh", str(dest_b)], cwd=science_day, env=env_b, timeout=120)
    res.add("install.sh принимает путь назначения с пробелами",
            proc_b.returncode == 0 and (dest_b / "index.html").is_file(),
            proc_b.stderr[-300:] if proc_b.returncode else str(dest_b))

    # C: XDG_DATA_HOME переопределён → ярлык там.
    xdg_c = base / "xdg данные"
    env_c = dict(os.environ)
    env_c["HOME"] = str(base / "дом C")
    env_c["XDG_DATA_HOME"] = str(xdg_c)
    proc_c = run(["bash", "install.sh"], cwd=science_day, env=env_c, timeout=120)
    launcher_c = list((xdg_c / "applications").glob("*.desktop")) if xdg_c.is_dir() else []
    res.add("ярлык попадает в $XDG_DATA_HOME/applications, когда он задан",
            proc_c.returncode == 0 and bool(launcher_c), str(xdg_c / "applications"))
    return paths


def check_apple_zip(res: CheckResults, dist: Path) -> None:
    zpath = dist / "apple-silicon.zip"
    if not res.add("apple-silicon.zip существует", zpath.is_file(), str(zpath)):
        return
    try:
        with zipfile.ZipFile(zpath) as zf:
            names = zip_names(zf)
            missing = [f for f in CORE_RELEASE_FILES if f not in names]
            res.add("universal ZIP содержит то же приложение", not missing, f"нет: {missing}")
            res.add("все члены под science-day/",
                    all(n.startswith("science-day/") for n in names))
            binaries = []
            for n in names:
                head = zf.open(n).read(4)
                if head.startswith(b"\x7fELF") or head in MACHO_MAGICS:
                    binaries.append(n)
            res.add("нет ELF/Mach-O бинарников — ZIP действительно универсальный",
                    not binaries, str(binaries[:5]))
    except zipfile.BadZipFile as e:
        res.add("apple-silicon.zip читается как ZIP", False, str(e))


def check_phone_html(res: CheckResults, dist: Path) -> None:
    p = dist / "phone.html"
    if not res.add("phone.html существует", p.is_file(), str(p)):
        return
    html = p.read_text(encoding="utf-8", errors="replace")
    size = p.stat().st_size
    res.add("phone.html разумного размера (0,2–80 МиБ)", 200_000 < size < 80_000_000, f"{size} байт")
    res.add("игровые данные встроены (GAME_DATA/data:image)",
            "GAME_DATA" in html or html.count("data:image") >= 12,
            f"data:image×{html.count('data:image')}")
    res.add("карта неба встроена (SKY_DATA с текстурой-dataURI)",
            "SKY_DATA" in html and "window.SKY_DATA" in html, f"SKY_DATA={'SKY_DATA' in html}")
    res.add("истории открытий встроены (DISCOVERY_DATA)",
            "DISCOVERY_DATA" in html, f"DISCOVERY_DATA={'DISCOVERY_DATA' in html}")
    res.add("иллюстрации ночной смены встроены (NIGHTSHIFT_ART с data URI)",
            "NIGHTSHIFT_ART" in html and "data:image" in html,
            f"NIGHTSHIFT_ART={'NIGHTSHIFT_ART' in html}")
    legal_links = re.findall(r'href="(data:(?:application/zip|text/plain)[^"]+)"', html)
    try:
        payloads = {uri.split(";", 1)[0]:
                    base64.b64decode(uri.split(",", 1)[1], validate=True)
                    for uri in legal_links}
        license_text = payloads["data:text/plain"].decode("utf-8")
        with zipfile.ZipFile(io.BytesIO(payloads["data:application/zip"])) as archive:
            sources_readable = "sky-source/constellationship.fab" in archive.namelist()
        legal_ok = sources_readable and all(marker in license_text for marker in
            ("GNU GENERAL PUBLIC LICENSE", "Attribution-ShareAlike 4.0 International",
             "Free Art License"))
        legal_detail = "Встроенные ZIP и UTF-8 лицензии декодированы"
    except (KeyError, ValueError, UnicodeError, zipfile.BadZipFile) as error:
        legal_ok, legal_detail = False, str(error)
    res.add("автономные ссылки открывают исходники атласа и полные лицензии",
            legal_ok, legal_detail)
    ext = []
    if re.search(r'src\s*=\s*["\'](?:https?:)?//', html):
        ext.append("src=http(s)")
    if re.search(r'href\s*=\s*["\']https?:', html):
        ext.append("href=http(s)")
    if re.search(r'url\(\s*["\']?\s*(?:https?:)?//', html):
        ext.append("url(http)")
    if re.search(r'\bfetch\s*\(', html):
        ext.append("fetch(")
    if re.search(r'<script[^>]+src\s*=\s*["\'](?!data:)[^"\']+["\']', html):
        ext.append("внешний <script src>")
    if re.search(r'<link[^>]+href\s*=\s*["\'](?!data:)[^"\']+["\']', html):
        ext.append("внешний <link href>")
    res.add("полностью автономен: нет внешних ссылок, стилей, скриптов и fetch",
            not ext, str(ext))


def _pdf_pages_text(pdf: Path, total: int) -> dict[int, str]:
    """Текст постранично, с нормализованными пробелами."""
    pages = {}
    for p in range(1, total + 1):
        out = run(["pdftotext", "-f", str(p), "-l", str(p), str(pdf), "-"], timeout=120).stdout
        pages[p] = " ".join(out.split())
    return pages


def _pdf_numbers(txt: str) -> list[float]:
    """Все числа из текста PDF: минус U+2212, запятая как десятичный разделитель."""
    vals = []
    for t in re.findall(r"[−-]?\d+(?:[.,]\d+)?", txt):
        try:
            vals.append(float(t.replace("−", "-").replace(",", ".")))
        except ValueError:
            continue
    return vals


def check_pdfs(res: CheckResults, dist: Path, out: Path, with_pdftotext: bool,
               dump_path: Path) -> None:
    print_dir = dist / "print"
    render_dir = fresh_dir(out / "pdf")
    import numpy as np
    from PIL import Image

    dump = None
    if dump_path.is_file():
        try:
            dump = json.loads(dump_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            dump = None

    for name in ("presenter", "ranking", "cards"):
        p = print_dir / f"{name}.pdf"
        if not res.add(f"print/{name}.pdf существует", p.is_file(), str(p)):
            continue
        res.add(f"{name}.pdf начинается с %PDF", p.read_bytes()[:4] == b"%PDF")
        try:
            info = run(["pdfinfo", str(p)], timeout=120, check=True).stdout
        except Exception as e:
            res.add(f"{name}.pdf разбирается pdfinfo", False, str(e))
            continue
        pages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
        res.add(f"{name}.pdf: ≥1 страница, без шифрования",
                pages >= 1 and bool(re.search(r"^Encrypted:\s+no\s*$", info, re.MULTILINE)),
                f"pages={pages}")
        ppm = run(["pdftoppm", "-png", "-r", "60", "-f", "1",
                   "-l", "2" if pages >= 2 else "1", str(p), str(render_dir / name)],
                  timeout=180)
        rendered = sorted(render_dir.glob(f"{name}-*.png"))
        res.add(f"{name}.pdf рендерится pdftoppm", ppm.returncode == 0 and bool(rendered),
                ppm.stderr[-200:])
        for img_path in rendered:
            arr = np.asarray(Image.open(img_path).convert("L"), dtype=float)
            res.add(f"{name}.pdf: страница {img_path.name} не пустая (есть контраст)",
                    8 < arr.std() < 130 and 2 < arr.mean() < 253,
                    f"std={arr.std():.1f} mean={arr.mean():.1f}")

    if not with_pdftotext:
        res.add("pdftotext доступен для содержательных проверок печати", False, "нет poppler-utils")
        return
    if dump is None:
        res.add("дамп данных приложен для содержательных проверок печати", False, str(dump_path))
        return

    contact = dump["contact"]
    names = [" ".join(c["name"].split()) for c in contact]
    scores = [float(c["score"]) for c in contact]
    expl = [" ".join(c["explanation"].split())[:30] for c in contact]
    obs_dates = sorted({o["date"][:10]
                        for c in contact for o in c.get("observations", []) if o.get("date")})

    # --- ranking.pdf: рейтинг АЛГОРИТМА, сортировка по счёту, колонки порогов 1/3 ---
    rank_txt = " ".join(run(["pdftotext", str(print_dir / "ranking.pdf"), "-"],
                            timeout=120).stdout.split())
    nums = _pdf_numbers(rank_txt)
    first_pos = {}
    for i, v in enumerate(nums):
        for s in scores:
            if s not in first_pos and abs(v - s) <= 0.005:
                first_pos[s] = i
    found_scores = [s for s in scores if s in first_pos]
    res.add("ranking.pdf: счёты участков совпадают с данными (12 из 12)",
            len(found_scores) == len(scores),
            f"совпало {len(found_scores)}/{len(scores)}")
    if len(found_scores) == len(scores):
        order = [first_pos[s] for s in sorted(found_scores, reverse=True)]
        res.add("ranking.pdf: счёты идут по убыванию (реальная сортировка рейтинга)",
                all(a <= b for a, b in zip(order, order[1:])),
                f"позиции в тексте: {order}")
    res.add("ranking.pdf: колонки порогов обозначены (порог/мягкий/строгий)",
            any(k in rank_txt.lower() for k in ("порог", "мягк", "сторг")),
            rank_txt[:120])
    res.add("ranking.pdf: без командного соревнования",
            not re.search(r"команд|лидерборд", rank_txt, re.I),
            "найдено слово о командах" if re.search(r"команд|лидерборд", rank_txt, re.I) else "")

    # --- cards.pdf: страницы игрока только с 2 кадрами и без ответов; ответы — вырезки позже ---
    cards = print_dir / "cards.pdf"
    cinfo = run(["pdfinfo", str(cards)], timeout=120, check=True).stdout
    ctotal = int(re.search(r"Pages:\s+(\d+)", cinfo).group(1))
    cpages = _pdf_pages_text(cards, ctotal)
    joined = " ".join(cpages.values())

    def page_has_answer(txt: str) -> bool:
        return any(f in txt for f in expl)

    first_ans = next((p for p in sorted(cpages) if page_has_answer(cpages[p])), None)
    res.add("cards.pdf: страницы игрока идут до вырезок, вырезки с ответами присутствуют",
            first_ans is not None and first_ans > 1,
            f"первая страница с ответом: {first_ans} из {ctotal}")
    if first_ans is not None:
        player_txt = " ".join(cpages[p] for p in cpages if p < first_ans)
        missing_names = [n for n in names if n not in player_txt]
        res.add("cards.pdf: все 12 участков на страницах игрока (по именам)",
                not missing_names, f"нет: {missing_names[:3]}")
        res.add("cards.pdf: у вырезок те же имена участков (соответствие id)",
                all(n in joined for n in names),
                f"нет в вырезках: {[n for n in names if n not in joined][:3]}")

    # --- cards.pdf: подписи кадров групп несут фактические даты наблюдений ---
    if first_ans is not None:
        player_txt = " ".join(cpages[p] for p in cpages if p < first_ans)
        cut_txt = " ".join(cpages[p] for p in cpages if p >= first_ans)
        miss_player, miss_cut = [], []
        for c in contact:
            ds = [o.get("date", "")[:10] for o in c.get("observations", [])]
            if len(ds) != 3:
                miss_player.append(f"{c['id']}: наблюдений не 3")
                continue
            for d in ds[:2]:
                if d not in player_txt:
                    miss_player.append(f"{c['id']} кадр1-2: {d}")
            if ds[2] not in cut_txt:
                miss_cut.append(f"{c['id']} кадр3: {ds[2]}")
        res.add("cards.pdf: даты кадров 1–2 напечатаны на карточках групп",
                not miss_player, f"нет: {miss_player[:4]}")
        res.add("cards.pdf: дата доп-наблюдения (кадр 3) напечатана в вырезках ведущего",
                not miss_cut, f"нет: {miss_cut[:4]}")

    # --- presenter.pdf: атрибуции настоящих снимков обязательны дословно ---
    pres_txt = " ".join(run(["pdftotext", str(print_dir / "presenter.pdf"), "-"],
                            timeout=120).stdout.split())
    res.add("печатный справочник ведущего несёт атрибуции (ESA/Hubble, STScI)",
            ("ESA/Hubble" in pres_txt or "esahubble" in pres_txt) and "STScI" in pres_txt,
            f"ESA/Hubble={'ESA/Hubble' in pres_txt}, STScI={'STScI' in pres_txt}")
    missing_pdates = [dt for dt in obs_dates if dt not in pres_txt]
    res.add("presenter.pdf: даты всех наблюдений участков в таблице ключа",
            obs_dates and not missing_pdates, f"нет: {missing_pdates[:4]}")
    acks = ((dump.get("meta") or {}).get("acknowledgments") or {})
    if acks:
        norm = " ".join(pres_txt.split())
        missing_ack = [k for k, v in acks.items()
                       if " ".join(str(v).split())[:40] not in norm]
        res.add("presenter.pdf: благодарности обзора (meta.acknowledgments) дословно",
                not missing_ack, f"нет: {missing_ack}")


def check_sky_source(res: CheckResults, science_day: Path | None) -> None:
    """sky-source.zip: исходники покрытых лицензиями данных атласа в поставке."""
    zpath = science_day / "sky-source.zip" if science_day else None
    if not res.add("sky-source.zip в поставке", bool(zpath and zpath.is_file()),
                   str(zpath)):
        return
    try:
        with zipfile.ZipFile(zpath) as zf:
            names = set(zip_names(zf))
            need = {"sky-source/constellationship.fab", "sky-source/manifest.json",
                    "sky-source/prepare_sky.py", "sky-source/prepare_demo.py",
                    "sky-source/observations-manifest.json"}
            res.add("sky-source.zip несёт исходники атласа, рецепты данных и манифесты",
                    need <= names, f"нет: {sorted(need - names)[:3]}")
            res.add("sky-source.zip содержит переводы/имена (.po/.fab)",
                    any(n.startswith("sky-source/") and (n.endswith(".po") or n.endswith(".fab"))
                        for n in names - need), str(sorted(names)[:8]))
    except zipfile.BadZipFile as e:
        res.add("sky-source.zip читается как ZIP", False, str(e))
    lic = science_day / "LICENSES.txt"
    if res.add("LICENSES.txt в поставке", lic.is_file(), str(lic)):
        text = lic.read_text(encoding="utf-8", errors="replace")
        for marker, title in (("GNU GENERAL PUBLIC LICENSE", "GPL-2.0"),
                              ("Attribution-ShareAlike 4.0 International", "CC BY-SA 4.0"),
                              ("Free Art License", "FAL")):
            res.add(f"LICENSES.txt: полный текст {title}", marker in text,
                    f"«{marker}»={'есть' if marker in text else 'НЕТ'}")


def check_credits(res: CheckResults, science_day: Path | None) -> None:
    if not res.add("исходный CREDITS.md на месте", CREDITS.is_file()):
        return
    src = CREDITS.read_text(encoding="utf-8")
    attrs = [ln[len("- Атрибуция:"):].strip() for ln in src.splitlines()
             if ln.startswith("- Атрибуция:")]
    urls = re.findall(r"https://\S+?(?=[)\s]|$)", src)
    res.add("в CREDITS.md есть 3 атрибуции", len(attrs) >= 3, f"{len(attrs)}")
    if science_day is None:
        res.add("копия CREDITS.md в поставке", False, "архив не извлечён")
        return
    copies = list(science_day.rglob("CREDITS.md"))
    if res.add("копия CREDITS.md в поставке", bool(copies)):
        res.add("копия CREDITS.md дословная",
                copies[0].read_text(encoding="utf-8") == src, str(copies[0]))
    # LICENSES.txt проверяет check_sky_source (наличие + полные тексты лицензий).
    blob = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                     for p in science_day.rglob("*") if p.is_file()
                     and p.suffix in {".md", ".txt", ".html", ".js"} and p.stat().st_size < 2_000_000)
    missing = [u for u in urls if u not in blob]
    res.add("источники (heic2407a/heic2018a/news-2023-010) сохранены в поставке",
            not missing, f"потеряны: {missing}")


def check_docs(res: CheckResults) -> None:
    rb = ROOT / "docs" / "runbook.md"
    ok = rb.is_file() and len(rb.read_text(encoding="utf-8", errors="replace")) > 200
    res.add("docs/runbook.md собран и содержател (>200 знаков)", ok, str(rb))
    if ok:
        txt = rb.read_text(encoding="utf-8", errors="replace")
        res.add("runbook описывает установку (install.sh / science-day)",
                "install.sh" in txt or "science-day" in txt)


# ---------------------------------------------------------------- реальные данные и происхождение

ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _sha256_file(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_data_real(res: CheckResults, dump_path: Path) -> None:
    """Контракт РЕАЛЬНЫХ данных: происхождение (манифест наблюдений), координаты,
    три датированных наблюдения из разных FITS, детекторные метаданные.
    Генераторных сидов и синтетических инвариантов больше нет."""
    if not res.add("дамп данных приложен (--data-dump)", dump_path.is_file(), str(dump_path)):
        raise SystemExit(2)
    d = json.loads(dump_path.read_text(encoding="utf-8"))
    regenerated = dump_path.parent / "tmp" / "regenerated-data.js"
    regenerated.parent.mkdir(parents=True, exist_ok=True)
    generation = run([sys.executable, str(TOOLS / "generate_data.py"),
                      "--out", str(regenerated)], timeout=900)
    res.add("CLI generate_data.py воспроизводит app/data.js байт-в-байт офлайн (кэш+манифест)",
            generation.returncode == 0 and regenerated.is_file()
            and regenerated.read_bytes() == (APP / "data.js").read_bytes(),
            generation.stderr[-200:])
    meta = d["meta"]

    res.add("meta: synthetic=false, precomputed=true — реальные снимки, счёт рассчитан заранее",
            meta.get("synthetic") is False and meta.get("precomputed") is True,
            json.dumps({k: meta.get(k) for k in ("synthetic", "precomputed")}, default=str))
    _th = meta.get("thresholds") or {}
    res.add("meta: пороги soft=1.0 strict=3.0 и формула счёта сохранены",
            _th.get("soft") == 1.0 and _th.get("strict") == 3.0
            and isinstance(meta.get("score_formula"), str) and len(meta.get("score_formula") or "") > 5,
            json.dumps({"thresholds": _th, "score_formula": meta.get("score_formula")}, default=str)[:200])
    tr = meta.get("training") or {}
    res.add("meta.training: 300 реальных строк, правило патчей, дайджест sha256",
            tr.get("n_rows") == 300 and isinstance(tr.get("rule"), str) and bool(tr["rule"])
            and bool(re.fullmatch(r"[0-9a-f]{64}", tr.get("digest") or "")),
            json.dumps(tr, default=str)[:200])
    ds = meta.get("dataset") or {}
    manifest = ROOT / (ds.get("manifest") or "assets/observations/manifest.json")
    if res.add("манифест наблюдений существует (meta.dataset.manifest)", manifest.is_file(), str(manifest)):
        res.add("meta.dataset.manifest_sha256 совпадает с фактическим SHA256 манифеста",
                _sha256_file(manifest) == ds.get("manifest_sha256"),
                f"meta={str(ds.get('manifest_sha256'))[:16]}…")
    res.add("meta.dataset: обзор и конвейер названы",
            bool(ds.get("survey")) and bool(ds.get("pipeline")),
            json.dumps({k: ds.get(k) for k in ("survey", "pipeline")}, default=str)[:160])
    ack = meta.get("acknowledgments")
    res.add("meta.acknowledgments: дословные благодарности ZTF/IRSA на месте",
            isinstance(ack, dict) and bool(ack)
            and all(isinstance(v, str) and len(v) > 10 for v in ack.values()),
            str(list(ack or {}))[:160])

    contact = d["contact"]
    res.add("contact: 12 уникальных id", len(contact) == 12
            and len({c["id"] for c in contact}) == 12, str([c["id"] for c in contact]))
    res.add("shortIds: 6 уникальных id из контактного листа",
            len(d["shortIds"]) == 6 and set(d["shortIds"]) <= {c["id"] for c in contact},
            str(d["shortIds"]))
    from collections import Counter
    comp = meta.get("composition")
    if isinstance(comp, dict) and comp:
        res.add("контакт: состав типов совпадает с meta.composition",
                dict(Counter(c["type"] for c in contact)) == {k: int(v) for k, v in comp.items()},
                f"{comp} против {dict(Counter(c['type'] for c in contact))}")
    else:
        res.add("контакт: состав типов зафиксирован в meta.composition", False, f"meta.composition={comp!r}")
    short_comp = meta.get("short_composition")
    if isinstance(short_comp, dict) and short_comp:
        by_id = {c["id"]: c["type"] for c in contact}
        res.add("shortIds: состав типов совпадает с meta.short_composition",
                dict(Counter(by_id[i] for i in d["shortIds"])) == {k: int(v) for k, v in short_comp.items()},
                f"{short_comp} против {dict(Counter(by_id[i] for i in d['shortIds']))}")
    else:
        res.add("shortIds: состав типов зафиксирован в meta.short_composition",
                False, f"meta.short_composition={short_comp!r}")

    def _case_real(c) -> str | None:
        """None — участок соответствует контракту реальных данных, иначе текст проблемы."""
        expected = {"normal": "stable", "mover": "sky", "variable": "sky",
                    "artifact": "artifact", "weak": "sky", "weak_mid": "sky",
                    "unresolved": "uncertain"}
        if c.get("type") not in expected or c.get("expectedVerdict") != expected[c["type"]]:
            return "научный вердикт отсутствует или не соответствует типу участка"
        try:
            ra, dec = float(c["ra"]), float(c["dec"])
        except (KeyError, TypeError, ValueError):
            return "нет ra/dec"
        if not (0.0 <= ra < 360.0 and -90.0 <= dec <= 90.0):
            return f"ra/dec вне диапазона: {ra}, {dec}"
        obs = c.get("observations")
        if not isinstance(obs, list) or len(obs) != 3:
            return "observations не 3"
        dates = [o.get("date") for o in obs]
        if not all(isinstance(t, str) and ISO_UTC.fullmatch(t) for t in dates):
            return "даты не ISO UTC"
        if len(set(dates)) != 3:
            return f"даты не различаются: {dates}"
        srcs = [o.get("source") for o in obs]
        if not all(isinstance(s, str) and s.startswith("https://") for s in srcs):
            return "у наблюдений нет https-источников FITS"
        if len(set(srcs)) != 3:
            return "наблюдения ссылаются на один файл — третьего независимого кадра нет"
        for o in obs:
            if not (isinstance(o.get("filter"), str) and o["filter"]
                    and isinstance(o.get("exposure"), (int, float)) and o["exposure"] > 0
                    and isinstance(o.get("mjd"), (int, float))):
                return f"неполное наблюдение: {json.dumps(o, default=str)[:120]}"
        s = c.get("source") or {}
        if not (isinstance(s.get("label"), str) and s["label"]
                and isinstance(s.get("url"), str) and s["url"].startswith("https://")
                and isinstance(s.get("credit"), str) and len(s["credit"]) > 10):
            return "source{label,url,credit} неполон"
        if not (isinstance(c.get("evidence"), str) and len(c["evidence"]) > 10
                and isinstance(c.get("limitations"), str) and len(c["limitations"]) > 10):
            return "evidence/limitations пусты"
        ph = c.get("photometry")
        if ph is not None:
            if not (isinstance(ph.get("note"), str) and ph["note"]
                    and isinstance(ph.get("epochs"), list) and len(ph["epochs"]) == 3):
                return "photometry задан, но неполон"
        return None

    problems = [msg for msg in (_case_real(c) for c in contact) if msg]
    res.add("контакт: у всех 12 участков ra/dec, 3 разных датированных наблюдения из разных FITS, "
            "источник, доказательства и ограничения",
            not problems, "; ".join(problems[:4]))
    demo = d.get("demo_cases") or []
    if res.add("дамп несёт демо-набор из 200 реальных полей с координатами и датами",
               len(demo) == 200 and all(_case_real(c) is None for c in demo), f"demo={len(demo)}"):
        res.add("демо: id идут по порядку d001…d200",
                d["demo_ids"] == [f"d{i:03d}" for i in range(1, 201)], str(d["demo_ids"][:5]))

    # Обучающая статистика детектора: внутренняя согласованность meta.
    import numpy as np
    mts = meta.get("train_stats") or {}
    if res.add("meta.train_stats содержит medians/p99/rows", {"medians", "p99", "rows"} <= set(mts),
               str(list(mts))):
        rows = np.asarray(mts["rows"], dtype=float)
        med = np.asarray(mts["medians"], dtype=float)
        p99 = np.asarray(mts["p99"], dtype=float)
        res.add("train_stats: строки 300×3; medians/p99 согласованы с этими строками",
                rows.shape == (300, 3) and med.shape == (3,) and p99.shape == (3,)
                and bool(np.all(np.abs(np.median(rows, axis=0) - med) <= 0.005))
                and bool(np.all(np.abs(np.percentile(rows, 99, axis=0) - p99) <= 0.005)),
                f"shape={rows.shape}, medians={np.round(med, 3).tolist()}, p99={np.round(p99, 3).tolist()}")


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="Артефактная группа приёмки")
    ap.add_argument("--dist", default=str(DIST))
    ap.add_argument("--out", default=str(ROOT / "verification"))
    ap.add_argument("--data-dump", default="")
    ap.add_argument("--only-data", action="store_true",
                    help="только контракт реальных данных и их происхождение")
    args = ap.parse_args()
    dist = Path(args.dist)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    extract_root = fresh_dir(out / "tmp" / "extract")

    dump = Path(args.data_dump) if args.data_dump else out / "data-dump.json"
    paths = {}
    if not args.only_data:
        pdftotext, _ = pdf_tools()
        if not dump.is_file():
            runner = js_runner()
            if runner and (APP / "data.js").is_file():
                try:
                    run(runner + [str(TOOLS / "check_model.mjs"), "--dump", str(dump)],
                        cwd=ROOT, timeout=300, check=True)
                except (RuntimeError, subprocess.TimeoutExpired) as e:
                    print(f"дамп данных не создан: {e}", file=sys.stderr)
        res_zip = CheckResults("Архив linux.zip")
        science_day = check_linux_zip(res_zip, dist, extract_root)
        res_zip.dump(out / "artifacts-linux-zip.json")

        res_inst = CheckResults("Установщик install.sh")
        paths = check_installer(res_inst, science_day, extract_root, dist / "linux.zip")
        res_inst.dump(out / "artifacts-installer.json")

        res_apple = CheckResults("Архив apple-silicon.zip")
        check_apple_zip(res_apple, dist)
        res_apple.dump(out / "artifacts-apple-zip.json")

        res_phone = CheckResults("Автономный phone.html")
        check_phone_html(res_phone, dist)
        res_phone.dump(out / "artifacts-phone.json")

        res_pdf = CheckResults("Печатный комплект PDF")
        check_pdfs(res_pdf, dist, out, pdftotext, dump)
        res_pdf.dump(out / "artifacts-pdf.json")

        res_cr = CheckResults("Атрибуции и лицензии")
        check_credits(res_cr, science_day)
        res_cr.dump(out / "artifacts-credits.json")

        res_sky = CheckResults("Исходники атласа и тексты лицензий")
        check_sky_source(res_sky, science_day)
        res_sky.dump(out / "artifacts-sky-source.json")

        res_docs = CheckResults("Документация поставки")
        check_docs(res_docs)
        res_docs.dump(out / "artifacts-docs.json")

    res_data = CheckResults("Данные и происхождение реальных наблюдений")
    if not dump.is_file():
        runner = js_runner()
        if runner and (APP / "data.js").is_file():
            try:
                run(runner + [str(TOOLS / "check_model.mjs"), "--dump", str(dump)],
                    cwd=ROOT, timeout=300, check=True)
            except (RuntimeError, subprocess.TimeoutExpired) as e:
                res_data.add("дамп данных создаётся из app/data.js", False, str(e)[-300:])
    try:
        check_data_real(res_data, dump)
    except SystemExit as e:
        res_data.dump(out / "artifacts-data.json")
        return 2 if e.code == 2 else 1
    res_data.dump(out / "artifacts-data.json")

    (out / "paths.json").write_text(json.dumps(paths, ensure_ascii=False, indent=1), encoding="utf-8")

    groups = [res_data] if args.only_data else [
        res_zip, res_inst, res_apple, res_phone, res_pdf, res_cr, res_sky, res_docs,
        res_data]
    failed = [g for g in groups if not g.ok]
    print(f"\nАРТЕФАКТЫ {'OK' if not failed else 'ПРОВАЛ'}: "
          f"групп {len(groups)}, проваленных {len(failed)}: {[g.title for g in failed]}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
