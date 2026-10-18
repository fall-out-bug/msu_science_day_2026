#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE = Path(__file__).with_name("build.py")
SPEC = importlib.util.spec_from_file_location("design_site_build", MODULE)
build = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(build)


class DesignSiteBuildTest(unittest.TestCase):
    revision = "a" * 40

    def make_source(self, root: Path) -> Path:
        source = root / "source"
        (source / "docs" / "evidence").mkdir(parents=True)
        (source / "docs" / "assets").mkdir()
        (source / "docs" / "guide").mkdir()
        (source / "docs" / "guide" / "next.md").write_text("# Следующий", encoding="utf-8")
        (source / "docs" / "first.md").write_text(
            "# Первый\n\n[Дальше](guide/next.md#часть)\n\n[Инструмент](../tools/run.py)\n\n```mermaid\ngraph TD\n A --> B\n```\n",
            encoding="utf-8",
        )
        (source / "docs" / "evidence" / "raw.md").write_text("# Evidence", encoding="utf-8")
        (source / "docs" / "assets" / "picture.png").write_bytes(b"png")
        (source / "docs" / "diagram.mmd").write_text("graph LR\n A-->B", encoding="utf-8")
        (source / "docs" / "legacy.html").write_text('<title>Legacy title</title><img src="assets/picture.png"><button data-screen-image="assets/picture.png">Экран</button><script src="assets/demo.js"></script>', encoding="utf-8")
        (source / "docs" / "assets" / "demo.js").write_text("window.demo = true;", encoding="utf-8")
        return source

    def test_builds_pages_sources_links_and_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            source = self.make_source(temporary_path)
            output = temporary_path / "output"
            manifest = build.build(source, output, self.revision)
            rendered = (output / "docs" / "first.html").read_text(encoding="utf-8")
            self.assertIn('href="guide/next.html#часть"', rendered)
            self.assertIn(f"https://github.com/fall-out-bug/msu_science_day_2026/blob/{self.revision}/tools/run.py", rendered)
            self.assertIn('class="mermaid"', rendered)
            self.assertTrue((output / "source" / "docs" / "first.md").is_file())
            self.assertTrue((output / "docs" / "assets" / "picture.png").is_file())
            self.assertFalse((output / "unrelated.txt").exists())
            self.assertTrue((output / "docs" / "diagram.mmd.html").is_file())
            self.assertNotIn("docs/evidence/raw.html", [page["path"] for page in manifest["pages"]])
            saved = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["revision"], self.revision)
            self.assertIn("docs/first.html", saved["files"])
            report = json.loads((output / "link-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report[0]["kind"], "github-source")

    def test_html_resources_collision_and_mermaid_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            source = self.make_source(temporary_path)
            (source / "docs" / "legacy.md").write_text("# Markdown legacy\n\n[Диаграмма](diagram.mmd)", encoding="utf-8")
            historical = source / "docs" / "design-2026-10-06" / "history" / "before-nika"
            historical.mkdir(parents=True)
            (historical / "screens.html").write_text("<h2>Экраны</h2>", encoding="utf-8")
            output = temporary_path / "output"
            build.build(source, output, self.revision)
            self.assertTrue((output / "docs" / "legacy.html").is_file())
            self.assertTrue((output / "docs" / "legacy.md.html").is_file())
            raw = (output / "docs" / "legacy.html").read_text(encoding="utf-8")
            self.assertIn('src="assets/picture.png"', raw)
            self.assertIn('data-screen-image="assets/picture.png"', raw)
            self.assertIn('src="assets/demo.js"', raw)
            self.assertIn("<!doctype html>", raw)
            self.assertNotIn("Фрагмент исторического документа", raw)
            old = (output / "docs/design-2026-10-06/history/before-nika/screens.html").read_text(encoding="utf-8")
            self.assertIn("Фрагмент исторического документа", old)
            self.assertIn("/docs/galaxy-game-design-before-nika.html", old)
            rendered = (output / "docs" / "legacy.md.html").read_text(encoding="utf-8")
            self.assertIn('href="diagram.mmd.html"', rendered)

    def test_refuses_ancestor_and_nonempty_output_without_touching_sentinel(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            source = self.make_source(temporary_path)
            sentinel = temporary_path / "sentinel.txt"
            sentinel.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ancestor"):
                build.build(source, temporary_path, self.revision)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            output = temporary_path / "occupied"
            output.mkdir()
            (output / "keep.txt").write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "absent or an empty"):
                build.build(source, output, self.revision)
            self.assertTrue((output / "keep.txt").is_file())

    def test_rejects_symlink_in_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            source = self.make_source(temporary_path)
            try:
                (source / "docs" / "escape.md").symlink_to("/etc/passwd")
            except OSError as error:
                self.skipTest(f"symlinks unavailable: {error}")
            with self.assertRaisesRegex(ValueError, "symlinks are not allowed"):
                build.build(source, temporary_path / "output", self.revision)

    def test_requires_full_revision(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            with self.assertRaisesRegex(ValueError, "full hexadecimal"):
                build.build(self.make_source(temporary_path), temporary_path / "output", "short")


if __name__ == "__main__":
    unittest.main()
