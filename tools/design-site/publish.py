#!/usr/bin/env python3
"""Publish a Git snapshot atomically; never build from a dirty checkout."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request


def command(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if result.returncode:
        # Do not copy arbitrary subprocess output into a public receipt or log.
        raise RuntimeError(f"{Path(str(args[0])).name} failed (exit {result.returncode})")
    return result.stdout.strip()


def switch_link(path, target):
    temporary = path.with_name(path.name + ".next")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    temporary.replace(path)


def verify_files(site, revision):
    manifest = json.loads((site / "manifest.json").read_text())
    if manifest["revision"] != revision:
        raise ValueError("Build revision does not match the requested commit")
    files = manifest["files"]
    if not files or "index.html" not in files:
        raise ValueError("Manifest does not contain the catalogue")
    for name, expected in files.items():
        path = site / name
        if not path.resolve().is_relative_to(site.resolve()) or path.is_symlink():
            raise ValueError("Manifest path escapes the release")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Build checksum mismatch: {name}")
    return manifest


def verify_served(base, revision):
    url = base.rstrip("/") + "/design/manifest.json"
    with urllib.request.urlopen(url, timeout=15) as response:
        manifest = json.load(response)
    if manifest["revision"] != revision:
        raise RuntimeError("Served revision does not match the selected release")


def verify_ci(revision):
    url = ("https://api.github.com/repos/fall-out-bug/msu_science_day_2026/actions/runs"
           f"?head_sha={revision}&event=push&per_page=100")
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                  "User-Agent": "science-day-design-publisher"})
    with urllib.request.urlopen(request, timeout=20) as response:
        runs = json.load(response)["workflow_runs"]
    matching = [run for run in runs if run.get("head_sha") == revision
                and run.get("head_branch") == "main"
                and run.get("path", "").split("@", 1)[0] == ".github/workflows/design-docs.yml"]
    latest = max(matching, key=lambda run: run["id"], default=None)
    if not latest or latest.get("status") != "completed" or latest.get("conclusion") != "success":
        raise RuntimeError("Waiting for successful Design documents CI on this main commit")


def activate(published, target, base=None):
    current = published / "current"
    previous = os.readlink(current) if current.is_symlink() else None
    revision = json.loads((published / target / "manifest.json").read_text())["revision"]
    switch_link(current, target)
    try:
        if base:
            verify_served(base, revision)
    except Exception:
        if previous:
            switch_link(current, previous)
        else:
            current.unlink()
        raise
    if previous and previous != target:
        switch_link(published / "previous", previous)


def publish(args):
    repo, state = args.repo.resolve(), args.state.resolve()
    state.mkdir(parents=True, exist_ok=True)
    published = state / "published"
    (published / "releases").mkdir(parents=True, exist_ok=True)
    with (state / "publish.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.rollback:
            previous = published / "previous"
            if not previous.is_symlink():
                raise RuntimeError("No previous publication")
            target = os.readlink(previous)
            if not (published / target).resolve().is_relative_to((published / "releases").resolve()):
                raise ValueError("Invalid rollback release")
            revision = json.loads((published / target / "manifest.json").read_text())["revision"]
            verify_files(published / target, revision)
            activate(published, target, args.verify_base)
            print(json.dumps({"status": "rolled_back", "revision": revision}))
            return
        if args.sync_main:
            command(["git", "-C", str(repo), "-c", "credential.helper=", "fetch", "--quiet", "--no-tags",
                     "https://github.com/fall-out-bug/msu_science_day_2026.git",
                     "+refs/heads/main:refs/remotes/origin/main"], timeout=120,
                    env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        ref = "origin/main" if args.sync_main else args.ref
        revision = command(["git", "-C", str(repo), "rev-parse", "--verify", ref + "^{commit}"])
        trees = command(["git", "-C", str(repo), "rev-parse", revision + ":docs", revision + ":tools/design-site"])
        tree_key = hashlib.sha256(trees.encode()).hexdigest()
        receipt = published / "current" / "publication.json"
        if receipt.is_file() and json.loads(receipt.read_text()).get("treeKey") == tree_key:
            if args.verify_base:
                verify_served(args.verify_base, json.loads(receipt.read_text())["revision"])
            print(json.dumps({"status": "unchanged", "revision": json.loads(receipt.read_text())["revision"]}))
            return
        if args.sync_main:
            verify_ci(revision)
        with tempfile.TemporaryDirectory(prefix="build-", dir=state) as temporary:
            work = Path(temporary)
            archive = work / "source.tar"
            command(["git", "-C", str(repo), "archive", "--format=tar", "--output=" + str(archive),
                     revision, "docs", "tools/design-site"])
            source = work / "source"
            source.mkdir()
            with tarfile.open(archive) as bundle:
                bundle.extractall(source, filter="data")
            site = work / "site"
            command([sys.executable, str(source / "tools/design-site/build.py"),
                     "--source", str(source), "--output", str(site), "--revision", revision], timeout=120)
            command([sys.executable, str(source / "tools/design-site/check.py"), str(site)], timeout=60)
            manifest = verify_files(site, revision)
            (site / "publication.json").write_text(json.dumps({"revision": revision, "treeKey": tree_key}) + "\n")
            target = "releases/" + revision
            destination = published / target
            if destination.exists():
                # Immutable commits have deterministic output; never overwrite a release.
                verify_files(destination, revision)
                if (destination / "manifest.json").read_bytes() != (site / "manifest.json").read_bytes():
                    raise ValueError("Existing release differs from this build")
            else:
                shutil.move(str(site), destination)
            activate(published, target, args.verify_base)
            print(json.dumps({"status": "published", "revision": revision, "files": len(manifest["files"])}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=Path.home() / ".local/share/science-day/design-site")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--sync-main", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    parser.add_argument("--ref", default="HEAD", help="Commit to publish without fetching")
    parser.add_argument("--verify-base", help="HTTP(S) origin serving /design/, checked after switching")
    args = parser.parse_args()
    try:
        publish(args)
    except BlockingIOError:
        print("Another publication is already running")
        return 75
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"Design publication failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
