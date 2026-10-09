#!/usr/bin/env python
"""Publish the current design and its historical foundations without touching comments."""
import argparse
import hashlib
import html
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import markdown
from markdown.extensions.toc import slugify_unicode


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs" / "design-2026-10-08"
PUBLIC = ROOT / "designlab" / "comparison" / "docs"
PAGES = {
    "night-of-discoveries": ("galaxy-game-design", "Дизайн: Ночь открытий"),
    "night-release": ("release", "Проверки и поставка"),
    "night-goal": ("goal", "Текущая цель"),
    "programme": ("programme", "Описание для программы"),
    "learning-review": ("learning-review", "Вычитка учебного маршрута"),
    "game-design": ("game-design-foundation", "Исходный дизайн 8 октября"),
    "technical-plan": ("technical-plan", "Технический план"),
    "acceptance": ("acceptance", "Исходная матрица A/V"),
    "goal": ("goal-20261008", "Цель предыдущего выпуска"),
    "baseline": ("baseline", "Исходное состояние"),
    "text-review": ("text-review", "Вычитка 8 октября"),
    "release": ("release-20261008", "Проверки предыдущего выпуска"),
}
HISTORICAL_HTML = "galaxy-game-design-20261006.html"
HISTORICAL_MD = "galaxy-game-design-20261006.md"
ZIP_SUPPORT_FILES = (
    "galaxy-design-demo.js",
    "galaxy-design-nika.js",
    "scenario-comments.css",
    "scenario-comments.js",
    "first-shift-scenario.html",
    "first-shift-scenario.md",
    "first-shift-scenario-before-nika.html",
    "first-shift-scenario-before-nika.md",
    "first-shift-changes.html",
    "first-shift-classification.diff",
    "galaxy-game-design-before-nika.html",
    "galaxy-game-design-before-nika.md",
)


def source_path(name: str) -> Path:
    folder = ROOT / "docs" / "design-2026-10-09" if name in {"night-of-discoveries", "night-release", "night-goal", "programme", "learning-review"} else SOURCE
    return folder / f"{name}.md"


def page_links(current: str) -> str:
    links = []
    for source_name, (published_name, title) in PAGES.items():
        if published_name != current:
            links.append(f'<a href="{published_name}.html">{html.escape(title)}</a>')
    return "".join(links)


def rewrite_html_links(text: str) -> str:
    """Keep the published document set closed under its useful links."""
    text = text.replace("../design-2026-10-08/", "").replace("../design-2026-10-09/", "")
    for source_name, (published_name, _) in PAGES.items():
        text = re.sub(
            rf'(\]\(){re.escape(source_name)}\.md(?=#[^)]+\)|\))',
            rf'\1{published_name}.html',
            text,
        )
    text = re.sub(
        r'(\]\()\.\./design-2026-10-06/game-design\.md(?:#[^)]+)?(?=\))',
        rf'\1{HISTORICAL_HTML}',
        text,
    )
    # The repository READMEs are source references, not a part of this small
    # offline publication.  Point readers at the local explanation instead.
    text = re.sub(
        r'(\]\()\.\./\.\./(?:designlab/galaxy-shift(?:/experiments)?/README|tools/galaxy-release/RELEASE)\.md(?=\))',
        r'\1README.md#исходные-материалы',
        text,
    )
    return text


def render(source_name: str, published_name: str, title: str, raw: str) -> str:
    rendered = markdown.Markdown(extensions=["tables", "fenced_code", "toc"], extension_configs={"toc":{"slugify":slugify_unicode}})
    if source_name in {"night-of-discoveries", "night-release", "night-goal", "programme", "learning-review"}:
        raw = raw.replace("](evidence/", "](night-evidence/")
    body = rendered.convert(rewrite_html_links(raw))
    return f"""<!doctype html>
<html lang=\"ru\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
  <title>{html.escape(title)} · Science Day</title>
  <link rel=\"stylesheet\" href=\"galaxy-design.css\">
</head>
<body>
  <main>
    <header>
      <p class=\"eyebrow\">Science Day · 9 октября 2026 · Ночь открытий</p>
      <div class=\"asset-links\">{page_links(published_name)}<a href=\"{HISTORICAL_HTML}\">Историческая редакция с комментариями</a><a href=\"galaxy-design-offline.zip\">Офлайн-документы</a></div>
      <p class=\"build-note\">Дизайн и матрица задают требования. Фактические проверки и состояние публикации записаны в <a href=\"release.html\">отчёте о поставке</a>.</p>
    </header>
    <nav aria-label=\"Оглавление\">{rendered.toc}</nav>
    {body}
  </main>
</body>
</html>
"""


def readme() -> str:
    return """# Документы «Ночи открытий» · 9 октября 2026

Стартовая страница: `galaxy-game-design.html`. Рядом лежат технический план,
матрица приёмки, формулировка цели, исходное состояние, вычитка и отчёт о
поставке. Текущие решения и отчёт собраны из `docs/design-2026-10-09/`;
научный и технический контракт сохранён из `docs/design-2026-10-08/`.
При противоречии в маршруте и интерфейсе действует редакция 9 октября.

`galaxy-game-design-20261006.html` и `.md` — точная сохранённая публикация
6 октября. В HTML остаются исходные `data-review-id`, подключение комментариев
и локальные ресурсы, поэтому прежние обсуждения не теряют привязку. Новые
страницы не используют сервер комментариев и не получают его идентификаторы.

## Сборка

Из корня репозитория, в Python с установленным пакетом `markdown`:

```bash
python tools/scenario-review/build-current-design.py
```

Команда создаёт страницы, Markdown-копии и `galaxy-design-offline.zip`. Архив
содержит все связанные страницы, CSS и историческую редакцию; его можно открыть
без сети. Сборка не запускает браузер, не меняет реестры привязок и не
перезапускает сервис комментариев.

## Исходные материалы

Ссылки на README игры, протокол опытов и порядок выпуска в опубликованных
страницах ведут сюда, потому что сами репозиторные README не входят в компактный
архив документов. Их актуальные исходники остаются соответственно в
`designlab/galaxy-shift/README.md`, `designlab/galaxy-shift/experiments/README.md`
и `tools/galaxy-release/RELEASE.md`.
"""


def check_historical(path: Path) -> None:
    content = path.read_text()
    required = ("data-review-document=\"galaxy-gdd-v1\"", "data-review-id=\"n4d", "scenario-comments.js")
    if not all(token in content for token in required):
        raise RuntimeError(f"{path} is not the archived 6 October commented GDD")


def write_zip_file(archive: zipfile.ZipFile, path: Path, name: str) -> None:
    entry = zipfile.ZipInfo(name, date_time=(2026, 10, 8, 0, 0, 0))
    entry.compress_type = zipfile.ZIP_DEFLATED
    entry.external_attr = 0o100644 << 16
    content = path.read_bytes()
    if name in {f"{published}.html" for published, _ in PAGES.values()}:
        content = content.replace(
            b'<a href="galaxy-design-offline.zip">' + 'Офлайн-документы'.encode() + b'</a>',
            '<span>Автономная копия документов</span>'.encode(),
        )
    archive.writestr(entry, content)


def build() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    missing = [name for name in PAGES if not source_path(name).is_file()]
    if missing:
        raise FileNotFoundError(f"missing design sources: {', '.join(missing)}")

    old_html = PUBLIC / "galaxy-game-design.html"
    old_md = PUBLIC / "galaxy-game-design.md"
    historical_html = PUBLIC / HISTORICAL_HTML
    historical_md = PUBLIC / HISTORICAL_MD
    if not historical_html.exists():
        check_historical(old_html)
    if not historical_md.exists() and not old_md.exists():
        raise FileNotFoundError("cannot archive the 6 October Markdown source")

    with tempfile.TemporaryDirectory(prefix="science-day-current-design-") as temp_dir:
        staging = Path(temp_dir)
        raw_sources = {name: source_path(name).read_text() for name in PAGES}
        for source_name, (published_name, title) in PAGES.items():
            (staging / f"{published_name}.md").write_text(raw_sources[source_name])
            (staging / f"{published_name}.html").write_text(
                render(source_name, published_name, title, raw_sources[source_name])
            )
        (staging / "README.md").write_text(readme())
        evidence = SOURCE / "evidence"
        if evidence.is_dir():
            shutil.copytree(evidence, staging / "evidence")
        night_evidence = ROOT / "docs/design-2026-10-09/evidence"
        if night_evidence.is_dir():
            shutil.copytree(night_evidence, staging / "night-evidence")

        shutil.copy2(
            historical_html if historical_html.exists() else old_html,
            staging / HISTORICAL_HTML,
        )
        shutil.copy2(
            historical_md if historical_md.exists() else old_md,
            staging / HISTORICAL_MD,
        )

        css = PUBLIC / "galaxy-design.css"
        if not css.exists():
            raise FileNotFoundError(css)
        shutil.copy2(css, staging / css.name)
        support_paths = [PUBLIC / name for name in ZIP_SUPPORT_FILES]
        support_paths.extend((PUBLIC / "gdd-assets").rglob("*") )
        missing_support = [path for path in support_paths if not path.exists()]
        if missing_support:
            raise FileNotFoundError(", ".join(str(path) for path in missing_support))
        with zipfile.ZipFile(staging / "galaxy-design-offline.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(staging.iterdir()):
                if path.is_file() and path.name != "galaxy-design-offline.zip":
                    write_zip_file(archive, path, path.name)
                elif path.is_dir():
                    for child in sorted(path.rglob("*")):
                        if child.is_file():
                            write_zip_file(archive, child, child.relative_to(staging).as_posix())
            for path in support_paths:
                if path.is_file():
                    write_zip_file(archive, path, path.relative_to(PUBLIC).as_posix())

        if not historical_html.exists():
            shutil.copy2(staging / HISTORICAL_HTML, historical_html)
        if not historical_md.exists():
            shutil.copy2(staging / HISTORICAL_MD, historical_md)
        for path in staging.iterdir():
            if path.is_file() and path.name not in {HISTORICAL_HTML, HISTORICAL_MD, "galaxy-design.css"}:
                shutil.copy2(path, PUBLIC / path.name)
            elif path.is_dir():
                shutil.copytree(path, PUBLIC / path.name, dirs_exist_ok=True)

    check_historical(historical_html)
    current = (PUBLIC / "galaxy-game-design.html").read_text()
    if "data-review-id=" in current or "scenario-comments.js" in current:
        raise RuntimeError("current GDD unexpectedly retained comment bindings")
    print(
        "built current design documents",
        f"sources={len(PAGES)}",
        f"historical_sha256={hashlib.sha256(historical_html.read_bytes()).hexdigest()}",
    )


if __name__ == "__main__":
    build()
