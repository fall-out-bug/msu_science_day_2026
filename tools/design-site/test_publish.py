import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from io import BytesIO

spec = importlib.util.spec_from_file_location("publisher", Path(__file__).with_name("publish.py"))
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def release(self, name, content="catalogue"):
        site = self.root / "releases" / name
        site.mkdir(parents=True)
        (site / "index.html").write_text(content)
        (site / "manifest.json").write_text(json.dumps({"revision": name, "files": {
            "index.html": hashlib.sha256(content.encode()).hexdigest()}}))
        return site

    def test_corrupted_artifact_cannot_pass_verification(self):
        site = self.release("one")
        (site / "index.html").write_text("damaged")
        with self.assertRaisesRegex(ValueError, "checksum"):
            publisher.verify_files(site, "one")

    def test_manifest_cannot_point_outside_release(self):
        site = self.release("one")
        data = json.loads((site / "manifest.json").read_text())
        data["files"]["../../../private"] = "unused"
        (site / "manifest.json").write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "escapes"):
            publisher.verify_files(site, "one")

    def test_failed_served_check_restores_previous_publication(self):
        self.release("one")
        self.release("two")
        publisher.activate(self.root, "releases/one")
        with patch.object(publisher, "verify_served", side_effect=RuntimeError("unavailable")):
            with self.assertRaises(RuntimeError):
                publisher.activate(self.root, "releases/two", "http://example.test")
        self.assertEqual((self.root / "current").readlink(), Path("releases/one"))
        self.assertFalse((self.root / "previous").exists())

    def test_successful_publication_retains_rollback_target(self):
        self.release("one")
        self.release("two")
        publisher.activate(self.root, "releases/one")
        publisher.activate(self.root, "releases/two")
        self.assertEqual((self.root / "current").readlink(), Path("releases/two"))
        self.assertEqual((self.root / "previous").readlink(), Path("releases/one"))

    def test_ci_must_match_the_exact_main_commit_and_latest_attempt(self):
        run = {"id": 1, "head_sha": "a" * 40, "head_branch": "main",
               "path": ".github/workflows/design-docs.yml@main", "status": "completed", "conclusion": "success"}
        newer_failed = {**run, "id": 2, "conclusion": "failure"}
        for runs in [[{**run, "head_sha": "b" * 40}], [run, newer_failed]]:
            with patch.object(publisher.urllib.request, "urlopen", return_value=BytesIO(json.dumps({"workflow_runs": runs}).encode())):
                with self.assertRaisesRegex(RuntimeError, "Waiting"):
                    publisher.verify_ci("a" * 40)
        with patch.object(publisher.urllib.request, "urlopen", return_value=BytesIO(json.dumps({"workflow_runs": [run]}).encode())):
            publisher.verify_ci("a" * 40)
        run["path"] = ".github/workflows/design-docs.yml"
        with patch.object(publisher.urllib.request, "urlopen", return_value=BytesIO(json.dumps({"workflow_runs": [run]}).encode())):
            publisher.verify_ci("a" * 40)


if __name__ == "__main__":
    unittest.main()
