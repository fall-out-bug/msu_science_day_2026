#!/usr/bin/env python3
"""Build the static /design/ catalogue from a deliberately small git export.

The input is an export containing ``docs/`` and this tool, never a working
tree.  This keeps unpublished files and git metadata out of the release.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import posixpath
import re
import shutil
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import markdown


REPOSITORY = "https://github.com/fall-out-bug/msu_science_day_2026/blob"
EXCLUDED_CATALOG_PARTS = {"assets", "evidence"}
MERMAID_FENCE = re.compile(r"^```mermaid\s*\n(.*?)^```\s*$", re.MULTILINE | re.DOTALL)
MARKDOWN_LINK = re.compile(r"(!?)\[([^\]]+)\]\(([^\s)]+)(?:\s+['\"][^)]*['\"])?\)")
MARKDOWN_DESTINATION = re.compile(r"!?\[([^\]]*)\]\(([^\s)]+)(?:\s+['\"][^)]*['\"])?\)")
HTML_RESOURCE = re.compile(r"\b(?:href|src|data-screen-image)\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
GDD_ASSET_ALIASES = {
    "gdd-assets/concepts/": "assets/concepts/",
    "gdd-assets/navigation/": "assets/navigation/",
    "gdd-assets/navigation-nika/": "assets/navigation-nika/",
}
HISTORICAL_HOSTED = {
    "galaxy-game-design-before-nika.html": "/docs/galaxy-game-design-before-nika.html",
    "first-shift-scenario-before-nika.html": "/docs/first-shift-scenario-before-nika.html",
}
RESOURCE_SUFFIXES = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".pdf", ".mmd", ".mermaid"}


def die(message: str) -> None:
    raise ValueError(message)


def safe_relative(path: Path, root: Path) -> PurePosixPath:
    try:
        return PurePosixPath(path.relative_to(root).as_posix())
    except ValueError as error:
        raise ValueError(f"path escapes source: {path}") from error


def is_catalogue_page(relative: PurePosixPath) -> bool:
    return relative.suffix.lower() in {".md", ".html", ".mmd", ".mermaid"} and not (
        set(relative.parts) & EXCLUDED_CATALOG_PARTS
    )


def is_remote(value: str) -> bool:
    return bool(urlsplit(value).scheme) or value.startswith("//") or value.startswith("#")


def github_url(revision: str, repo_path: PurePosixPath, fragment: str = "") -> str:
    base = f"{REPOSITORY}/{revision}/{repo_path.as_posix()}"
    return f"{base}#{fragment}" if fragment else base


def page_path(relative: PurePosixPath, docs_root: Path) -> PurePosixPath:
    """Use .md.html when a raw HTML document has the same source stem."""
    if relative.suffix.lower() == ".md" and (docs_root / relative.with_suffix(".html")).is_file():
        return PurePosixPath(str(relative) + ".html")
    if relative.suffix.lower() in {".mmd", ".mermaid"}:
        return PurePosixPath(str(relative) + ".html")
    return relative.with_suffix(".html")


def relative_url(origin: PurePosixPath, target: PurePosixPath) -> str:
    return posixpath.relpath(target.as_posix(), start=origin.parent.as_posix())


def resolve_local(value: str, source_file: PurePosixPath, docs_root: Path) -> tuple[PurePosixPath | None, PurePosixPath | None]:
    """Return docs-relative target, or repository-relative target outside docs."""
    path = value
    if source_file.parts[:3] == ("design-2026-10-06", "history", "before-nika"):
        # These files were moved below history/ after their review links were
        # written.  Their old layout is documented by the canonical copies.
        if path.startswith("assets/"):
            return PurePosixPath("design-2026-10-06/assets") / path[len("assets/"):], None
        if path.startswith("../redesign-2026-10-05/"):
            return PurePosixPath("redesign-2026-10-05") / path[len("../redesign-2026-10-05/"):], None
        if path.startswith("../../"):
            return None, PurePosixPath(path[len("../../"):])
    for old, new in GDD_ASSET_ALIASES.items():
        if path.startswith(old):
            return PurePosixPath("design-2026-10-06") / (new + path[len(old):]), None
    candidate = (docs_root / source_file.parent / path).resolve()
    try:
        return safe_relative(candidate, docs_root.resolve()), None
    except ValueError:
        repo_path = PurePosixPath(posixpath.normpath((PurePosixPath("docs") / source_file.parent / path).as_posix()))
        return None, repo_path


def published_target(relative: PurePosixPath, docs_root: Path) -> PurePosixPath:
    return PurePosixPath("docs") / page_path(relative, docs_root) if relative.suffix.lower() in {".md", ".mmd", ".mermaid"} else PurePosixPath("docs") / relative


def rewrite_markdown_links(text: str, source_file: PurePosixPath, docs_root: Path, revision: str) -> str:
    """Turn local Markdown references into rendered-page references.

    A target outside the exported docs tree is intentionally a pinned GitHub
    link.  Do not guess or copy it: the caller may have exported only docs.
    """
    def replace(match: re.Match[str]) -> str:
        image, label, target = match.groups()
        if is_remote(target):
            return match.group(0)
        parts = urlsplit(target)
        if not parts.path:
            return match.group(0)
        if parts.path in HISTORICAL_HOSTED:
            replacement = HISTORICAL_HOSTED[parts.path] + (f"#{parts.fragment}" if parts.fragment else "")
            return f"{image}[{label}]({replacement})"
        relative, repo_target = resolve_local(parts.path, source_file, docs_root)
        if repo_target is not None:
            return f"{image}[{label}]({github_url(revision, repo_target, parts.fragment)})"
        assert relative is not None
        candidate = docs_root / relative
        if candidate.is_dir():
            repo_target = PurePosixPath("docs") / relative
            return f"{image}[{label}]({github_url(revision, repo_target, parts.fragment)})"
        if candidate.is_file():
            rendered = relative_url(published_target(source_file, docs_root), published_target(relative, docs_root))
            if parts.fragment:
                rendered += f"#{parts.fragment}"
            return f"{image}[{label}]({rendered})"
        return match.group(0)

    return MARKDOWN_LINK.sub(replace, text)


def rewrite_html_resources(text: str, source_file: PurePosixPath, docs_root: Path, revision: str) -> str:
    def replace(match: re.Match[str]) -> str:
        value = match.group(1)
        if is_remote(value):
            return match.group(0)
        parts = urlsplit(value)
        if not parts.path:
            return match.group(0)
        relative, repo_target = resolve_local(parts.path, source_file, docs_root)
        if repo_target is not None:
            replacement = github_url(revision, repo_target, parts.fragment)
        else:
            assert relative is not None
            candidate = docs_root / relative
            if not candidate.is_file():
                return match.group(0)
            replacement = relative_url(PurePosixPath("docs") / source_file, published_target(relative, docs_root))
            if parts.fragment:
                replacement += f"#{parts.fragment}"
        return match.group(0).replace(value, replacement)
    return HTML_RESOURCE.sub(replace, text)


def title_for(item: Path, raw: str) -> str:
    if item.suffix.lower() == ".md":
        match = re.search(r"^#\s+(.+?)\s*$", raw, re.MULTILINE)
    else:
        match = re.search(r"<title[^>]*>\s*(.*?)\s*</title>|<h1[^>]*>\s*(.*?)\s*</h1>", raw, re.IGNORECASE | re.DOTALL)
    if match:
        return re.sub(r"<[^>]+>", "", next(part for part in match.groups() if part is not None)).strip()
    return item.stem


def ignored(relative: PurePosixPath) -> bool:
    return any(part.startswith(".") or part == "__pycache__" for part in relative.parts) or relative.suffix.lower() == ".pyc"


def render_markdown(raw: str, relative: PurePosixPath, docs_root: Path, revision: str) -> str:
    source = rewrite_markdown_links(raw, relative, docs_root, revision)
    source = MERMAID_FENCE.sub(
        lambda match: '<pre class="mermaid">' + html.escape(match.group(1).strip()) + "</pre>", source
    )
    return markdown.markdown(
        source,
        extensions=["extra", "sane_lists", "toc", "nl2br"],
        output_format="html5",
    )


def shell(title: str, body: str, source_url: str, include_mermaid: bool) -> str:
    script = '<script src="/design/vendor/mermaid/mermaid.min.js"></script><script src="/design/site.js"></script>' if include_mermaid else '<script src="/design/site.js"></script>'
    source = f'<a class="source" href="{html.escape(source_url)}" download>Скачать исходник</a>' if source_url else ""
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} — Science Day</title><link rel="stylesheet" href="/design/site.css"></head>
<body><header><a href="/design/">Science Day · дизайн</a>{source}</header>
<main><article>{body}</article></main>{script}</body></html>"""


def is_full_html(text: str) -> bool:
    return bool(re.search(r"<!doctype\b|<html\b", text, re.IGNORECASE))


def historical_document_url(relative: PurePosixPath) -> str:
    if relative.parts[:3] == ("design-2026-10-06", "history", "before-nika"):
        return "/docs/galaxy-game-design-before-nika.html"
    return "/docs/galaxy-game-design.html"


def historical_fragment(title: str, body: str, relative: PurePosixPath) -> str:
    if relative.parts[0] != "design-2026-10-06":
        return shell(title, body, "", False)
    note = (
        '<p class="fragment-note">Фрагмент исторического документа. '
        f'<a href="{historical_document_url(relative)}">Открыть полную старую редакцию</a>.</p>'
    )
    return shell(title, note + body, "", False)


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def link_report(docs: Path, revision: str) -> list[dict[str, str]]:
    """Describe unresolved references without silently replacing them."""
    report: list[dict[str, str]] = []
    docs_root = docs.resolve()
    for item in sorted(docs.rglob("*")):
        if not item.is_file() or item.suffix.lower() not in {".md", ".html"}:
            continue
        relative = safe_relative(item, docs)
        if ignored(relative):
            continue
        text = item.read_text(encoding="utf-8")
        targets = (match.group(2) for match in MARKDOWN_DESTINATION.finditer(text)) if item.suffix.lower() == ".md" else (match.group(1) for match in HTML_RESOURCE.finditer(text))
        for value in targets:
            if is_remote(value):
                continue
            parsed = urlsplit(value)
            if not parsed.path:
                continue
            if parsed.path in HISTORICAL_HOSTED:
                continue
            target_relative, repo_path = resolve_local(parsed.path, relative, docs_root)
            if repo_path is not None:
                report.append({"kind": "github-source", "source": f"docs/{relative}", "target": repo_path.as_posix(), "url": github_url(revision, repo_path, parsed.fragment)})
                continue
            assert target_relative is not None
            candidate = docs_root / target_relative
            if candidate.is_dir():
                repo_path = PurePosixPath("docs") / target_relative
                report.append({"kind": "github-source", "source": f"docs/{relative}", "target": repo_path.as_posix(), "url": github_url(revision, repo_path, parsed.fragment)})
                continue
            if not candidate.is_file():
                report.append({"kind": "missing-local-resource", "source": f"docs/{relative}", "target": f"docs/{target_relative}"})
    return report


def build(source: Path, output: Path, revision: str) -> dict[str, object]:
    source, output = source.resolve(), output.resolve()
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", revision):
        die("--revision must be a full hexadecimal commit SHA")
    docs = source / "docs"
    if not docs.is_dir():
        die(f"missing docs directory: {docs}")
    if output == source or output in source.parents or output == docs or docs in output.parents:
        die("output must not be source, an ancestor of source, or overlap docs")
    # Only docs is publication input.  An export may share its parent directory
    # with a virtualenv or other build tooling, none of which belongs here.
    for path in docs.rglob("*"):
        if path.is_symlink():
            die(f"symlinks are not allowed in a publication export: {path}")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        die("output must be absent or an empty directory")
    output.mkdir(parents=True, exist_ok=True)

    pages: list[dict[str, str]] = []
    resources: list[str] = []
    for item in sorted(docs.rglob("*")):
        if item.is_dir():
            continue
        relative = safe_relative(item, docs)
        if ignored(relative):
            continue
        output_relative = PurePosixPath("docs") / relative
        if item.suffix.lower() == ".md":
            raw = item.read_text(encoding="utf-8")
            body = render_markdown(raw, relative, docs, revision)
            rendered_relative = PurePosixPath("docs") / page_path(relative, docs)
            target = output / rendered_relative
            source_target = output / "source" / output_relative
            copy_file(item, source_target)
            source_url = relative_url(rendered_relative, PurePosixPath("source") / output_relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(shell(title_for(item, raw), body, source_url, "mermaid" in body), encoding="utf-8")
            if is_catalogue_page(relative):
                pages.append({"title": title_for(item, raw), "path": rendered_relative.as_posix(), "group": relative.parts[0] if len(relative.parts) > 1 else "Общее"})
        elif item.suffix.lower() in {".mmd", ".mermaid"}:
            raw = item.read_text(encoding="utf-8")
            rendered_relative = PurePosixPath("docs") / page_path(relative, docs)
            target = output / rendered_relative
            source_target = output / "source" / output_relative
            copy_file(item, source_target)
            source_url = relative_url(rendered_relative, PurePosixPath("source") / output_relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(shell(item.stem, '<pre class="mermaid">' + html.escape(raw) + "</pre>", source_url, True), encoding="utf-8")
            if is_catalogue_page(relative):
                pages.append({"title": item.stem, "path": rendered_relative.as_posix(), "group": relative.parts[0] if len(relative.parts) > 1 else "Общее"})
        else:
            raw = item.read_text(encoding="utf-8") if item.suffix.lower() == ".html" else ""
            if item.suffix.lower() == ".html":
                target = output / output_relative
                target.parent.mkdir(parents=True, exist_ok=True)
                rewritten = rewrite_html_resources(raw, relative, docs, revision)
                rendered = rewritten if is_full_html(rewritten) else historical_fragment(title_for(item, raw), rewritten, relative)
                target.write_text(rendered, encoding="utf-8")
            else:
                copy_file(item, output / output_relative)
            if item.suffix.lower() == ".html" and is_catalogue_page(relative):
                pages.append({"title": title_for(item, raw), "path": output_relative.as_posix(), "group": relative.parts[0] if len(relative.parts) > 1 else "Общее"})
            if item.suffix.lower() in RESOURCE_SUFFIXES:
                resources.append(output_relative.as_posix())

    def catalogue_order(page):
        date = re.search(r"\d{4}-\d{2}-\d{2}", page["group"])
        return (date.group(0) if date else "", page["group"], page["path"])

    pages.sort(key=catalogue_order, reverse=True)
    groups: dict[str, list[dict[str, str]]] = {}
    for page in pages:
        groups.setdefault(page["group"], []).append(page)
    links = "".join(f"<section><h2>{html.escape(group)}</h2><ul class=pages>" + "\n".join(f'<li><a href="{html.escape(page["path"])}">{html.escape(page["title"])}</a><small>{html.escape(page["path"])}</small></li>' for page in group_pages) + "</ul></section>" for group, group_pages in groups.items())
    resource_links = "\n".join(f'<li><a href="{html.escape(path)}">{html.escape(path)}</a></li>' for path in sorted(resources))
    (output / "index.html").write_text(
        shell("Каталог дизайн-документов", f"<h1>Каталог дизайн-документов</h1><p>Редакция исходников: <code>{revision}</code></p>{links}<details><summary>Схемы, изображения и PDF ({len(resources)})</summary><ul class=pages>{resource_links}</ul></details>", "", False),
        encoding="utf-8",
    )
    tool_dir = Path(__file__).resolve().parent
    copy_file(tool_dir / "site.css", output / "site.css")
    copy_file(tool_dir / "site.js", output / "site.js")
    vendor = tool_dir / "vendor" / "mermaid"
    if vendor.is_dir():
        shutil.copytree(vendor, output / "vendor" / "mermaid")

    report = link_report(docs, revision)
    (output / "link-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    files = {
        path.relative_to(output).as_posix(): sha256(path)
        for path in sorted(output.rglob("*")) if path.is_file() and path.name != "manifest.json"
    }
    manifest = {"revision": revision.lower(), "pages": pages, "files": files}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    try:
        manifest = build(args.source, args.output, args.revision)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"design-site: {error}", file=sys.stderr)
        return 2
    print(f"built {len(manifest['pages'])} catalogue pages in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
