# Общие помощники приёмочной проверки (check_release/check_browser/check_artifacts).
# Только стандартная библиотека — тяжёлые импорты в самих проверках.
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
APP = ROOT / "app"
DIST = ROOT / "dist"
ASSETS_REAL = ROOT / "assets" / "real"
CREDITS = ASSETS_REAL / "CREDITS.md"

# Разрешённый состав поставки (контракт): ядро приложения + сопроводительные файлы.
CORE_RELEASE_FILES = (
    "science-day/index.html",
    "science-day/game.css",
    "science-day/game.js",
    "science-day/model.js",
    "science-day/sky-map.js",
    "science-day/sky-map.css",
    "science-day/sky-data.js",
    "science-day/discovery-data.js",
    "science-day/data.js",
    "science-day/content.js",
    "science-day/nightshift-evidence.js",
    "science-day/nightshift-content.js",
    "science-day/nightshift-model.js",
    "science-day/nightshift-art.js",
    "science-day/nightshift.js",
    "science-day/nightshift.css",
    "science-day/install.sh",
    "science-day/sky-source.zip",
)

CHROMIUM_DIR = Path.home() / ".cache" / "ms-playwright"


class CheckResults:
    """Копилка результатов одной группы проверок."""

    def __init__(self, title: str):
        self.title = title
        self.rows: list[dict] = []
        self.failures: list[str] = []

    def add(self, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            self.failures.append(f"{name}" + (f" — {detail}" if detail else ""))
            print(f"FAIL  {name}" + (f" — {detail}" if detail else ""))
        else:
            print(f"  ok  {name}" + (f" — {detail}" if detail else ""))
        return ok

    @property
    def ok(self) -> bool:
        return not self.failures

    def dump(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(
            {"title": self.title, "ok": self.ok, "checks": self.rows,
             "failures": self.failures},
            ensure_ascii=False, indent=1), encoding="utf-8")


def run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None,
        timeout: int = 600, check: bool = False) -> subprocess.CompletedProcess:
    """Запуск процесса с перехватом вывода; raise на таймауте всегда."""
    proc = subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, env=env,
        capture_output=True, text=True, timeout=timeout)
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"команда {' '.join(cmd)} вернула {proc.returncode}\n"
            f"stdout: {proc.stdout[-2000:]}\nstderr: {proc.stderr[-2000:]}")
    return proc


def js_runner() -> list[str] | None:
    """Первый работающий рантайм JS: bun, затем node (проверяем живьём)."""
    for exe, probe, expect in (("bun", ["--version"], "."), ("node", ["-e", "process.stdout.write('js-ok')"], "js-ok")):
        try:
            proc = run([exe] + probe, timeout=30)
            if proc.returncode == 0 and expect in proc.stdout:
                return [exe]
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None


def chromium_executable() -> Path | None:
    """Реальный Chromium из кэша Playwright (контракт: chromium-1234 первым)."""
    env = os.environ.get("PW_CHROMIUM")
    if env and Path(env).exists():
        return Path(env)
    pinned = CHROMIUM_DIR / "chromium-1234" / "chrome-linux" / "chrome"
    if pinned.exists():
        return pinned
    candidates = sorted(glob.glob(str(CHROMIUM_DIR / "chromium-*" / "chrome-linux" / "chrome")))
    return Path(candidates[-1]) if candidates else None


def firefox_executable() -> Path | None:
    candidates = sorted(glob.glob(str(CHROMIUM_DIR / "firefox-*" / "firefox" / "firefox")))
    return Path(candidates[-1]) if candidates else None


def pdf_tools() -> tuple[bool, bool]:
    """Наличие pdftotext и (pdfinfo, pdftoppm) одним взглядом."""
    pdftotext = shutil.which("pdftotext") is not None
    info_ppm = shutil.which("pdfinfo") is not None and shutil.which("pdftoppm") is not None
    return pdftotext, info_ppm


def fresh_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


class Timer:
    def __init__(self):
        self.t0 = time.monotonic()

    def seconds(self) -> float:
        return round(time.monotonic() - self.t0, 1)


def eprint(*args) -> None:
    print(*args, file=sys.stderr)
