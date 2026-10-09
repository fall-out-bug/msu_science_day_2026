#!/usr/bin/env python3
"""Regression checks for the archive restore CLI.

Run with ``python3 tools/archive/test_restore.py`` from the repository root.
The fixture exercises each storage kind, an internal npm-style symlink, and
refusal of corrupt payloads, traversal paths, and existing output directories.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
RESTORE = REPO / "tools/archive/restore.py"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class RestoreCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="archive-restore-test-")
        self.root = Path(self.temporary.name)
        self.manifest = self.root / "manifest.json"
        (self.root / "source").mkdir()
        self.source = b"readable source\n"
        (self.root / "source/note.txt").write_bytes(self.source)
        self.head = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()
        self.blob = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD:README.md"], text=True).strip()
        self.readme = subprocess.check_output(["git", "-C", str(REPO), "cat-file", "blob", self.blob])
        self.payload = b"payload object\n"
        self.link = b"../plain.txt"
        self.write_manifest()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_manifest(self) -> None:
        members = [self.payload, self.link]
        part = self.root / "payload.tar.xz"
        with tarfile.open(part, "w:xz") as archive:
            for content in members:
                info = tarfile.TarInfo(sha256(content))
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        part_data = part.read_bytes()
        document = {
            "schemaVersion": 1,
            "historyCommit": self.head,
            "payloadParts": [{"path": "payload.tar.xz", "size": len(part_data), "sha256": sha256(part_data)}],
            "files": [
                {"path": "plain.txt", "type": "file", "size": len(self.payload), "mode": 0o640,
                 "sha256": sha256(self.payload), "storage": {"kind": "payload", "member": sha256(self.payload)}},
                {"path": "links/plain", "type": "symlink", "size": len(self.link), "mode": 0o777,
                 "sha256": sha256(self.link), "storage": {"kind": "payload", "member": sha256(self.link)}},
                {"path": "note.txt", "type": "file", "size": len(self.source), "mode": 0o600,
                 "sha256": sha256(self.source), "storage": {"kind": "file", "path": "source/note.txt"}},
                {"path": "history.md", "type": "file", "size": len(self.readme), "mode": 0o644,
                 "sha256": sha256(self.readme), "storage": {"kind": "git", "blob": self.blob}},
            ],
        }
        self.manifest.write_text(json.dumps(document), encoding="utf-8")

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(RESTORE), *arguments], text=True, capture_output=True)

    def test_verify_and_restore_all_storage_kinds(self) -> None:
        verified = self.run_cli("--verify", "--manifest", str(self.manifest))
        self.assertEqual(verified.returncode, 0, verified.stderr)
        restored = self.root / "restored"
        result = self.run_cli("--output", str(restored), "--manifest", str(self.manifest))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((restored / "plain.txt").read_bytes(), self.payload)
        self.assertEqual((restored / "note.txt").read_bytes(), self.source)
        self.assertEqual((restored / "history.md").read_bytes(), self.readme)
        self.assertTrue((restored / "links/plain").is_symlink())
        self.assertEqual((restored / "links/plain").readlink().as_posix(), "../plain.txt")
        self.assertEqual((restored / "plain.txt").stat().st_mode & 0o7777, 0o640)

    def test_rejects_corruption_and_unsafe_paths(self) -> None:
        with (self.root / "payload.tar.xz").open("ab") as handle:
            handle.write(b"corruption")
        corrupted = self.run_cli("--verify", "--manifest", str(self.manifest))
        self.assertNotEqual(corrupted.returncode, 0)
        self.write_manifest()
        document = json.loads(self.manifest.read_text(encoding="utf-8"))
        document["files"][0]["path"] = "../escape"
        self.manifest.write_text(json.dumps(document), encoding="utf-8")
        traversal = self.run_cli("--verify", "--manifest", str(self.manifest))
        self.assertNotEqual(traversal.returncode, 0)

    def test_refuses_existing_output(self) -> None:
        existing = self.root / "existing"
        existing.mkdir()
        sentinel = existing / "keep.txt"
        sentinel.write_text("existing work")
        result = self.run_cli("--output", str(existing), "--manifest", str(self.manifest))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_text(), "existing work")

    def test_rejects_relative_output_and_mismatched_payload_metadata(self) -> None:
        result = self.run_cli("--output", "relative-output", "--manifest", str(self.manifest))
        self.assertNotEqual(result.returncode, 0)
        for field, value in (("size", len(self.payload) + 1), ("sha256", "0" * 64)):
            with self.subTest(field=field):
                self.write_manifest()
                document = json.loads(self.manifest.read_text())
                document["files"][0][field] = value
                self.manifest.write_text(json.dumps(document))
                result = self.run_cli("--verify", "--manifest", str(self.manifest))
                self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
