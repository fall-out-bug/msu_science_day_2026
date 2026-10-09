#!/usr/bin/env python3
"""Сборка полной поставки «Архив неизвестного».

  python3 tools/build_release.py              # полная сборка (нужны файлы app/)
  python3 tools/build_release.py --data-only  # только app/data.js + app/real (ранняя интеграция)

Что делает полная сборка:
  1. Регенерирует app/data.js через tools/generate_data.py — офлайн из проверяемого
     кэша реальных наблюдений assets/observations (манифест + SHA256), без сети.
  2. Копирует реальные фотографии assets/real/*.jpg и CREDITS.md в app/real/.
  3. Собирает stage science-day/ только из разрешённого списка файлов приложения
     (index.html, game.css, game.js, model.js, sky-map.js, sky-map.css, sky-data.js,
     discovery-data.js, data.js, content.js, nightshift-*.js, nightshift.js,
     nightshift.css) + real/ + install.sh + docs/runbook.md
     + LICENSES.txt. Файлы прототипов в поставку не попадают никогда.
  4. dist/linux.zip и dist/apple-silicon.zip — один и тот же платформенно-независимый
     пакет с префиксом science-day/ (без заявки на .app и без бинарников).
  5. dist/phone.html — автономная страница: все CSS/JS/изображения/данные встроены,
     включая sky-data.js (карта неба) и discovery-data.js (открытия); ссылки
     real/<файл> подменяются data URI. Сборка падает, если остаются внешние
     ссылки, fetch() или не встроенные данные.
  6. dist/print/{presenter,ranking,cards}.pdf — печатный комплект (tools/print_kit.py)
     с фактическими датами, фильтрами и благодарностями обзора.

Записи ZIP имеют фиксированные метки времени и сортировку — сборка воспроизводима.
Зависимости: numpy, Pillow, reportlab (tools/requirements.txt); DejaVu Sans —
системный пакет fonts-dejavu-core (для PDF).
"""
import argparse
import base64
import re
import shutil
import sys
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import generate_data  # noqa: E402
import print_kit      # noqa: E402

APP_FILES = ["index.html", "game.css", "game.js", "model.js",
             "sky-map.js", "sky-map.css", "sky-data.js", "discovery-data.js",
             "data.js", "content.js", "nightshift-evidence.js", "nightshift-content.js",
             "nightshift-model.js", "nightshift-art.js", "nightshift.js", "nightshift.css"]
SCRIPT_ORDER = ["data.js", "sky-data.js", "discovery-data.js", "content.js",
                "model.js", "sky-map.js", "nightshift-evidence.js", "nightshift-content.js",
                "nightshift-model.js", "nightshift-art.js", "game.js", "nightshift.js"]
CSS_FILES = ["game.css", "sky-map.css", "nightshift.css"]
REAL_DIR = "assets/real"
ZIP_DATE = (2026, 10, 1, 12, 0, 0)  # фиксированная метка: воспроизводимые архивы

# Исходники покрытых лицензиями данных атласа и конвейера обработки снимков —
# фактически поставляемые файлы (без «письменных предложений источника»).
SKY_SOURCE_MEMBERS = ("constellationship.fab", "constellation_names.eng.fab",
                      "star_names.fab", "skycultures_ru.po", "stellarium_ru.po",
                      "info.ini")
# Обработка игровых данных: рецепты, провенанс и зависимости
# (репродукция встроенных PNG). Отсутствие любого файла — ошибка сборки.
GAME_SOURCE_FILES = (
    ("tools/prepare_demo.py", "sky-source/prepare_demo.py"),
    ("tools/prepare_curated.py", "sky-source/prepare_curated.py"),
    ("tools/prepare_discoveries.py", "sky-source/prepare_discoveries.py"),
    ("tools/import_observations.py", "sky-source/import_observations.py"),
    ("tools/generate_data.py", "sky-source/generate_data.py"),
    ("tools/field_context.py", "sky-source/field_context.py"),
    ("tools/realdata.py", "sky-source/realdata.py"),
    ("tools/requirements.txt", "sky-source/requirements.txt"),
    ("assets/observations/demo-provenance.json", "sky-source/demo-provenance.json"),
    ("assets/observations/curated-provenance.json", "sky-source/curated-provenance.json"),
    ("assets/observations/manifest.json", "sky-source/observations-manifest.json"),
    ("assets/discoveries/provenance.json", "sky-source/discoveries-provenance.json"),
)
LICENSE_TEXTS = (("GNU General Public License v2", "GPL-2.0.txt"),
                 ("Creative Commons Attribution-ShareAlike 4.0 International",
                  "CC-BY-SA-4.0.txt"),
                 ("Free Art License", "FAL-1.3.txt"))


def licenses_text(data) -> str:
    """Лицензии и происхождение поставки; фактические данные берутся из meta."""
    m = data.get("meta") or {}
    ds = m.get("dataset") or {}
    tr = m.get("training") or {}
    survey = ds.get("survey") or "обзор наблюдений"
    lines = [
        "ЛИЦЕНЗИИ И ИСТОЧНИКИ ПОСТАВКИ «Архив неизвестного»",
        "==================================================",
        "",
        "1. Снимки игры — настоящие научные наблюдения (" + survey + ").",
    ]
    if ds.get("pipeline"):
        lines.append("   Конвейер подготовки: " + ds["pipeline"]
                     + " (tools/generate_data.py офлайн из кэша observations).")
    if ds.get("manifest"):
        lines.append("   Происхождение кадров (URL, даты, выдержки, SHA256 FITS): "
                     + str(ds["manifest"])
                     + (f" (sha256 {ds['manifest_sha256'][:16]}…) "
                        if ds.get("manifest_sha256") else ""))
    if tr.get("n_rows"):
        lines.append(f"   Обучение детектора: {tr['n_rows']} строк реальных наблюдений; "
                     "оценки рассчитаны заранее (meta.precomputed), формула — meta.score_formula.")
    lines += [
        "",
        "2. Благодарности обзора данных (дословно, воспроизводить при публикации):",
    ]
    for v in (m.get("acknowledgments") or {}).values():
        lines.append("   " + str(v))
    lines += [
        "",
        "3. Звёздные данные (sky-data.js):",
        "   • Текстура: NASA SVS, «Deep Star Maps 2020» (https://svs.gsfc.nasa.gov/4851,",
        "     файл starmap_2020_8k.exr) — каталожная визуализация Hipparcos-2,",
        "     Tycho-2 и Gaia DR2, не фотография. Контент NASA не защищён авторским",
        "     правом (NASA Media Usage Guidelines); атрибуция — в real/CREDITS.md",
        "     и на карте.",
        "   • Звёзды (оверлей): каталог HYG v4.1 (https://github.com/astronexus/hyg-database),",
        "     лицензия CC BY-SA 4.0 — производный набор звёзд распространяется на тех же",
        "     условиях CC BY-SA 4.0.",
        "   • Линии и русские названия созвездий: планетарий Stellarium, skyculture",
        "     «western» (constellationship.fab, constellation_names.eng.fab, ru.po):",
        "     данные — CC BY-SA 4.0 + Free Art License (по info.ini skyculture),",
        "     переводы ru.po — GPL-2.0+. Исходные файлы — в sky-source.zip поставки;",
        "     полные тексты лицензий — в конце этого файла.",
        "   • Сборка: tools/prepare_sky.py из кэша assets/sky (манифест с URL и sha256).",
        "",
        "4. Данные открытий (discovery-data.js): кривая блеска Кеплера-90 — архив MAST",
        "   (STScI), снимки миссии NASA «Kepler»; кадры SN 2023tyk — настоящие продукты",
        "   ZTF/IRSA (sciimg и scimrefdiffimg). График и кадры — наша производная",
        "   обработка архивных измерений (не рисунки из публикаций). URL, хэши и",
        "   примечания об обработке дословно — в real/CREDITS.md и",
        "   assets/discoveries/provenance.json.",
        "",
        "5. Реальные фотографии экрана «Из настоящих наблюдений» — см. real/CREDITS.md",
        "   (копия assets/real/CREDITS.md): ESA/Hubble — лицензия CC BY 4.0,",
        "   STScI — public domain. Атрибуция обязательна и воспроизводится дословно",
        "   на экране и в печати.",
        "",
        "6. Шрифт печатного комплекта (PDF в папке print) — DejaVu Sans",
        "   (https://dejavu-fonts.github.io). Свободная лицензия Bitstream Vera/DejaVu:",
        "   использование, изменение и встраивание в документы разрешены; в PDF встроены",
        "   подмножества. Текст лицензии: пакет fonts-dejavu-core",
        "   (/usr/share/doc/fonts-dejavu-core/copyright) или",
        "   https://dejavu-fonts.github.io/License",
        "",
        "7. Шрифты интерфейса — системный стек (файловые шрифты в поставку не входят).",
        "",
        "8. Данные: window.GAME_DATA (data.js), window.SKY_DATA (sky-data.js) и",
        "   window.DISCOVERY_DATA (discovery-data.js) собираются офлайн из",
        "   проверяемого кэша; сеть при сборке и игре не используется. Исходные файлы",
        "   покрытых лицензиями данных атласа поставляются в sky-source.zip (рядом с",
        "   этой папкой); полные тексты лицензий — в конце этого файла.",
    ]
    return "\n".join(lines) + "\n"


def write_licenses_txt(repo_root, data) -> Path:
    """app/LICENSES.txt: сводка происхождения + полные тексты лицензий.

    Один и тот же файл идёт в app/ (разработка, file://) и в поставку.
    Тексты лицензий обязательны: их отсутствие — ошибка сборки.
    """
    parts = [licenses_text(data)]
    for title, fname in LICENSE_TEXTS:
        p = repo_root / "assets" / "sky" / "licenses" / fname
        if not p.is_file():
            raise SystemExit(f"build_release: нет обязательного текста лицензии "
                             f"assets/sky/licenses/{fname} ({title})")
        parts.append("\n\n" + "-" * 74 + f"\n{title}\n" + "-" * 74 + "\n\n" + p.read_text(encoding="utf-8", errors="replace"))
    out = repo_root / "app" / "LICENSES.txt"
    out.write_text("".join(parts) + "\n", encoding="utf-8")
    log(f"  LICENSES.txt: {out.stat().st_size / 1024:.0f} КиБ (сводка + полные тексты)")
    return out


def build_sky_source_zip(repo_root, app_dir) -> Path:
    """app/sky-source.zip: исходники данных атласа и конвейера снимков.

    Состав: файлы skyculture «western», манифест и prepare_sky.py (атлас),
    а также рецепты обработки игровых данных — prepare_demo.py,
    import_observations.py, generate_data.py, demo-provenance.json и
    манифест наблюдений. Метки фиксированы — архив воспроизводим.
    """
    src = repo_root / "assets" / "sky" / "src"
    out = app_dir / "sky-source.zip"
    members: list[tuple[str, bytes]] = []
    missing: list[str] = []
    for name in SKY_SOURCE_MEMBERS:
        p = src / name
        if p.is_file():
            members.append((f"sky-source/{name}", p.read_bytes()))
        else:
            missing.append(f"assets/sky/src/{name}")
    man = repo_root / "assets" / "sky" / "manifest.json"
    if man.is_file():
        members.append(("sky-source/manifest.json", man.read_bytes()))
    else:
        missing.append("assets/sky/manifest.json")
    prep = repo_root / "tools" / "prepare_sky.py"
    if prep.is_file():
        members.append(("sky-source/prepare_sky.py", prep.read_bytes()))
    else:
        missing.append("tools/prepare_sky.py")
    for rel, arc in GAME_SOURCE_FILES:
        p = repo_root / rel
        if p.is_file():
            members.append((arc, p.read_bytes()))
        else:
            missing.append(rel)
    if missing:
        raise SystemExit("sky-source.zip: отсутствуют обязательные исходники "
                         f"(запустите prepare-скрипты): {', '.join(missing)}")
    members.sort()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for arc, blob in members:
            info = zipfile.ZipInfo(arc, date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o644 << 16) | 0o100000
            info.create_system = 3
            z.writestr(info, blob)
    log(f"  sky-source.zip: {len(members)} файлов, {out.stat().st_size / 1024:.0f} КиБ")
    return out


def log(msg):
    print(msg, flush=True)


def write_data_js(app_dir):
    """Регенерирует app/data.js из генератора реальных наблюдений (кэш + манифест)."""
    data, images = generate_data.build_game_data()
    out = app_dir / "data.js"
    out.write_text(generate_data.render_js(data), encoding="utf-8")
    ds = (data.get("meta") or {}).get("dataset") or {}
    log(f"  data.js: {len(data['contact'])} участков + {len(data.get('demo') or [])} демо-полей, "
        f"{out.stat().st_size / 1024:.0f} КиБ"
        + (f", обзор {ds['survey']}" if ds.get("survey") else ""))
    return data, images


def sync_real(app_dir, repo_root):
    """Копирует реальные снимки и CREDITS.md в app/real (для разработки и поставки)."""
    src, dst = repo_root / REAL_DIR, app_dir / "real"
    dst.mkdir(parents=True, exist_ok=True)
    copied = []
    for f in sorted(src.iterdir()):
        if f.is_file():
            shutil.copyfile(f, dst / f.name)
            copied.append(f.name)
    log(f"  real/: {', '.join(copied)}")
    return dst


def stage_release(app_dir, repo_root, stage):
    """Собирает science-day/ строго из разрешённого списка."""
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "docs").mkdir(parents=True)
    missing = [f for f in APP_FILES if not (app_dir / f).is_file()]
    if missing:
        raise SystemExit("В app/ нет файлов (завершите интеграцию или используйте "
                         f"--data-only): {', '.join(missing)}")
    for f in APP_FILES:
        shutil.copyfile(app_dir / f, stage / f)
    shutil.copytree(app_dir / "real", stage / "real")
    shutil.copyfile(repo_root / "install.sh", stage / "install.sh")
    shutil.copyfile(repo_root / "docs" / "runbook.md", stage / "docs" / "runbook.md")
    shutil.copyfile(app_dir / "LICENSES.txt", stage / "LICENSES.txt")
    shutil.copyfile(app_dir / "sky-source.zip", stage / "sky-source.zip")
    staged = sorted(p.name for p in stage.rglob("*") if p.is_file())
    banned = [n for n in staged if "prototype" in n.lower()]
    if banned:
        raise SystemExit(f"Прототипы в поставке запрещены: {banned}")
    return staged


def display_path(p):
    try:
        return p.relative_to(ROOT)
    except ValueError:
        return p


def make_zip(stage, zip_path):
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(stage.rglob("*")):
            if p.is_file():
                arc = "science-day/" + str(p.relative_to(stage))
                info = zipfile.ZipInfo(arc, date_time=ZIP_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                mode = 0o755 if p.name == "install.sh" else 0o644
                info.external_attr = (mode << 16) | 0o100000  # обычный файл
                info.create_system = 3  # unix
                z.writestr(info, p.read_bytes())
    log(f"  {display_path(zip_path)}: {zip_path.stat().st_size / (1024 * 1024):.1f} МиБ")


def bundle_phone(stage, dist, app_dir):
    """Автономный phone.html: инлайнит CSS/JS, подменяет real/<файл> на data URI.

    Исходные app/*.js не изменяются — подмена только в собранном файле.
    Порядок инлайна повторяет SCRIPT_ORDER: данные и модули обоих режимов
    встраиваются до их интерфейсов, иллюстрации NIGHTSHIFT_ART — как data URI.
    """
    html = (stage / "index.html").read_text(encoding="utf-8")
    for css in CSS_FILES:
        css_text = (stage / css).read_text(encoding="utf-8").replace("</style", "<\\/style")
        html = re.sub(
            rf'<link\s+rel="stylesheet"\s+href="{re.escape(css)}"\s*/?>',
            lambda _: f"<style>\n{css_text}\n</style>", html)
    for js in SCRIPT_ORDER:
        js_text = (stage / js).read_text(encoding="utf-8").replace("</script", "<\\/script")
        html, n = re.subn(
            rf'<script\s+src="{re.escape(js)}"\s*>\s*</script>',
            lambda _: f"<script>\n{js_text}\n</script>", html)
        if n != 1:
            raise SystemExit(f"phone.html: не найден (или найден многократно) тег "
                             f"<script src=\"{js}\"> в index.html — проверьте порядок скриптов")
    for jpg in sorted((stage / "real").glob("*.jpg")):
        uri = "data:image/jpeg;base64," + base64.b64encode(jpg.read_bytes()).decode("ascii")
        html = html.replace(f"real/{jpg.name}", uri)
    # Правовые ссылки: исходники атласа и полные тексты лицензий — встроенными dataURI
    # (атрибут download сохраняется, файлы получаются без сети).
    for fname, mime in (("sky-source.zip", "application/zip"),
                        ("LICENSES.txt", "text/plain;charset=utf-8")):
        uri = f"data:{mime};base64," + base64.b64encode((stage / fname).read_bytes()).decode("ascii")
        html, n = re.subn(rf'href="{re.escape(fname)}"', f'href="{uri}"', html)
        if n == 0:
            raise SystemExit(f"phone.html: в index.html нет ссылки href=\"{fname}\" "
                             f"(ожидался блок legal-details)")
    low = html.lower()
    problems = []
    if 'src="http' in low or 'href="http' in low or "url(http" in low:
        problems.append("внешние ссылки http(s)")
    if "fetch(" in low:
        problems.append("fetch(")
    if 'src="real/' in low or 'href="real/' in low:
        problems.append("несвёрнутые ссылки real/…")
    if '<script src="' in low:
        problems.append("не встроены скрипты (остался <script src=>)")
    if '<link rel="stylesheet"' in low:
        problems.append("не встроены стили (остался <link>)")
    if 'href="sky-source.zip"' in low or 'href="licenses.txt"' in low:
        problems.append("не встроены правовые файлы (остался href на файл)")
    for marker in ("window.GAME_DATA", "window.SKY_DATA", "window.DISCOVERY_DATA",
                   "NIGHTSHIFT_ART"):
        if marker not in html:
            problems.append(f"не встроены данные ({marker})")
    if problems:
        raise SystemExit(f"phone.html не автономен: {', '.join(problems)}")
    banner = ("<!-- Автосборка tools/build_release.py: автономная версия для телефона. "
              "Все стили, скрипты, снимки и данные встроены; интернет не нужен. -->\n")
    html = html.replace("<!doctype html>", "<!doctype html>\n" + banner, 1)
    out = dist / "phone.html"
    out.write_text(html, encoding="utf-8")
    log(f"  phone.html: {out.stat().st_size / (1024 * 1024):.1f} МиБ (полностью автономен)")


def main():
    ap = argparse.ArgumentParser(description="Сборка поставки «Архив неизвестного»")
    ap.add_argument("--data-only", action="store_true",
                    help="только app/data.js + app/real (без dist/)")
    ap.add_argument("--dist", default="dist", help="папка вывода (по умолчанию dist)")
    ap.add_argument("--app", default="app", help="папка приложения (по умолчанию app)")
    args = ap.parse_args()

    repo_root = ROOT
    app_dir = (repo_root / args.app).resolve()
    dist = (repo_root / args.dist).resolve()
    log("Генерация данных…")
    data, images = write_data_js(app_dir)
    sync_real(app_dir, repo_root)
    log("Лицензии и исходники атласа…")
    write_licenses_txt(repo_root, data)
    build_sky_source_zip(repo_root, app_dir)
    if args.data_only:
        log("Готово: --data-only (dist/ не собирался).")
        return

    log("Печатный комплект…")
    frame_pngs = {cid: [generate_data.png_bytes(e) for e in epochs]
                  for cid, epochs in images.items()}
    pdfs = print_kit.build_print_kit(dist / "print", data, frame_pngs)
    for p in pdfs:
        log(f"  {p.relative_to(dist.parent)}: {p.stat().st_size / 1024:.0f} КиБ")

    log("Сборка поставки…")
    stage = dist / ".stage" / "science-day"
    staged = stage_release(app_dir, repo_root, stage)
    log(f"  science-day/: {len(staged)} файлов (прототипы исключены)")
    dist.mkdir(parents=True, exist_ok=True)
    make_zip(stage, dist / "linux.zip")
    make_zip(stage, dist / "apple-silicon.zip")
    log("Автономный телефон…")
    bundle_phone(stage, dist, app_dir)
    shutil.rmtree(dist / ".stage")
    log(f"Готово. Содержимое dist/: linux.zip, apple-silicon.zip, phone.html, print/, "
        f"эталон stage — удалён; исходники поставки: app/ + install.sh + docs/runbook.md.")


if __name__ == "__main__":
    main()
