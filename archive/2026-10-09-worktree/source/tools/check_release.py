#!/usr/bin/env python3
"""Единая приёмка поставки «Охота за звёздными аномалиями».

Режимы:
  tools/check_release.py               — ПОЛНАЯ попытка приёмки (все группы).
  tools/check_release.py --model-only  — под check: только модель (не считается попыткой).
  tools/check_release.py --browser-only|artifacts-only|data-only — аналогично, по группам.
  tools/check_release.py --status      — показать журнал попыток и выйти.

Правила бюджета (контракт):
  • Полных попыток не более ПЯТИ; счёт ведёт только этот драйвер, честно, в
    verification/attempts.json. Подпроверки (--*-only) попытки НЕ расходуют.
  • Попытка регистрируется до старта групп и получает финальный статус
    pass/fail/interrupted — прерванная попытка тоже считается.
  • Код 0 только если ВСЕ реальные проверки прошли. Отказ из-за исчерпанного
    бюджета — код 2. Нет окружения — код 3; полный запуск всё равно расходует
    попытку, включая ошибки окружения и прерывания.
  • Вне среды остаются непроверяемыми и честно печатаются: нативные macOS/Safari,
    физический телефон, печать на бумаге.

Перед полным запуском: python3 -m venv .venv && .venv/bin/pip install -r tools/requirements-verify.txt
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
from verify_common import (APP, DIST, Timer, chromium_executable, eprint,  # noqa: E402
                           fresh_dir, js_runner)

MAX_ATTEMPTS = 5
OUT = ROOT / "verification"
ATTEMPTS = OUT / "attempts.json"
PY = Path(sys.executable)


# ---------------------------------------------------------------- окружение

def ensure_env() -> Path:
    """Возвращает интерпретатор с зависимостями без повторной регистрации запуска."""
    need = ("playwright", "numpy", "PIL")
    missing = []
    for m in need:
        try:
            __import__(m)
        except ImportError:
            missing.append(m)
    venv_py = ROOT / ".venv" / "bin" / "python"
    if missing:
        if venv_py.is_file() and Path(sys.prefix).resolve() != venv_py.parent.parent.resolve():
            probe = subprocess.run(
                [str(venv_py), "-c", "import playwright, numpy, PIL"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if probe.returncode == 0:
                return venv_py
        eprint("Нет зависимостей приёмки: " + ", ".join(missing))
        eprint("Установите: python3 -m venv .venv && .venv/bin/pip install -r tools/requirements-verify.txt")
        sys.exit(3)
    return PY


def preflight(js: list[str] | None) -> str | None:
    """Проверка браузера/рантайма. Текст проблемы или None."""
    has_ff = any((Path.home() / ".cache" / "ms-playwright").glob("firefox-*"))
    if chromium_executable() is None and not has_ff:
        return "нет Chromium (~/.cache/ms-playwright/chromium-1234) и Firefox — браузерные проверки невозможны"
    if js is None:
        return "нет ни bun, ни node — модельные проверки (check_model.mjs) не запустить"
    for tool in ("pdfinfo", "pdftoppm", "pdftotext", "unzip"):
        if shutil.which(tool) is None:
            return f"нет утилиты {tool} (poppler-utils / unzip)"
    return None


# ---------------------------------------------------------------- журнал попыток

def read_attempts() -> dict:
    if ATTEMPTS.is_file():
        try:
            return json.loads(ATTEMPTS.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            eprint("verification/attempts.json повреждён — требую ручного разбора, попытки не списываю")
            sys.exit(3)
    return {"max_attempts": MAX_ATTEMPTS, "note": "считаются только полные попытки; подпроверки --*-only не считаются", "attempts": []}


def write_attempts(doc: dict) -> None:
    ATTEMPTS.parent.mkdir(parents=True, exist_ok=True)
    ATTEMPTS.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- запуск групп

def run_suite(name: str, cmd: list[str], log_path: Path) -> tuple[bool, str]:
    """Запускает группу, потоками показывает вывод и кладёт полный лог."""
    print(f"\n——— ГРУППА: {name} ———")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=3600)
    log_path.write_text(proc.stdout, encoding="utf-8")
    tail = proc.stdout.strip().splitlines()[-14:]
    for ln in tail:
        print(f"  | {ln}")
    dt = round(time.monotonic() - t0, 1)
    ok = proc.returncode == 0
    print(f"——— {name}: {'PASS' if ok else 'FAIL'} (код {proc.returncode}, {dt} с, лог: {log_path.name}) ———")
    return ok, proc.stdout[-4000:]


def execute_full(n: int) -> int:
    """Одна полная попытка: все группы, сводка, журнал."""
    timer = Timer()
    fresh_dir(OUT / "tmp")
    entry = read_attempts()["attempts"][n - 1]
    print(f"\n=== ПОЛНАЯ ПОПЫТКА ПРИЁМКИ {n}/{MAX_ATTEMPTS} ===")

    js = js_runner()
    dump = OUT / "data-dump.json"
    suites: list[tuple[str, list[str], Path]] = [
        ("Модель (модульные регрессии)", js + [str(TOOLS / "check_model.mjs")], OUT / "logs" / "model.log"),
        ("Дамп реальных данных", js + [str(TOOLS / "check_model.mjs"), "--dump", str(dump)], OUT / "logs" / "dump.log"),
        ("Артефакты: архивы, установщик, PDF, источники, данные и происхождение",
         [str(PY), str(TOOLS / "check_artifacts.py"), "--dist", str(DIST), "--out", str(OUT),
          "--data-dump", str(dump)], OUT / "logs" / "artifacts.log"),
    ]
    installed = ""
    paths_file = OUT / "paths.json"
    artifacts_ok = False
    # Сначала модель+дамп+артефакты, затем браузер (ему нужен paths.json от установщика).
    failures: list[str] = []
    for name, cmd, log in suites:
        ok, _ = run_suite(name, cmd, log)
        if name.startswith("Артефакты"):
            artifacts_ok = ok
        if not ok:
            failures.append(name)
    if paths_file.is_file():
        try:
            installed = (json.loads(paths_file.read_text(encoding="utf-8")) or {}).get("installed_dir") or ""
        except json.JSONDecodeError:
            installed = ""
    browser_cmd = [str(PY), str(TOOLS / "check_browser.py"), "--app", str(APP),
                   "--dist", str(DIST), "--out", str(OUT)]
    if installed and Path(installed).is_dir():
        browser_cmd += ["--installed", installed]
    ok_browser, _ = run_suite("Браузер: file://, HTTP-офлайн, клавиатура, 390px, reduced-motion, телефон, установленная копия",
                              browser_cmd, OUT / "logs" / "browser.log")
    if not ok_browser:
        failures.append("Браузер")
    if not artifacts_ok and "Артефакты" not in failures:
        failures.append("Артефакты")

    passed = not failures
    entry.update({
        "status": "pass" if passed else "fail",
        "failed_suites": failures,
        "duration_s": timer.seconds(),
        "finished": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    doc = read_attempts()
    doc["attempts"][-1] = entry
    write_attempts(doc)

    print(f"\n=== ПОЛНАЯ ПОПЫТКА {n}/{MAX_ATTEMPTS}: {'ПРОЙДЕНА' if passed else 'ПРОВАЛ'} "
          f"({entry['duration_s']} с) ===")
    if failures:
        print("Проваленные группы:")
        for f in failures:
            print(f"  - {f}")
    print("Вне среды (честно не проверялось): нативные macOS/Safari, физический телефон, бумажная печать.")
    print(f"Журнал попыток: {ATTEMPTS}")
    return 0 if passed else 1


def execute_subcheck(kind: str) -> int:
    """Подпроверка одной группы: попытку НЕ списывает (пишет это явно)."""
    print(f"=== ПОДПРОВЕРКА: {kind} — ПОЛНОЙ ПОПЫТКОЙ НЕ СЧИТАЕТСЯ ===")
    fresh_dir(OUT / "tmp")
    js = js_runner()
    if kind == "model":
        if js is None:
            eprint("нет bun/node")
            return 3
        ok, _ = run_suite("Модель", js + [str(TOOLS / "check_model.mjs")], OUT / "logs" / "model.log")
        return 0 if ok else 1
    if kind == "data":
        if js is None:
            eprint("нет bun/node")
            return 3
        dump = OUT / "data-dump.json"
        run_suite("Дамп данных", js + [str(TOOLS / "check_model.mjs"), "--dump", str(dump)],
                  OUT / "logs" / "dump.log")
        ok, _ = run_suite("Данные и происхождение",
                          [str(PY), str(TOOLS / "check_artifacts.py"), "--only-data",
                           "--dist", str(DIST), "--out", str(OUT), "--data-dump", str(dump)],
                          OUT / "logs" / "artifacts-data.log")
        return 0 if ok else 1
    if kind == "artifacts":
        ok, _ = run_suite("Артефакты",
                          [str(PY), str(TOOLS / "check_artifacts.py"), "--dist", str(DIST),
                           "--out", str(OUT)], OUT / "logs" / "artifacts.log")
        return 0 if ok else 1
    if kind == "browser":
        installed = ""
        if (OUT / "paths.json").is_file():
            try:
                installed = (json.loads((OUT / "paths.json").read_text(encoding="utf-8")) or {}).get("installed_dir") or ""
            except json.JSONDecodeError:
                installed = ""
        cmd = [str(PY), str(TOOLS / "check_browser.py"), "--app", str(APP),
               "--dist", str(DIST), "--out", str(OUT)]
        if installed and Path(installed).is_dir():
            cmd += ["--installed", installed]
        ok, _ = run_suite("Браузер", cmd, OUT / "logs" / "browser.log")
        return 0 if ok else 1
    eprint(f"неизвестная подпроверка: {kind}")
    return 3


def show_status() -> int:
    doc = read_attempts()
    print(f"Полных попыток: {len(doc['attempts'])}/{doc.get('max_attempts', MAX_ATTEMPTS)}")
    for a in doc["attempts"]:
        print(f"  #{a['n']} {a.get('started')} — {a.get('status')}"
              + (f", провал: {', '.join(a.get('failed_suites', []))}" if a.get("failed_suites") else "")
              + (f", {a.get('duration_s')} с" if a.get("duration_s") else ""))
    return 0


def main() -> int:
    global PY
    ap = argparse.ArgumentParser(description="Единая приёмка (см. шапку файла)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--model-only", action="store_true")
    g.add_argument("--data-only", action="store_true")
    g.add_argument("--artifacts-only", action="store_true")
    g.add_argument("--browser-only", action="store_true")
    g.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        return show_status()

    if any((args.model_only, args.data_only, args.artifacts_only, args.browser_only)):
        PY = ensure_env()
        kind = ("model" if args.model_only else "data" if args.data_only
                else "artifacts" if args.artifacts_only else "browser")
        if kind != "model":
            js = js_runner()  # для дампа данных
        problem = preflight(js_runner())
        if problem and kind != "model":
            eprint(f"Окружение не готово: {problem}")
            return 3
        return execute_subcheck(kind)

    doc = read_attempts()
    used = len(doc["attempts"])
    if used >= MAX_ATTEMPTS:
        eprint(f"Бюджет приёмки исчерпан: {used}/{MAX_ATTEMPTS} полных попыток. "
               f"Журнал: {ATTEMPTS}. Новые прогоны требуют явного решения владельца.")
        for a in doc["attempts"]:
            eprint(f"  #{a['n']} {a.get('status')} {a.get('started')}"
                   + (f" провал: {', '.join(a.get('failed_suites', []))}" if a.get("failed_suites") else ""))
        return 2

    n = used + 1
    entry = {
        "n": n, "mode": "full", "status": "interrupted",
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "host": os.uname().nodename,
    }
    doc["attempts"].append(entry)
    write_attempts(doc)
    try:
        PY = ensure_env()
        problem = preflight(js_runner())
        if problem:
            eprint(f"Окружение не готово: {problem}")
            raise SystemExit(3)
    except SystemExit:
        entry.update(status="fail", failed_suites=["Окружение"],
                     finished=time.strftime("%Y-%m-%dT%H:%M:%S"))
        write_attempts(doc)
        raise
    return execute_full(n)


if __name__ == "__main__":
    sys.exit(main())
