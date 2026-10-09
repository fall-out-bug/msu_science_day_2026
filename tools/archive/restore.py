#!/usr/bin/env python3
"""Verify or restore a repository-backed Science Day worktree snapshot.

The manifest deliberately describes files rather than an executable archive:
content is either a Git blob, a readable file next to the manifest, or a
deduplicated object in a split ``tar.xz`` payload.  This program never runs
anything from the snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import posixpath
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from typing import Any, Iterable


CHUNK = 1024 * 1024
SHA256_LEN = 64
SHA1_LEN = 40
DEFAULT_MANIFEST = Path("archive/2026-10-09-worktree/manifest.json")


class ArchiveError(Exception):
    """An invalid or incomplete archive."""


@dataclass(frozen=True)
class Entry:
    path: str
    kind: str
    size: int
    mode: int
    sha256: str
    storage_kind: str
    storage_value: str


@dataclass(frozen=True)
class Part:
    path: Path
    size: int
    sha256: str


def fail(message: str) -> None:
    raise ArchiveError(message)


def is_hex(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(c in "0123456789abcdef" for c in value)


def safe_relative(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        fail(f"{label} must be a non-empty relative path")
    posix = PurePosixPath(value)
    if posix.is_absolute() or not posix.parts or value != posix.as_posix() or ".." in posix.parts:
        fail(f"{label} is not a safe relative path: {value!r}")
    # A manifest is portable only when paths have one separator convention.
    if "\\" in value:
        fail(f"{label} must use POSIX separators: {value!r}")
    return Path(*posix.parts)


def hash_stream(stream: Any) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    while True:
        block = stream.read(CHUNK)
        if not block:
            break
        digest.update(block)
        total += len(block)
    return total, digest.hexdigest()


def hash_path(path: Path, label: str) -> tuple[int, str]:
    try:
        info = path.lstat()
    except FileNotFoundError:
        fail(f"missing {label}: {path}")
    if not stat.S_ISREG(info.st_mode):
        fail(f"{label} is not a regular file: {path}")
    with path.open("rb") as handle:
        return hash_stream(handle)


def require_digest(size: int, digest: str, expected_size: int, expected_digest: str, label: str) -> None:
    if size != expected_size:
        fail(f"{label} has size {size}, expected {expected_size}")
    if digest != expected_digest:
        fail(f"{label} has SHA-256 {digest}, expected {expected_digest}")


def load_manifest(path: Path) -> tuple[dict[str, Any], list[Entry], list[Part]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"manifest does not exist: {path}")
    except json.JSONDecodeError as exc:
        fail(f"manifest is not JSON: {exc}")
    if not isinstance(raw, dict) or raw.get("schemaVersion") != 1:
        fail("manifest schemaVersion must be 1")
    if not is_hex(raw.get("historyCommit"), SHA1_LEN):
        fail("manifest historyCommit must be a lowercase 40-character Git commit")
    records = raw.get("files")
    if not isinstance(records, list):
        fail("manifest files must be a list")

    entries: list[Entry] = []
    paths: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            fail(f"files[{index}] must be an object")
        file_path = record.get("path")
        safe_relative(file_path, f"files[{index}].path")
        if file_path in paths:
            fail(f"duplicate file path: {file_path}")
        paths.add(file_path)
        file_kind = record.get("type")
        if file_kind not in ("file", "symlink"):
            fail(f"files[{index}].type must be file or symlink")
        size, mode, digest = record.get("size"), record.get("mode"), record.get("sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            fail(f"files[{index}].size must be a non-negative integer")
        if not isinstance(mode, int) or isinstance(mode, bool) or not 0 <= mode <= 0o7777:
            fail(f"files[{index}].mode must be a POSIX permission integer")
        if file_kind == "symlink" and mode != 0o777:
            fail(f"files[{index}] symlink mode must be 0o777")
        if not is_hex(digest, SHA256_LEN):
            fail(f"files[{index}].sha256 must be lowercase SHA-256")
        storage = record.get("storage")
        if not isinstance(storage, dict):
            fail(f"files[{index}].storage must be an object")
        storage_kind = storage.get("kind")
        if storage_kind == "git":
            storage_value = storage.get("blob")
            if not is_hex(storage_value, SHA1_LEN):
                fail(f"files[{index}].storage.blob must be lowercase Git SHA-1")
        elif storage_kind == "file":
            storage_value = storage.get("path")
            safe_relative(storage_value, f"files[{index}].storage.path")
        elif storage_kind == "payload":
            storage_value = storage.get("member")
            if not is_hex(storage_value, SHA256_LEN):
                fail(f"files[{index}].storage.member must be lowercase SHA-256")
            if storage_value != digest:
                fail(f"files[{index}] payload member must equal file SHA-256")
        else:
            fail(f"files[{index}].storage.kind is unsupported")
        entries.append(Entry(file_path, file_kind, size, mode, digest, storage_kind, storage_value))

    # No file can simultaneously be a parent directory for another path.
    for entry in entries:
        parent = PurePosixPath(entry.path)
        for candidate in parent.parents:
            if str(candidate) in paths:
                fail(f"file path is a parent of another file: {candidate} and {entry.path}")

    parts_data = raw.get("payloadParts")
    if not isinstance(parts_data, list):
        fail("manifest payloadParts must be a list")
    parts: list[Part] = []
    part_paths: set[str] = set()
    for index, record in enumerate(parts_data):
        if not isinstance(record, dict):
            fail(f"payloadParts[{index}] must be an object")
        part_path = record.get("path")
        safe_relative(part_path, f"payloadParts[{index}].path")
        if part_path in part_paths:
            fail(f"duplicate payload part path: {part_path}")
        part_paths.add(part_path)
        size, digest = record.get("size"), record.get("sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            fail(f"payloadParts[{index}].size must be a non-negative integer")
        if not is_hex(digest, SHA256_LEN):
            fail(f"payloadParts[{index}].sha256 must be lowercase SHA-256")
        parts.append(Part(Path(*PurePosixPath(part_path).parts), size, digest))

    expected_payload = {entry.storage_value for entry in entries if entry.storage_kind == "payload"}
    if expected_payload and not parts:
        fail("payload storage is referenced but payloadParts is empty")
    return raw, entries, parts


def git_blob(repo_root: Path, blob: str) -> bytes:
    process = subprocess.run(
        ["git", "-C", str(repo_root), "cat-file", "blob", blob],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.returncode:
        message = process.stderr.decode("utf-8", "replace").strip()
        fail(f"cannot read Git blob {blob}: {message or 'unknown Git error'}")
    return process.stdout


def verify_parts(manifest_dir: Path, parts: Iterable[Part], work_dir: Path) -> Path | None:
    parts = list(parts)
    if not parts:
        return None
    joined = work_dir / "payload.tar.xz"
    with joined.open("xb") as destination:
        for part in parts:
            source = manifest_dir / part.path
            size, digest = hash_path(source, "payload part")
            require_digest(size, digest, part.size, part.sha256, f"payload part {part.path}")
            with source.open("rb") as handle:
                shutil.copyfileobj(handle, destination, CHUNK)
    return joined


def verify_payload(joined: Path | None, expected_members: dict[str, int], work_dir: Path, materialize: bool) -> dict[str, Path]:
    if not expected_members:
        if joined is not None:
            # An empty payload is still a payload: it must be a valid empty archive.
            pass
        else:
            return {}
    if joined is None:
        fail("payload parts are required")
    objects_dir = work_dir / "payload-objects"
    if materialize:
        objects_dir.mkdir()
    seen: set[str] = set()
    try:
        archive = tarfile.open(joined, mode="r:xz")
    except (tarfile.TarError, lzma.LZMAError) as exc:
        fail(f"cannot read payload tar.xz: {exc}")
    with archive:
        for member in archive:
            if member.name in seen:
                fail(f"duplicate payload member: {member.name}")
            seen.add(member.name)
            if member.name not in expected_members or not is_hex(member.name, SHA256_LEN):
                fail(f"unexpected payload member: {member.name!r}")
            if not member.isfile() or member.issparse() or member.linkname:
                fail(f"payload member must be an ordinary non-sparse file: {member.name}")
            source = archive.extractfile(member)
            if source is None:
                fail(f"cannot read payload member: {member.name}")
            destination = objects_dir / member.name if materialize else None
            if destination is None:
                with source:
                    size, digest = hash_stream(source)
            else:
                with source, destination.open("xb") as output:
                    digest_state = hashlib.sha256()
                    size = 0
                    while True:
                        block = source.read(CHUNK)
                        if not block:
                            break
                        output.write(block)
                        digest_state.update(block)
                        size += len(block)
                    digest = digest_state.hexdigest()
            if digest != member.name:
                fail(f"payload member {member.name} does not match its SHA-256 name")
            if size != member.size:
                fail(f"payload member {member.name} has unexpected decompressed size")
            if size != expected_members[member.name]:
                fail(f"payload member {member.name} has size {size}, expected {expected_members[member.name]}")
    expected_names = set(expected_members)
    if seen != expected_names:
        missing = sorted(expected_names - seen)
        extra = sorted(seen - expected_names)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing[:3]))
        if extra:
            details.append("unexpected " + ", ".join(extra[:3]))
        fail("payload member set does not match manifest: " + "; ".join(details))
    return {member: objects_dir / member for member in expected_members} if materialize else {}


def verify_history_and_blobs(repo_root: Path, history_commit: str, entries: Iterable[Entry]) -> None:
    checked = subprocess.run(
        ["git", "-C", str(repo_root), "cat-file", "-e", f"{history_commit}^{{commit}}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    if checked.returncode:
        message = checked.stderr.decode("utf-8", "replace").strip()
        fail(f"historyCommit is not available as a commit: {message or history_commit}")
    # `rev-list --objects` follows only the named commit and its ancestors, not
    # local worktree snapshots or unreachable objects.  This makes a shallow
    # repository fail explicitly instead of accidentally restoring stale data.
    reachable_result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-list", "--objects", history_commit],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if reachable_result.returncode:
        message = reachable_result.stderr.decode("utf-8", "replace").strip()
        fail(f"cannot enumerate objects reachable from historyCommit: {message}")
    reachable = {line.split(maxsplit=1)[0].decode("ascii") for line in reachable_result.stdout.splitlines() if line}
    missing = sorted({entry.storage_value for entry in entries if entry.storage_kind == "git"} - reachable)
    if missing:
        fail("Git blobs are not reachable from historyCommit: " + ", ".join(missing[:3]))


def content_for(entry: Entry, manifest_dir: Path, repo_root: Path, payload_objects: dict[str, Path]) -> tuple[int, str, bytes | Path]:
    if entry.storage_kind == "git":
        content = git_blob(repo_root, entry.storage_value)
        size = len(content)
        digest = hashlib.sha256(content).hexdigest()
        return size, digest, content
    if entry.storage_kind == "file":
        source = manifest_dir / safe_relative(entry.storage_value, "storage path")
        size, digest = hash_path(source, "manifest source file")
        return size, digest, source
    source = payload_objects.get(entry.storage_value)
    if source is None:
        fail(f"payload object was not materialized: {entry.storage_value}")
    size, digest = hash_path(source, "payload object")
    return size, digest, source


def verify_entries(entries: Iterable[Entry], manifest_dir: Path, repo_root: Path, payload_objects: dict[str, Path]) -> None:
    for entry in entries:
        size, digest, _ = content_for(entry, manifest_dir, repo_root, payload_objects)
        require_digest(size, digest, entry.size, entry.sha256, f"file {entry.path}")


def write_content(destination: Path, content: bytes | Path) -> None:
    with destination.open("xb") as output:
        if isinstance(content, bytes):
            output.write(content)
        else:
            with content.open("rb") as source:
                shutil.copyfileobj(source, output, CHUNK)


def internal_link_target(entry: Entry, target: bytes, known_paths: set[str]) -> str:
    try:
        target_text = target.decode("utf-8", "surrogateescape")
    except UnicodeDecodeError:
        fail(f"symlink target is not representable on this platform: {entry.path}")
    if not target_text or "\x00" in target_text or "\\" in target_text:
        fail(f"symlink target is invalid: {entry.path}")
    target_path = PurePosixPath(target_text)
    if target_path.is_absolute():
        fail(f"symlink target is not internal: {entry.path}")
    resolved = posixpath.normpath(posixpath.join(str(PurePosixPath(entry.path).parent), target_text))
    if resolved in (".", "..") or resolved.startswith("../") or resolved not in known_paths:
        fail(f"symlink target does not resolve inside snapshot: {entry.path}")
    return target_text


def restore(entries: list[Entry], manifest_dir: Path, repo_root: Path, payload_objects: dict[str, Path], output: Path) -> None:
    if not output.is_absolute():
        fail("--output must be an absolute path")
    if output.exists() or output.is_symlink():
        fail(f"--output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(mode=0o700)
    try:
        regular = [entry for entry in entries if entry.kind == "file"]
        links = [entry for entry in entries if entry.kind == "symlink"]
        known_paths = {entry.path for entry in entries}
        for entry in regular:
            destination = output / safe_relative(entry.path, "file path")
            destination.parent.mkdir(parents=True, exist_ok=True)
            size, digest, content = content_for(entry, manifest_dir, repo_root, payload_objects)
            require_digest(size, digest, entry.size, entry.sha256, f"file {entry.path}")
            write_content(destination, content)
            os.chmod(destination, entry.mode)
        # Link targets are snapshot content and have already been hash-checked.  Links
        # are created after all regular files so an archive cannot redirect a write.
        for entry in links:
            destination = output / safe_relative(entry.path, "file path")
            destination.parent.mkdir(parents=True, exist_ok=True)
            size, digest, content = content_for(entry, manifest_dir, repo_root, payload_objects)
            require_digest(size, digest, entry.size, entry.sha256, f"file {entry.path}")
            if isinstance(content, Path):
                target = content.read_bytes()
            else:
                target = content
            # Links are allowed to contain ``..`` when the resolved target stays
            # inside this snapshot (as npm's .bin links normally do).
            target_text = internal_link_target(entry, target, known_paths)
            os.symlink(target_text, destination)
        verify_restored(entries, output)
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def verify_restored(entries: Iterable[Entry], output: Path) -> None:
    for entry in entries:
        target = output / safe_relative(entry.path, "file path")
        try:
            info = target.lstat()
        except FileNotFoundError:
            fail(f"restored file is missing: {entry.path}")
        if entry.kind == "file":
            if not stat.S_ISREG(info.st_mode):
                fail(f"restored file has wrong type: {entry.path}")
            size, digest = hash_path(target, "restored file")
        else:
            if not stat.S_ISLNK(info.st_mode):
                fail(f"restored symlink has wrong type: {entry.path}")
            raw_target = os.fsencode(os.readlink(target))
            size, digest = len(raw_target), hashlib.sha256(raw_target).hexdigest()
        require_digest(size, digest, entry.size, entry.sha256, f"restored file {entry.path}")
        actual_mode = stat.S_IMODE(info.st_mode)
        if actual_mode != entry.mode:
            fail(f"restored file {entry.path} has mode {oct(actual_mode)}, expected {oct(entry.mode)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--verify", action="store_true", help="verify the manifest and all stored content")
    group.add_argument("--output", metavar="NEW_ABSOLUTE_DIRECTORY", help="restore into a new absolute directory")
    parser.add_argument("--manifest", metavar="PATH", help="manifest path (default: repository archive manifest)")
    arguments = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    manifest_path = Path(arguments.manifest).expanduser().resolve() if arguments.manifest else repo_root / DEFAULT_MANIFEST
    output = Path(arguments.output).expanduser() if arguments.output else None
    try:
        manifest, entries, parts = load_manifest(manifest_path)
        if output is not None and not output.is_absolute():
            fail("--output must be an absolute path")
        if output is not None and (output.exists() or output.is_symlink()):
            fail(f"--output already exists: {output}")
        verify_history_and_blobs(repo_root, manifest["historyCommit"], entries)
        manifest_dir = manifest_path.parent
        with tempfile.TemporaryDirectory(prefix="science-day-archive-") as temp_name:
            work_dir = Path(temp_name)
            joined = verify_parts(manifest_dir, parts, work_dir)
            payload_ids: dict[str, int] = {}
            for entry in entries:
                if entry.storage_kind == "payload":
                    previous = payload_ids.setdefault(entry.storage_value, entry.size)
                    if previous != entry.size:
                        fail(f"payload member has conflicting expected sizes: {entry.storage_value}")
            objects = verify_payload(joined, payload_ids, work_dir, materialize=bool(output))
            # --verify does not need a copy of payload files.  Verify their hashes while
            # reading the tar, then verify the Git and readable-source records.
            if not output:
                verify_entries((entry for entry in entries if entry.storage_kind != "payload"), manifest_dir, repo_root, objects)
            else:
                # Objects are materialized and every file is verified before creation.
                verify_entries(entries, manifest_dir, repo_root, objects)
                restore(entries, manifest_dir, repo_root, objects, output)
        print("archive verification passed" if not output else f"archive restored and verified: {output}")
        return 0
    except (ArchiveError, OSError, subprocess.SubprocessError, tarfile.TarError, lzma.LZMAError) as exc:
        print(f"archive verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
