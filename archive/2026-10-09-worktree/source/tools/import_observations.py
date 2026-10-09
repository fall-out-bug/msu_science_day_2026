#!/usr/bin/env python3
"""Загрузка и научное курирование реальных наблюдений ZTF.

Источники (все публичные, авторские обязательства — verbatim в manifest):
  • Пиксели: IRSA IBE, продукт ztf/products/sci (+ ref — опорные стеки), ZTF Public Survey.
  • Метаданные одиночных детекций (до DR8): IRSA ZTF Light Curve API.
  • Метаданные детекций после DR8 и ML-кандидаты: ALeRCE broker (только метаданные;
    пиксели ALeRCE не распространяем — права на брокерные вырезки не опубликованы).
  • Идентификация движущихся объектов: SkyBoT (IMCCE, VO-SSP).

Кэш: assets/observations/cache/{sci,ref}/<basename>.fits.gz + запись в manifest
(URL, размер, sha256, ключевые поля заголовка). Генерация data.js идёт офлайн
только по кэшу и manifest.

Запуск (примеры):
  python3 tools/import_observations.py sn
  python3 tools/import_observations.py variable --oid ZTF… --amp-min 0.5
  python3 tools/import_observations.py merge-handoff --path <handoff.json>
  python3 tools/import_observations.py download
  python3 tools/import_observations.py verify
Зависимости: см. tools/requirements.txt (numpy, astropy, scipy, requests, Pillow).
"""
import argparse
import csv
import gzip
import io
import json
import sys
import time
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
OBS = ROOT / "assets" / "observations"
CACHE_SCI = OBS / "cache" / "sci"
CACHE_REF = OBS / "cache" / "ref"
MANIFEST = OBS / "manifest.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

IBE = "https://irsa.ipac.caltech.edu/ibe"
LC_URL = "https://irsa.ipac.caltech.edu/cgi-bin/ZTF/nph_light_curves"
ALERC = "https://api.alerce.online/ztf/v1"
SKYBOT = "https://ssp.imcce.fr/webservices/skybot/api/conesearch.php"

SURVEY = {
    "name": "ZTF Public Survey, IRSA Image Backend (ztf/products/sci, ztf/products/ref)",
    "release_page": "https://ztf.ipac.caltech.edu/page/dr8",
    "doi_image_service": "10.26131/IRSA539",
    "ack_phase1_valid": "наблюдения до 2020-12-01",
    "ack_phase2_valid": "наблюдения с 2020-12-01",
    "phase1": (
        "Based on observations obtained with the Samuel Oschin 48-inch Telescope "
        "at the Palomar Observatory as part of the Zwicky Transient Facility "
        "project. ZTF is supported by the National Science Foundation under "
        "Grant No. AST-1440341 and a collaboration including Caltech, IPAC, the "
        "Weizmann Institute for Science, the Oskar Klein Center at Stockholm "
        "University, the University of Maryland, the University of Washington, "
        "Deutsches Elektronen-Synchrotron and Humboldt University, Los Alamos "
        "National Laboratories, the TANGO Consortium of Taiwan, the University "
        "of Wisconsin at Milwaukee, and Lawrence Berkeley National Laboratories. "
        "Operations are conducted by COO, IPAC, and UW."),
    "phase2": (
        "Based on observations obtained with the Samuel Oschin Telescope 48-inch "
        "and the 60-inch Telescope at the Palomar Observatory as part of the "
        "Zwicky Transient Facility project. ZTF is supported by the National "
        "Science Foundation under Grant No. AST-2034437 and a collaboration "
        "including Caltech, IPAC, the Weizmann Institute for Science, the Oskar "
        "Klein Center at Stockholm University, the University of Maryland, "
        "Deutsches Elektronen-Synchrotron and Humboldt University, the TANGO "
        "Consortium of Taiwan, the University of Wisconsin at Milwaukee, Trinity "
        "College Dublin, Lawrence Livermore National Laboratories, and INAF. "
        "Operations are conducted by COO, IPAC, and UW."),
    "citation_masci": "Masci et al. 2018, PASP 131, 995 (cтандартная ссылка ZTF)",
    "citation_alerce": ("Förster et al. 2021, AJ 161, 242; Sánchez-Sáez et al. "
                        "2021, AJ 161, 141 — брокер ALeRCE (только метаданные)"),
    "citation_skybot": "Berthier et al. 2006, ASPC 351, 367 — SkyBoT/IMCCE (VO-SSP)",
}

PARAMS = {
    "patch": 128, "cutout_arcsec": 420.0, "cal_zp": 25.0,
    "epoch_rule": ("Три экспозиции одного фильтра; времена, фильтр и поле "
                   "записаны в каждом случае. Порядок — хронологический."),
}


def cutout_center_for(patch_ra, patch_dec, scale_as=1.012):
    """Центр вырезки = центр игрового патча (патч центрирован на цели)."""
    return float(patch_ra), float(patch_dec)

_session = requests.Session()


def _get(url, params=None, retries=4, timeout=240):
    last = None
    for attempt in range(retries):
        try:
            r = _session.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.content
            last = RuntimeError(f"HTTP {r.status_code}: {url} {r.text[:200]}")
        except requests.RequestException as exc:
            last = exc
        time.sleep(2.0 * (attempt + 1))
    raise last


# --- IRSA IBE ---------------------------------------------------------------

def ibe_search(pos, size_deg=None, where=None, product="sci", columns=None):
    q = ["ct=csv"]
    if pos is not None:
        q.insert(0, f"POS={pos[0]},{pos[1]}")
    if size_deg:
        q.append(f"SIZE={size_deg}")
    if columns:
        q.append(f"COLUMNS={columns}")
    if where:
        q.append(f"WHERE={where}")
    raw = _get(f"{IBE}/search/ztf/products/{product}?" +
               "&".join(x.replace("&", "%26") for x in q))
    text = raw.decode("utf-8", errors="replace")
    if text.startswith("<?xml") or "QUERY_STATUS" in text[:2000]:
        raise RuntimeError(f"IBE error: {text[:300]}")
    rows = list(csv.DictReader(io.StringIO(text)))
    return rows


def sci_relpath(row):
    """Путь файла внутри ztf/products/sci: YYYY/MMDD/ffd6/name.fits."""
    ffd = str(row["filefracday"])
    date = row["obsdate"]                     # '2023-10-05 11:47:…+00'
    year, mmdd = date[0:4], date[5:7] + date[8:10]
    name = (f"ztf_{ffd}_{int(row['field']):06d}_{row['filtercode']}"
            f"_c{int(row['ccdid']):02d}_o_q{int(row['qid'])}_sciimg.fits")
    return f"{year}/{mmdd}/{ffd[-6:]}/{name}"


def sci_data_url(row):
    return f"{IBE}/data/ztf/products/sci/{sci_relpath(row)}"


def cutout_url(row, center, arcsec, gzip=False):
    return (f"{sci_data_url(row)}?center={center[0]},{center[1]}"
            f"&size={arcsec}arcsec&gzip={'true' if gzip else 'false'}")


def irsa_lc(ra, dec, radius_deg=0.0008):
    url = (f"{LC_URL}?POS=CIRCLE+{ra}+{dec}+{radius_deg}"
           f"&BAD_CATFLAGS_MASK=32768&FORMAT=csv")
    raw = _get(url)
    text = raw.decode("utf-8", errors="replace")
    if "QUERY_STATUS" in text[:2000] and "ERROR" in text[:2000]:
        raise RuntimeError(f"LC error: {text[:300]}")
    return list(csv.DictReader(io.StringIO(text)))


def lc_clean(rows, filt="zr"):
    """Только zr, catflags=0; ccdid/qid из '0x…' → int."""
    out = []
    for r in rows:
        if r["filtercode"] != filt or int(r["catflags"]) != 0:
            continue
        out.append({
            "mjd": float(r["mjd"]), "mag": float(r["mag"]),
            "err": float(r["magerr"]), "expid": int(r["expid"]),
            "filefracday": r["filefracday"], "field": int(r["field"]),
            "ccdid": int(r["ccdid"], 16), "qid": int(r["qid"], 16),
            "limitmag": float(r["limitmag"]), "ra": float(r["ra"]),
            "dec": float(r["dec"]), "exptime": float(r["exptime"]),
        })
    out.sort(key=lambda d: d["mjd"])
    return out


# --- ALeRCE (только метаданные) ----------------------------------------------

def alerce(path, params=None):
    return json.loads(_get(f"{ALERC}{path}", params=params))


# --- SkyBoT ------------------------------------------------------------------

def skybot(ra, dec, epoch_iso, radius_arcsec=1200):
    raw = _get(SKYBOT, params={
        "-ep": epoch_iso, "-ra": f"{ra:.6f}", "-dec": f"{dec:.6f}",
        "-rs": int(radius_arcsec), "-mime": "text", "-output": "basic",
        "-observer": "675", "-filter": "120", "-objFilter": "100",
        "-refsys": "EQJ2000", "-from": "science_day_atlas"})
    out = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if line.startswith("#") or "|" not in line:
            continue
        p = [x.strip() for x in line.split("|")]
        # Num | Name | RA(h) | DE(deg) | Class | Mv | Err | d | dRA | dDEC | Dg | Dh
        try:
            out.append({
                "num": int(p[0]) if p[0] else None, "name": p[1],
                "ra": _sex_ra(p[2]), "dec": _sex_dec(p[3]),
                "cls": p[4], "vmag": float(p[5]), "pos_err": float(p[6]),
                "dra": float(p[8]), "ddec": float(p[9]),
            })
        except (ValueError, IndexError):
            continue
    return out


def _sex_ra(text):
    h, m, s = text.split()
    return (int(h) + int(m) / 60 + float(s) / 3600) * 15.0


def _sex_dec(text):
    sign = -1.0 if text.strip().startswith("-") else 1.0
    d, m, s = text.replace("-", " ").split()
    return sign * (int(d) + int(m) / 60 + float(s) / 3600)


# --- cache / manifest ---------------------------------------------------------

def cache_file(kind, basename, data):
    """Сохранить поток в cache/<kind>/<basename>.fits.gz, вернуть запись."""
    d = CACHE_SCI if kind == "sci" else CACHE_REF
    d.mkdir(parents=True, exist_ok=True)
    stem = basename[:-5] if basename.endswith(".fits") else basename
    path = d / f"{stem}.fits.gz"
    payload = data if data[:2] == b"\x1f\x8b" else gzip.compress(data, 6)
    path.write_bytes(payload)
    return path


def grab_cutout(row, center, arcsec=None, product="sci"):
    """Скачать вырезку, сохранить в кэш, вернуть dict записи (URL, sha, header)."""
    from tools.realdata import load_fits, pixel_scale
    arcsec = arcsec or PARAMS["cutout_arcsec"]
    url = cutout_url(row, center, arcsec)
    raw = _get(url)
    if b"Simple Image Access" in raw[:400] or raw[:15].startswith(b"<!DOCTYPE"):
        raise RuntimeError(f"cutout failed: {raw[:200]!r}")
    name = sci_relpath(row).split("/")[-1]
    stem = name[:-5] if name.endswith(".fits") else name
    tag = __import__("hashlib").sha256(
        f"{center[0]:.6f},{center[1]:.6f},{arcsec}".encode()).hexdigest()[:10]
    path = cache_file(product, f"{stem}_{tag}", raw)
    _, hdr = load_fits(path)
    rec = {
        "file": f"cache/{product}/{path.name}",
        "url": url, "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "header": {
            "obsmjd": hdr.get("OBSMJD"), "exptime": hdr.get("EXPTIME"),
            "filter": hdr.get("FILTER"), "fieldid": hdr.get("FIELDID"),
            "ccdid": hdr.get("CCD_ID"), "qid": hdr.get("QID"),
            "magzp": hdr.get("MAGZP"), "seeing": hdr.get("SEEING"),
            "maglim": hdr.get("MAGLIM"), "airmass": hdr.get("AIRMASS"),
            "moonillf": hdr.get("MOONILLF"), "infobits": hdr.get("INFOBITS"),
            "progremid": hdr.get("PROGRMID"), "pixscale_as": round(
                pixel_scale(hdr), 6),
        },
    }
    return rec


def manifest_load():
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"manifest_version": 1, "survey": SURVEY, "params": PARAMS,
            "cases": {}, "demo": {}, "training": {}, "files": {},
            "curation_log": [], "leakage_policy": []}


def manifest_save(man):
    man["params"] = PARAMS
    OBS.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST.with_suffix(".tmp")
    tmp.write_text(json.dumps(man, ensure_ascii=False, indent=1, sort_keys=True),
                   encoding="utf-8")
    tmp.replace(MANIFEST)


def register_file(man, rec):
    man["files"][rec["file"]] = {"url": rec["url"], "bytes": rec["bytes"],
                                 "sha256": rec["sha256"]}


def log(man, msg):
    man["curation_log"].append(msg)
    print("  [курирование]", msg)


# --- доступность кадров ------------------------------------------------------

def probe_url(url, timeout=90, retries=3):
    last = None
    for attempt in range(retries):
        try:
            r = _session.head(url, timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                return True
            if r.status_code == 404:
                return False
            last = RuntimeError(f"HTTP {r.status_code}")
        except requests.RequestException as exc:
            last = exc
        time.sleep(1.5 * (attempt + 1))
    return False


def probe_available(row):
    """Метаданные есть, но файл в публичном продукте может отсутствовать
    (дыры архива в разные периоды) — проверяем HEAD'ом с ретраями."""
    if "avail" not in row:
        row["avail"] = probe_url(sci_data_url(row))
    return row["avail"]


def nearest_available(rows, mjd, tol_days=0.2):
    """Ближайшая по mjd СУЩЕСТВУЮЩАЯ экспозиция (иначе None)."""
    cand = sorted(rows, key=lambda r: abs(_row_mjd(r) - mjd))
    for r in cand:
        if abs(_row_mjd(r) - mjd) > tol_days:
            return None
        if probe_available(r):
            return r
    return None


# --- курырование: отдельные команды -------------------------------------------

def row_slim(row):
    """Детерминированное подмножество полей строки IBE для manifest."""
    keys = ["filefracday", "field", "ccdid", "qid", "filtercode", "exptime",
            "seeing", "maglimit", "moonillf", "infobits", "obsdate", "obsjd",
            "expid", "fid", "ipac_pub_date"]
    return {k: row[k] for k in keys if k in row}


def mjd_from_row(row):
    from astropy.time import Time
    return float(Time(float(row["obsjd"]), format="jd").mjd)


def grab3(man, case_key, rows, patch_center, arcsec=None):
    """Скачать 3 вырезки эпох (патч центрируем на patch_center), записать case."""
    center = cutout_center_for(patch_center[0], patch_center[1])
    epochs = []
    for row in rows:
        rec = grab_cutout(row, center, arcsec)
        register_file(man, rec)
        rec = dict(rec)
        rec["row"] = row_slim(row)
        rec["mjd"] = mjd_from_row(row)
        epochs.append(rec)
    epochs.sort(key=lambda e: e["mjd"])
    man["cases"][case_key] = {
        "ra": center[0], "dec": center[1],
        "patch_center": [patch_center[0], patch_center[1]],
        "epochs": epochs,
        "group": {"field": int(rows[0]["field"]), "ccdid": int(rows[0]["ccdid"]),
                  "qid": int(rows[0]["qid"]), "filter": "zr"},
    }
    return man["cases"][case_key]


def utc_iso_from_mjd(mjd):
    import datetime
    t = datetime.datetime(1858, 11, 17) + datetime.timedelta(days=float(mjd))
    return t.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def align_center128(data, header, ra, dec, n=128):
    """Центрированная сетка 128×128 через проверенные rd.target_wcs +
    rd.align_epoch (север вверху, восток слева) — без второй реализации WCS."""
    from tools.realdata import align_epoch, pixel_scale, target_wcs
    twcs = target_wcs(float(ra), float(dec), pixel_scale(header), n=n)
    return align_epoch(data, header, twcs, n=n)


def iso_utc(mjd):
    return utc_iso_from_mjd(mjd)


# --- SN 2023tyk ---------------------------------------------------------------

SN_OID = "ZTF23abhvlji"
SN_TNS = ("SN 2023tyk: AstroNote 2023-265 (Rehemtulla et al.) — первый "
          "транзиент, пройдевший весь путь от обнаружения до спектральной "
          "классификации полностью автоматически; ZTF-имя ZTF23abhvlji")


def cmd_sn():
    man = manifest_load()
    obj = alerce(f"/objects/{SN_OID}")
    ra, dec = float(obj["meanra"]), float(obj["meandec"])
    dets = alerce(f"/objects/{SN_OID}/detections?page_size=50")
    rs = [d for d in dets if d["fid"] == 2]
    rs.sort(key=lambda d: float(d["mjd"]))
    assert len(rs) >= 3, "менее трёх r-детекций"
    rows = ibe_search((ra, dec), size_deg=0.01,
                      where="filtercode='zr' AND exptime=30 AND infobits=0")
    pairs = []
    for d in rs:
        row = nearest_available(rows, float(d["mjd"]), tol_days=0.15)
        if row is not None:
            pairs.append((d, row))
    assert len(pairs) >= 2, f"доступных пар детекция-кадр < 2 ({len(pairs)})"
    disc_mjd = float(pairs[0][0]["mjd"])
    # кадр ДО открытия: та же группа, 1–7 месяцев до первой детекции
    pre = [r for r in rows
           if disc_mjd - 210.0 <= _row_mjd(r) <= disc_mjd - 30.0]
    pre = sorted(pre, key=lambda r: abs(_row_mjd(r) - (disc_mjd - 120.0)))
    pre_row = None
    for r in pre:
        if probe_available(r):
            pre_row = r
            break
    assert pre_row is not None, "нет доступного до-открытия кадра"
    picks = [(None, pre_row), pairs[0], pairs[-1]]
    case = grab3(man, "sn2023tyk", [row for _d, row in picks], (ra, dec))
    phot = []
    for d, row in picks:
        frame_mjd = _row_mjd(row)
        if d is None:
            phot.append({
                "mjd_frame": round(frame_mjd, 4),
                "detection": False,
                "frame_limit_mag": float(row["maglimit"]) if row.get("maglimit")
                else None,
                "note": "Кадр до обнаружения SN; указан общий предел "
                        "чувствительности кадра, не индивидуальный предел для цели.",
            })
            continue
        phot.append({
            "mjd_frame": round(frame_mjd, 4),
            "mjd_detection": float(d["mjd"]),
            "mag_diff": float(d["magpsf"]),
            "err": float(d["sigmapsf"]),
            "isdiffpos": d["isdiffpos"], "distnr": d.get("distnr"),
            "magnr": d.get("magnr"), "rb": d.get("rb"),
            "candid": str(d["candid"]),
            "fid": d["fid"],
        })
    distnr = [float(p["distnr"]) for p in phot if p.get("distnr") is not None]
    case.update({
        "catalog_id": SN_OID,
        "tns": "SN 2023tyk (AstroNote 2023-265)",
        "photometry_alerce": phot,
        "ref_isolation": ("ближайший источник опорного стека дальше "
                          f"{min(distnr):.1f}\" от позиции" if distnr else
                          "источников опорного стека нет в окрестности"),
        "magpsf_note": ("Первая запись содержит только общий предел кадра IRSA. "
                        "Остальные — разностная PSF-фотометрия ALeRCE: оценка "
                        "изменяющейся составляющей, не полного света в апертуре."),
        "story": "sn2023tyk",
    })
    manifest_save(man)
    for e in case["epochs"]:
        print(f"  epoch {iso_utc(e['mjd'])} mjd={e['mjd']:.3f} "
              f"{e['file'].split('/')[-1]} seeing={e['header']['seeing']}")
    print(f"SN case: {ra:.5f} {dec:.5f}; {len(phot)} фотометрических точек ALeRCE")


def _row_mjd(row):
    from astropy.time import Time
    return float(Time(float(row["obsjd"]), format="jd").mjd)


# --- переменные (проверка по ПОЛНОМУ блеску IRSA LC) ---------------------------

def _qc_case(man, key, max_saturated=0.005):
    """Проверка качества скачанных кадров случая: конечность выровненного
    патча 128×128 и отсутствие доминирующих дефектов (насыщение/блики)."""
    from tools.realdata import calibrate, load_fits
    entry = man["cases"][key]
    raw, frames = [], []
    for e in entry["epochs"]:
        data, hdr = load_fits(OBS / e["file"])
        raw.append(data)
        frames.append((calibrate(data, hdr["MAGZP"]), hdr))
    aligned = [align_center128(d, h, entry["ra"], entry["dec"])
               for d, h in frames]
    bad_nan = max(float(np.mean(~np.isfinite(a))) for a in aligned)
    # сырые DN: доля насыщенных/бликовых пикселей в центральной области
    # вырезки (патч центрирован): ±64 px вокруг середины
    sat = []
    for r in raw:
        n = r.shape[0]
        sl = (slice(n // 2 - 64, n // 2 + 64), slice(n // 2 - 64, n // 2 + 64))
        sat.append(float(np.mean(r[sl] > 45000.0)))
    return {"nan": bad_nan, "saturated": sat,
            "ok": bad_nan == 0.0 and max(sat) <= max_saturated}


def cmd_variable(oid=None, amp_min=0.5, amp_max=None, label="variable",
                 case_key=None, ra=None, dec=None, delta=None):
    """Переменная: амплитуда по IRSA LC (полный блеск science-кадров).
    oid может быть списком через запятую — кандидаты перебираются до первого,
    прошедшего проверку кадров (NaN/насыщение в игровом поле)."""
    oids = [o.strip() for o in oid.split(",")] if oid else [None]
    for cand in oids:
        if _try_variable(cand, amp_min, amp_max, label, case_key, ra, dec,
                         delta):
            return
    raise SystemExit("ни один кандидат не прошёл проверку кадров")


def _try_variable(oid, amp_min, amp_max, label, case_key, ra, dec, delta):
    man = manifest_load()
    if oid:
        obj = alerce(f"/objects/{oid}")
        ra, dec = float(obj["meanra"]), float(obj["meandec"])
    rows = lc_clean(irsa_lc(ra, dec, 0.0008))
    # источник мог дрейфовать между квадрантами: берём доминирующую группу
    from collections import Counter
    groups = Counter((r["field"], r["ccdid"], r["qid"]) for r in rows)
    (gf, gc, gq), n_major = groups.most_common(1)[0]
    if n_major < 3:
        print(f"  ! в доминирующей группе {gf}/{gc}/{gq} лишь {n_major} точек — "
              "пропуск")
        return False
    rows = [r for r in rows
            if (r["field"], r["ccdid"], r["qid"]) == (gf, gc, gq)]
    print(f"  группа {gf}/{gc}/{gq}: {len(rows)} точек")
    mags = np.array([r["mag"] for r in rows])
    errs = np.array([r["err"] for r in rows])
    amp = float(mags.max() - mags.min())
    snr_amp = amp / float(np.median(errs))
    print(f"  LC {ra:.5f} {dec:.5f}: n={len(rows)} amp={amp:.3f} "
          f"SNR={snr_amp:.0f} lim={min(r['limitmag'] for r in rows):.1f}")
    if amp < amp_min or (amp_max and amp > amp_max) or snr_amp < 10:
        print("  ! амплитуда/значимость недостаточна — пропуск")
        return False
    if delta is None:
        order = np.argsort(mags)
        i_bright, i_faint = order[0], order[-1]
        t_med = np.median([rows[i_bright]["mjd"], rows[i_faint]["mjd"]])
        i_mid = min(order, key=lambda i: abs(rows[i]["mjd"] - t_med)
                    if i not in (i_bright, i_faint) else 1e9)
        picks = [rows[i_bright], rows[i_mid], rows[i_faint]]
    else:
        # пара с |Δmag|≈delta: ОБЯЗАТЕЛЬНО кадры 1–2 (пара признаков),
        # третья точка — позже обеих, с малым |Δ| к первой
        best = None
        for i in range(len(rows)):
            for j in range(len(rows)):
                if i == j or rows[j]["mjd"] <= rows[i]["mjd"]:
                    continue
                d = abs(abs(mags[i] - mags[j]) - delta)
                if best is None or d < best[0]:
                    best = (d, i, j)
        _d, i1, j1 = best
        low, high = rows[i1], rows[j1]
        if low["mjd"] > high["mjd"]:
            low, high = high, low
        after = [r for r in rows
                 if r["mjd"] > high["mjd"] + 0.02
                 and r["filefracday"] not in (low["filefracday"],
                                              high["filefracday"])]
        if not after:
            print("  ! нет третьей точки позже пары — пропуск")
            return False
        k3 = min(after, key=lambda r: abs(r["mag"] - low["mag"]))
        picks = [low, high, k3]

    def lcrow_to_row(r):
        """Строка IBE-вида из точки IRSA LC (файл однозначно задаётся filefracday)."""
        import datetime
        jd = float(r["mjd"]) + 2400000.5
        dt = (datetime.datetime(1858, 11, 17) +
              datetime.timedelta(days=float(r["mjd"])))
        return {
            "filefracday": r["filefracday"], "field": str(r["field"]),
            "ccdid": str(r["ccdid"]), "qid": str(r["qid"]),
            "filtercode": "zr", "exptime": str(r["exptime"]),
            "obsdate": dt.strftime("%Y-%m-%d %H:%M:%S") + "+00",
            "obsjd": f"{jd:.6f}", "maglimit": str(r["limitmag"]),
            "seeing": "0", "moonillf": "0", "infobits": "0",
            "ipac_pub_date": "",
        }

    used = []
    for p in picks:
        cand_rows = sorted(rows, key=lambda r: abs(r["mag"] - p["mag"]))
        got = None
        for r in cand_rows[:12]:
            row = lcrow_to_row(r)
            if not probe_available(row):
                continue
            got = (row, r)
            break
        if got is None:
            print("  ! нет доступного кадра IBE для LC-точки — пропуск")
            return False
        used.append(got)
    key = case_key or f"variable_{oid or 'pos'}"
    case = grab3(man, key, [row for row, _r in used], (ra, dec))
    qc = _qc_case(man, key)
    if not qc["ok"]:
        log(man, f"{key}: ОТКЛОНЁН по качеству кадров "
                 f"(nan={qc['nan']:.4f}, saturated={qc['saturated']})")
        del man["cases"][key]
        manifest_save(man)
        return False
    case.update({
        "catalog_id": oid,
        "amplitude": round(amp, 3),
        "amplitude_snr": round(snr_amp, 1),
        "label": label,
        "qc": qc,
        "epoch_mags": [{"mjd": round(r["mjd"], 4),
                        "mag": round(r["mag"], 3),
                        "err": round(r["err"], 4),
                        "filefracday": used[i][0]["filefracday"]}
                       for i, (_row, r) in enumerate(used)],
        "lc_points": [{"mjd": round(r["mjd"], 4), "mag": round(r["mag"], 3),
                       "err": round(r["err"], 4), "limitmag": r["limitmag"]}
                      for r in rows[:: max(1, len(rows) // 40)]],
        "mag_note": ("блеск измерен PSF-фотометрией по НАУЧНЫМ кадрам "
                     "(IRSA LC, catflags=0) — это полный блеск источника"),
    })
    manifest_save(man)
    for i, e in enumerate(case["epochs"]):
        m = case["epoch_mags"][i]["mag"]
        print(f"  epoch {iso_utc(e['mjd'])} mjd={e['mjd']:.3f} mag={m:.2f}")
    return True


def cmd_merge_handoff(path):
    """Влить подтверждённые случаи, сохранив все исходные доказательства."""
    handoff = json.loads(Path(path).read_text(encoding="utf-8"))
    man = manifest_load()
    base = Path(path).parent
    verified = {}

    def register(record):
        file = (OBS / record["file"]).resolve()
        relative = str(file.relative_to(OBS))
        if not file.is_file():
            raise SystemExit(f"Отсутствует исходный файл: {relative}")
        if file not in verified:
            verified[file] = sha256_file(file)
        if verified[file] != record["sha256"]:
            raise SystemExit(f"Не совпадает SHA-256: {relative}")
        info = {"url": record["url"], "sha256": verified[file],
                "bytes": file.stat().st_size}
        existing = man["files"].get(relative)
        if existing and existing["sha256"] != info["sha256"]:
            raise SystemExit(f"Конфликт версий исходного файла: {relative}")
        man["files"][relative] = info
        return {**record, **info, "file": relative}

    for key, entry in sorted(handoff["cases"].items()):
        epochs = [register(epoch) for epoch in entry["epochs"]]
        epochs.sort(key=lambda epoch: epoch["mjd"])
        for source in entry.get("mask_evidence", {}).get("sources", []):
            register(source)
        man["cases"][key] = {
            **entry, "ra": float(entry["ra"]), "dec": float(entry["dec"]),
            "patch_center": entry.get("patch_center", [entry["ra"], entry["dec"]]),
            "epochs": epochs, "source_slice": base.name,
        }
        log(man, f"{key}: импортирован из {base.name}; "
                 f"{len(epochs)} эпохи, SHA-256 проверены")
    manifest_save(man)
    print(f"Импортированы случаи: {sorted(handoff['cases'])}")


def cmd_download():
    """Восстановить зафиксированный кэш, не меняя эпохи или контрольные суммы."""
    man = manifest_load()
    for relative, info in sorted(man["files"].items()):
        path = OBS / relative
        if path.is_file():
            if sha256_file(path) != info["sha256"]:
                raise SystemExit(f"Изменён исходный файл: {relative}")
            continue
        url = info["url"]
        if not url.startswith(("https://", "http://")):
            raise SystemExit(f"Сначала подготовьте локальные данные: {relative} "
                             "(tools/prepare_demo.py и tools/prepare_curated.py)")
        payload = _get(url)
        if path.suffix == ".gz" and not payload.startswith(b"\x1f\x8b"):
            payload = gzip.compress(payload, compresslevel=6, mtime=0)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".download")
        temporary.write_bytes(payload)
        if sha256_file(temporary) != info["sha256"]:
            temporary.unlink()
            raise SystemExit(f"Архив вернул другую версию файла: {relative}; "
                             "ожидаемые данные не подменены")
        temporary.replace(path)
        print(f"Загружен и проверен: {relative}")
    print(f"Кэш проверен. Файлов: {len(man['files'])}")


def cmd_verify(quiet=False):
    man = manifest_load()
    bad = []
    for rel, info in sorted(man["files"].items()):
        p = OBS / rel
        if not p.exists():
            bad.append((rel, "отсутствует"));  continue
        if sha256_file(p) != info["sha256"]:
            bad.append((rel, "sha256"))
    if not quiet:
        print(f"файлов {len(man['files'])}, плохих {len(bad)}")
        for rel, why in bad[:10]:
            print("  !", rel, why)
    return bad


def main():
    ap = argparse.ArgumentParser(description="Импорт и курирование реальных данных")
    ap.add_argument("command", choices=[
        "probe", "sn", "variable", "download", "merge-handoff", "verify"])
    ap.add_argument("--oid")
    ap.add_argument("--amp-min", type=float, default=0.5)
    ap.add_argument("--amp-max", type=float)
    ap.add_argument("--delta", type=float,
                    help="целая |Δmag| пары эпох (weak/weak_mid)")
    ap.add_argument("--label", default="variable")
    ap.add_argument("--case-key")
    ap.add_argument("--ra", type=float)
    ap.add_argument("--dec", type=float)
    ap.add_argument("--path")
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT / "tools"))
    if args.command == "probe":
        rows = ibe_search((103.48, -0.9569), where="filtercode='zr' AND exptime=30")
        print(f"IBE ok: {len(rows)} строк; LC ok: {len(irsa_lc(103.48, -0.9569))}")
    elif args.command == "sn":
        cmd_sn()
    elif args.command == "variable":
        cmd_variable(args.oid, args.amp_min, args.amp_max, args.label,
                     args.case_key, args.ra, args.dec, args.delta)
    elif args.command == "merge-handoff":
        cmd_merge_handoff(args.path)
    elif args.command == "download":
        cmd_download()
    elif args.command == "verify":
        if cmd_verify():
            raise SystemExit(1)


if __name__ == "__main__":
    main()

