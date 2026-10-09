#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prepare_sky.py — сборка офлайн-атласа неба app/sky-data.js.

Реальные источники (кэш: assets/sky/src, сборка воспроизводима офлайн):
  1. NASA SVS 4851 «Deep Star Maps 2020», starmap_2020_{8k,4k}.exr —
     каталожная визуализация Hipparcos-2, Tycho-2, Gaia DR2 (НЕ фотография), plate carrée,
     ICRF/J2000, RA=0h в центре, RA растёт влево. EXR: ZIP-сжатие, half-float
     RGB — декодируется чистым Python (numpy+zlib), внешних зависимостей нет.
     Тонмаппинг: экспозиция → extended Reinhard → sRGB → насыщенность.
  2. HYG v4.1 (astronexus, CC BY-SA 4.0) — звёзды-оверлей (ra/dec/mag/proper).
  3. Stellarium «western» (CC BY-SA 4.0 + Free Art License): линии созвездий
     и исходные названия; po/stellarium-skycultures/ru.po — русские переводы
     (GPL-2.0+, лицензия пакета Stellarium).
  4. Самопроверка регистрации: пики яркости текстуры обязаны совпасть с
     каталожными позициями ярких звёзд (и НЕ совпадать при зеркалировании RA).

Запуск: .venv/bin/python tools/prepare_sky.py [--quality 82] [--max-mb 3.2]
Зависимости: numpy, Pillow (уже есть в .venv; requirements.txt не менялся).
"""
import argparse
import base64
import csv
import hashlib
import io
import json
import math
import os
import re
import struct
import sys
import urllib.request
import zlib

import numpy as np
from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets", "sky", "src")
OUT_JS = os.path.join(ROOT, "app", "sky-data.js")
OUT_MANIFEST = os.path.join(ROOT, "assets", "sky", "manifest.json")

SVS = "https://svs.gsfc.nasa.gov/vis/a000000/a004800/a004851/"
SOURCES = {
    "starmap_2020_4k.exr": (SVS + "starmap_2020_4k.exr", 35997085),
    "starmap_2020_8k.exr": (SVS + "starmap_2020_8k.exr", 130530278),
    "starmap_2020_4k_print.jpg": (SVS + "starmap_2020_4k_print.jpg", 42786),
    "constellation_figures_16k.tif": (SVS + "constellation_figures_16k.tif", 1741460),
    "celestial_grid_16k.tif": (SVS + "celestial_grid_16k.tif", 2762556),
    "hygdata_v41.csv": (
        "https://raw.githubusercontent.com/astronexus/hyg-database/main/hyg/CURRENT/hygdata_v41.csv",
        33932548),
    "constellationship.fab": (
        "https://raw.githubusercontent.com/Stellarium/stellarium/release/skycultures/western/constellationship.fab",
        8851),
    "star_names.fab": (
        "https://raw.githubusercontent.com/Stellarium/stellarium/release/skycultures/western/star_names.fab",
        32469),
    "constellation_names.eng.fab": (
        "https://raw.githubusercontent.com/Stellarium/stellarium/release/skycultures/western/constellation_names.eng.fab",
        2491),
    "stellarium_ru.po": (
        "https://raw.githubusercontent.com/Stellarium/stellarium/release/po/stellarium/ru.po",
        1202949),
    "skycultures_ru.po": (
        "https://raw.githubusercontent.com/Stellarium/stellarium/release/po/stellarium-skycultures/ru.po",
        2126244),
    "info.ini": (
        "https://raw.githubusercontent.com/Stellarium/stellarium/release/skycultures/western/info.ini",
        166),
}

LUM = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def log(msg):
    print("[prepare_sky] " + msg, flush=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_sources():
    os.makedirs(SRC, exist_ok=True)
    for name, (url, size) in SOURCES.items():
        path = os.path.join(SRC, name)
        if os.path.exists(path) and os.path.getsize(path) == size:
            continue
        log("download %s" % name)
        req = urllib.request.Request(url, headers={"User-Agent": "atlas-prepare/1.0"})
        with urllib.request.urlopen(req, timeout=180) as r, open(path, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        if os.path.getsize(path) != size:
            raise RuntimeError("size mismatch for %s" % name)


# ---------------------------------------------------------------------------
# 1. Чистый Python-декодер EXR (scanline, ZIP-сжатие) -> поток блоков float32 RGB

def exr_header(path):
    """Возвращает (w, h, compression, channels, offset_table_pos)."""
    with open(path, "rb") as f:
        if f.read(8) != b"\x76\x2f\x31\x01\x02\x00\x00\x00":
            raise RuntimeError("%s: не одночастный EXR v2" % os.path.basename(path))
        attrs = {}

        def cstr():
            bs = bytearray()
            while True:
                c = f.read(1)
                if c == b"\x00":
                    return bs.decode("utf-8")
                bs += c

        while True:
            if f.read(1) == b"\x00":
                break  # конец заголовка
            f.seek(-1, 1)
            name = cstr()
            typ = cstr()
            (size,) = struct.unpack("<i", f.read(4))
            attrs[name] = (typ, f.read(size))
        table_pos = f.tell()
    chans = []
    raw = attrs["channels"][1]
    pos = 0
    while pos < len(raw) - 1:
        end = raw.index(b"\x00", pos)
        cname = raw[pos:end].decode()
        (ptype,) = struct.unpack_from("<i", raw, end + 1)
        (xs, ys) = struct.unpack_from("<ii", raw, end + 9)
        chans.append((cname, ptype, xs, ys))
        pos = end + 17
    chans.sort()
    (xmin, ymin, xmax, ymax) = struct.unpack("<iiii", attrs["dataWindow"][1])
    compression = attrs["compression"][1][0]
    if compression != 3:
        raise RuntimeError("ожидалось ZIP-сжатие (3), получено %d" % compression)
    for (cname, ptype, xs, ys) in chans:
        if ptype != 1 or xs != 1 or ys != 1:
            raise RuntimeError("канал %s: не half с шагом 1" % cname)
    lines_per_block = 16  # ZIP
    n_blocks = (ymax - ymin + lines_per_block) // lines_per_block
    return (xmax - xmin + 1, ymax - ymin + 1, chans, table_pos, n_blocks, lines_per_block)


def exr_blocks(path, w, h, chans, table_pos, n_blocks, lines_per_block):
    """yield (y0, float32 RGB (lines, w, 3)) — линейные значения.

    Раскладка блока в этих файлах NASA (проверено по совпадению звёзд
    с каталогом и по корреляции 0.93 с NASA print jpg):
      1) zlib-инфляция всего блока;
      2) предиктор OpenEXR ZIP с шагом 1 байт (seed = s[0]);
      3) чередование байтов (чётные/нечётные) на весь блок;
      4) данные ПО СТРОКАМ: каждая строка = [B: w half][G: w half][R: w half]
         (не попиксельно и не плоскостями на весь блок)."""
    order = {c: i for i, (c, _, _, _) in enumerate(chans)}  # B,G,R
    with open(path, "rb") as f:
        f.seek(table_pos)
        offs = struct.unpack("<%dQ" % n_blocks, f.read(8 * n_blocks))
        bpp = len(chans) * 2
        for y0 in range(0, h, lines_per_block):
            lines = min(lines_per_block, h - y0)
            f.seek(offs[y0 // lines_per_block])
            (y, size) = struct.unpack("<ii", f.read(8))
            if y != y0:
                raise RuntimeError("EXR: неожиданный y блока")
            n = w * lines * bpp
            raw = zlib.decompress(f.read(size))
            if len(raw) != n:
                raise RuntimeError("EXR: размер блока %d != %d" % (len(raw), n))
            buf = np.frombuffer(raw, dtype=np.uint8)
            raw2 = ((np.cumsum(buf.astype(np.int32) - 128) + 128) & 0xFF).astype(np.uint8)
            out = np.empty(n, dtype=np.uint8)
            half = (n + 1) // 2
            out[0::2] = raw2[:half]
            out[1::2] = raw2[half:half + n // 2]
            planes = out.view("<f2").reshape(lines, len(chans), w).astype(np.float32)
            rgb = planes[:, [order["R"], order["G"], order["B"]], :]
            rgb = np.nan_to_num(rgb, nan=0.0, posinf=1e6, neginf=0.0)
            yield y0, np.ascontiguousarray(rgb.transpose(0, 2, 1))


# ---------------------------------------------------------------------------
# 2. Тонмаппинг

def srgb(x):
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def tonemap(img, p):
    img = np.maximum(img - p["floor"], 0.0, dtype=np.float32) * p["exposure"]
    lum = img @ LUM
    img *= ((1.0 + (lum / (p["white"] * p["white"]))) / (1.0 + lum))[..., None]  # Reinhard ext.
    img = srgb(np.clip(img, 0.0, None))
    lum2 = (img @ LUM)[..., None]
    img = lum2 + (img - lum2) * p["saturation"]  # насыщенность
    np.clip(img, 0.0, 1.0, out=img)
    return (img * 255.0).astype(np.uint8)


def build_texture(exr, params, progress_every=64):
    cache_npy = os.path.join(SRC, "tonemap_cache.npy")
    cache_js = cache_npy + ".json"
    sig = {k: params[k] for k in sorted(params)}
    sig["src"] = os.path.basename(exr)
    sig["decoder"] = 3  # де-интерливинг + предиктор шага 1 + построчные каналы
    if os.path.exists(cache_npy) and os.path.exists(cache_js):
        with open(cache_js, encoding="utf-8") as f:
            if json.load(f) == sig:
                log("тонмаппинг из кэша")
                return (np.load(cache_npy),
                        np.load(cache_npy.replace(".npy", "_lum.npy")))
    w, h, chans, table_pos, n_blocks, lpb = exr_header(exr)
    log("EXR %dx%d, блоков %d" % (w, h, n_blocks))
    out = np.empty((h, w, 3), dtype=np.uint8)
    pool = 8
    ph, pw = h // pool, w // pool
    lum_pool = np.zeros((ph, pw), dtype=np.float32)  # линейная яркость (не сатурируется)
    for i, (y0, rgb) in enumerate(exr_blocks(exr, w, h, chans, table_pos, n_blocks, lpb)):
        out[y0:y0 + rgb.shape[0]] = tonemap(rgb, params)
        blk = (rgb @ LUM).reshape(-1, pool, pw, pool).max(axis=(1, 3))
        lum_pool[y0 // pool:(y0 + rgb.shape[0]) // pool] = np.maximum(
            lum_pool[y0 // pool:(y0 + rgb.shape[0]) // pool], blk)
        if (i + 1) % progress_every == 0:
            log("  %d/%d блоков" % (i + 1, n_blocks))
    np.save(cache_npy, out)
    np.save(cache_npy.replace(".npy", "_lum.npy"), lum_pool)
    with open(cache_js, "w", encoding="utf-8") as f:
        json.dump(sig, f)
    return out, lum_pool


def encode_texture(arr, quality, max_mb):
    """Основной формат — JPEG (4:4:4); WebP — если JPEG вышел крупнее порога.
    Перед кодированием мягкая чистка одиночного зерна: median 3×3 сохраняет
    звёзды (они крупнее), убирает однопиксельный мусор; лёгкий гаусс 0.45.
    Оба варианта кодируются в память, на диск пишется только победитель."""
    img = Image.fromarray(arr, "RGB")
    img = img.filter(ImageFilter.MedianFilter(3)).filter(
        ImageFilter.GaussianBlur(radius=0.45))
    jb = io.BytesIO()
    img.save(jb, "JPEG", quality=quality, subsampling=0, optimize=True)
    fmt, blob, ext = "jpeg", jb.getvalue(), "jpg"
    if len(blob) > max_mb * (1 << 20):
        wb = io.BytesIO()
        img.save(wb, "WEBP", quality=quality, method=6)
        if len(wb.getvalue()) < len(blob):
            fmt, blob, ext = "webp", wb.getvalue(), "webp"
    path = os.path.join(SRC, "texture_full." + ext)
    with open(path, "wb") as f:
        f.write(blob)
    for stale in ("texture_full.jpg", "texture_full.webp"):
        sp = os.path.join(SRC, stale)
        if os.path.exists(sp) and os.path.basename(path) != stale:
            os.remove(sp)
    return fmt, path, len(blob)


# ---------------------------------------------------------------------------
# 3. Каталоги: HYG v4.1 + Stellarium

def parse_po(path):
    """msgid -> msgstr (без msgctxt) + отдельные словари по msgctxt."""
    plain, ctx = {}, {}
    with open(path, encoding="utf-8") as f:
        cur_ctx, msgid = None, None
        for line in f:
            line = line.strip()
            m = re.match(r'msgctxt "(.*)"$', line)
            if m:
                cur_ctx = m.group(1)
                continue
            m = re.match(r'msgid "(.*)"$', line)
            if m:
                msgid = m.group(1)
                continue
            m = re.match(r'msgstr "(.*)"$', line)
            if m and msgid is not None:
                if cur_ctx is None:
                    plain[msgid] = m.group(1)
                else:
                    ctx.setdefault(cur_ctx, {})[msgid] = m.group(1)
                cur_ctx, msgid = None, None
    return plain, ctx


def load_hyg(path):
    """{hip: (ra, dec, mag, proper)} + {(ra,dec,mag) без hip не нужен}."""
    stars = {}
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                hip = int(row["hip"]) if row["hip"] else 0
                ra = float(row["ra"]) * 15.0  # HYG v4.x: ra в ЧАСАХ -> градусы
                dec = float(row["dec"])
                mag = float(row["mag"])
            except (ValueError, TypeError, KeyError):
                continue
            if hip:
                stars[hip] = (ra, dec, mag, row["proper"] or "")
    if abs(stars[32349][0] - 101.287) > 0.1 or abs(stars[32349][1] + 16.716) > 0.1:
        raise RuntimeError("HYG: Сириус не на ожидаемых координатах — формат v4.1 изменился")
    return stars


def load_constellation_names(path):
    ab = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r'(\w+)\s+"([^"]+)"', line)
            if m:
                ab[m.group(1)] = m.group(2)
    return ab


def load_constellationship(path):
    """[(abbr, [hip-последовательность])] — пары соседей = звенья линий."""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            abbr, n = parts[0], int(parts[1])
            hips = [int(x) for x in parts[2:2 + 2 * n]]
            out.append((abbr, hips))
    return out


def merge_chains(edges):
    """Слить рёбра в ломаные: [[a,b],[b,c],...] -> [[a,b,c],...]."""
    adj = {}
    for a, b in edges:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    used = set()
    chains = []
    for a, b in edges:
        if (a, b) in used:
            continue
        chain = [a, b]
        used.add((a, b))
        used.add((b, a))
        # растим в обе стороны
        for direction in (1, -1):
            while True:
                tip = chain[-1] if direction == 1 else chain[0]
                nxt = None
                for cand in adj.get(tip, ()):
                    key = (tip, cand) if direction == 1 else (cand, tip)
                    if key not in used and cand != (chain[-2] if len(chain) > 1 else None):
                        nxt = cand
                        used.add((tip, cand))
                        used.add((cand, tip))
                        break
                if nxt is None:
                    break
                if direction == 1:
                    chain.append(nxt)
                else:
                    chain.insert(0, nxt)
        chains.append(chain)
    return chains


def sph_mean(points):
    """Среднее по единичной сфере (учитывает переход через RA=0)."""
    v = np.zeros(3)
    for ra, dec in points:
        a = np.radians(ra)
        d = np.radians(dec)
        v += [np.cos(d) * np.cos(a), np.cos(d) * np.sin(a), np.sin(d)]
    v /= max(len(points), 1)
    n = np.linalg.norm(v)
    if n < 1e-9:
        return points[0]
    return (math.degrees(math.atan2(v[1], v[0])) % 360.0,
            math.degrees(math.asin(v[2] / n)))


# 3a. Русские названия: правки поверх перевода skycultures_ru.po.
# IAU (WGSN, каталог CSN) утверждает имена в латинской письменности и НЕ
# стандартизирует русские транслитерации; русские написания — закрепившееся
# употребление. Поэтому правим ТОЛЬКО случаи с опорой на авторитетный источник:
# русскоязычные астрономические учреждения (Астронет/ГАИШ МГУ) либо каталог
# имён МАС для идентификации звезды. Расхождения, где есть лишь варианты
# написания без более сильного источника, НЕ правятся: сохраняется форма
# перевода Stellarium, вариант задокументирован в NAME_VARIANTS_KEPT.
# Ключ — msgid в po (он же поле proper в HYG); значение — (написание, тип,
# источник). Геометрия и каталожные позиции не затрагиваются — только name.
NAME_FIXES_RU = {
    "Rigil Kentaurus": ("Ригель Кентаурус", "выбор русского написания",
                        "Астронет, «Альфа Центавра»: https://www.astronet.ru/db/msg/eid/apod/ap030323"),
    "Elnath": ("Эльнат", "выбор русского написания",
               "Московский планетарий, прогноз на июль 2026: https://planetarium-moscow.ru/blog/news/astronomicheskiy-prognoz-na-iyul-2026-goda-43"),
    # Орфография имени собственного по Астронету (В. Г. Сурдин/ГАИШ МГУ)
    "Canes Venatici": ("Гончие Псы", "орфография имени собственного",
                       "Астронет, «Созвездие Гончие Псы»: astronet.ru/db/msg/1166003 (в po «Гончие псы»)"),
    "Corona Australis": ("Южная Корона", "орфография имени собственного",
                         "Астронет, «Созвездие Южная Корона»: astronet.ru/db/msg/1165706 (в po «Южная корона»)"),
}
# Остальные варианты оставлены как в Stellarium: другая транслитерация сама
# по себе не доказывает ошибку или неверную идентификацию звезды.
NAME_VARIANTS_KEPT = {
    "Gienah": "в po «Гиенах»; вариант «Джиенах». Идентичность задаётся каталогом: γ Ворона, HIP 59803; русское написание её не меняет",
    "Miaplacidus": "в po «Миаплацид»; вариант ru.wikipedia «Миаплацидус»",
    "Peacock": "в po «Павлин» (имя звезды — от созвездия Pavo); вариант ru.wikipedia «Пикок»",
    "Hamal": "в po «Гамаль»; вариант ru.wikipedia «Хамаль»",
    "Rasalhague": "в po «Расальхаг»; вариант ru.wikipedia «Рас Альхаге»",
    "Rasalgethi": "в po «Расальгети»; вариант ru.wikipedia «Рас Альгети»",
    "Saiph": "в po «Сайф»; вариант ru.wikipedia «Саиф»",
    "Suhail": "в po «Сухаиль»; вариант ru.wikipedia «Сухайль»",
    "Alsephina": "в po «Альзефина»; вариант ru.wikipedia «Альсефина»",
    "Mahasim": "в po «Махазим»; вариант ru.wikipedia «Махасим»",
    "Unukalhai": "в po «Унукалхаи»; варианты ru.wikipedia «Унук аль Хай», «Унук Альхайя»",
    "Cebalrai": "в po «Кебалраи»; варианты ru.wikipedia «Цебальрай», «Цельбальрай»",
    "Dschubba": "в po «Джубба»; вариант ru.wikipedia «Дшубба» (имя МАС Dschubba)",
    "Tejat": "в po «Тейят»; вариант ru.wikipedia «Тейат» (имя МАС Tejat)",
    "Athebyne": "в po «Афебын»; вариант ru.wikipedia «Альдибаин» (имя МАС Athebyne)",
    "Tianguan": "в po «Тиангвен»; пиньинь tiān guān, система Палладия даёт «Тяньгуань» (имя МАС Tianguan)",
    "Canis Minor": "в po «Малый Пес»; Астронет также «Малый Пес» (astronet.ru/db/msg/1165869); вариант ru.wikipedia «Малый Пёс»",
}


def ru_name(msgid, fallback):
    """Русское название с документированной правкой поверх po-перевода."""
    fix = NAME_FIXES_RU.get(msgid)
    return fix[0] if fix else fallback


def build_overlays(hyg_path, rel_path, names_path, po_skycultures_path, stars_max_mag):
    hyg = load_hyg(hyg_path)
    plain, _ = parse_po(po_skycultures_path)
    abbr2en = load_constellation_names(names_path)

    # звёзды-оверлей
    stars = []
    for hip, (ra, dec, mag, proper) in hyg.items():
        if mag > stars_max_mag:
            continue
        s = {"ra": round(ra, 2), "dec": round(dec, 2), "mag": round(mag, 1)}
        if mag <= 3.0:
            ru = ru_name(proper, plain.get(proper)) if proper else None
            if ru:
                s["name"] = ru
        stars.append(s)
    stars.sort(key=lambda s: (s["mag"], s["ra"]))

    # созвездия
    constellations = []
    missing = 0
    for abbr, hips in load_constellationship(rel_path):
        pts = []
        for h in hips:
            if h in hyg:
                pts.append(hyg[h][:2])
            else:
                missing += 1
        edges = [(hips[i], hips[i + 1]) for i in range(0, len(hips) - 1, 2)
                 if hips[i] in hyg and hips[i + 1] in hyg]
        if not edges:
            continue
        lines = []
        for chain in merge_chains(edges):
            if len(chain) >= 2 and all(c in hyg for c in chain):
                lines.append([[round(hyg[c][0], 2), round(hyg[c][1], 2)] for c in chain])
        if not lines:
            continue
        vertices = [tuple(p) for ln in lines for p in ln]
        (ra, dec) = sph_mean(vertices)
        en = abbr2en.get(abbr, abbr)
        constellations.append({
            "name": ru_name(en, plain.get(en, en)),
            "lines": lines,
            "ra": round(ra, 2),
            "dec": round(dec, 2),
        })
    log("звёзд: %d, созвездий: %d, недостающих HIP-звеньев: %d"
        % (len(stars), len(constellations), missing))
    return stars, constellations


# ---------------------------------------------------------------------------
# 4. Самопроверка регистрации (реальные звёзды против текстуры)

CHECK_STARS = [
    ("Сириус", 101.287, -16.716), ("Вега", 279.234, 38.784),
    ("Арктур", 213.915, 19.182), ("Капелла", 79.172, 45.998),
    ("Ригель", 78.634, -8.202), ("Процион", 114.826, 5.225),
    ("Бетельгейзе", 88.793, 7.407), ("Ахернар", 24.429, -57.237),
    ("Альтаир", 297.696, 8.868), ("Антарес", 247.352, -26.432),
    ("Альдебаран", 68.980, 16.509), ("Спика", 201.298, -11.161),
    ("Фомальгаут", 344.413, -29.622), ("Денеб", 310.358, 45.280),
    ("Полярная", 37.955, 89.264), ("Мимоза", 191.930, -59.689),
]


def ra_to_x(ra, w):
    return (((180.0 - ra) % 360.0) + 360.0) % 360.0 / 360.0 * w


def check_orientation(arr, lum8, w, h):
    """16 ярких звёзд из HYG обязаны найтись компактным источником в
    радиусе 0.9° от каталожной позиции (медиана <=0.45°). Это надёжно
    отсекает инверсию RA, перепутанный полюс и сдвиг всей сетки:
    при любой из этих ошибок совпадений почти не будет. Порог разброса
    подтверждён на NASA print jpg — там он такой же или больше; в
    линейной яркости этой визуализации пик спрайта не монотонен по
    звёздной величине, поэтому «яркостных» проверок не применяем."""
    win = int(1.1 / 360 * w)
    ok, dists, fails = 0, [], []
    for name, ra, dec in CHECK_STARS:
        px = ra_to_x(ra, w)
        py = (90.0 - dec) / 180.0 * h
        x0 = max(0, int(px) - win)
        x1 = min(w, int(px) + win)
        y0 = max(0, int(py) - win)
        y1 = min(h, int(py) + win)
        sub = arr[y0:y1, x0:x1] @ LUM
        (my, mx) = np.unravel_index(np.argmax(sub), sub.shape)
        m = sub >= 0.6 * sub[my, mx]  # ядро звезды: плато насыщения
        ys, xs = np.nonzero(m)
        ws = sub[ys, xs]
        fx = x0 + float((xs * ws).sum()) / ws.sum()
        fy = y0 + float((ys * ws).sum()) / ws.sum()
        good = math.hypot(fx - px, fy - py)
        ok += 0 if good > (0.9 / 360.0 * w) else 1
        dists.append(good)
        if good > (0.9 / 360.0 * w):
            fails.append("%s: %.2f°" % (name, good / w * 360))
    dists.sort()
    med = dists[len(dists) // 2] / w * 360
    log("регистрация: %d/%d в радиусе 0.9° (медиана %.2f°)"
        % (ok, len(CHECK_STARS), med))
    for f in fails:
        log("  FAIL " + f)
    return ok == len(CHECK_STARS) and med <= 0.45


# ---------------------------------------------------------------------------
# 5. Сборка sky-data.js и манифеста

def jdump(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quality", type=int, default=76)
    ap.add_argument("--max-mb", type=float, default=3.2,
                    help="порог для переключения JPEG->WebP")
    ap.add_argument("--exposure", type=float, default=7.0)
    ap.add_argument("--white", type=float, default=12.0)
    ap.add_argument("--floor", type=float, default=0.003)
    ap.add_argument("--saturation", type=float, default=1.12)
    ap.add_argument("--stars-max-mag", type=float, default=5.2)
    args = ap.parse_args()

    ensure_sources()

    exr = os.path.join(SRC, "starmap_2020_8k.exr")
    if not os.path.exists(exr):
        exr = os.path.join(SRC, "starmap_2020_4k.exr")
        log("8k отсутствует — использую 4k")
    params = {"exposure": args.exposure, "white": args.white, "floor": args.floor,
              "saturation": args.saturation}
    log("тонмаппинг %s" % os.path.basename(exr))
    arr, lum8 = build_texture(exr, params)
    h, w = arr.shape[:2]
    # быстрый предпросмотр для eyeball-сравнения с NASA print jpg
    Image.fromarray(arr, "RGB").resize((2048, 1024), Image.LANCZOS).save(
        os.path.join(SRC, "preview_small.jpg"), quality=90)
    if not check_orientation(arr, lum8, w, h):
        print("ОРИЕНТАЦИЯ НЕ ПОДТВЕРЖДЕНА — sky-data.js не записан", file=sys.stderr)
        return 2

    fmt, tex_path, tex_size = encode_texture(arr, args.quality, args.max_mb)
    log("текстура: %s %dx%d, %.2f МБ" % (fmt, w, h, tex_size / (1 << 20)))
    with open(tex_path, "rb") as f:
        datauri = "data:image/%s;base64,%s" % (
            "jpeg" if fmt == "jpeg" else "webp", base64.b64encode(f.read()).decode("ascii"))

    stars, constellations = build_overlays(
        os.path.join(SRC, "hygdata_v41.csv"),
        os.path.join(SRC, "constellationship.fab"),
        os.path.join(SRC, "constellation_names.eng.fab"),
        os.path.join(SRC, "skycultures_ru.po"), args.stars_max_mag)

    src = {
        "label": "NASA SVS Deep Star Maps 2020 · Hipparcos-2, Tycho-2, Gaia DR2 (каталожная визуализация, не фотография)",
        "url": "https://svs.gsfc.nasa.gov/4851",
        "credit": "Текстура: NASA Scientific Visualization Studio / Ernie Wright, "
                  "«Deep Star Maps 2020»; звёзды: HYG v4.1, David Nash / Astronexus "
                  "(CC BY-SA 4.0); созвездия: Stellarium «western» "
                  "(CC BY-SA 4.0 + Free Art License); русские переводы: команда Stellarium (GPL-2.0+); "
                  "выбор русских написаний — по Астронету и Московскому планетарию; "
                  "перечень: assets/sky/manifest.json, разделы name_fixes "
                  "и name_variants_kept",
        "note": "Карта звёздного неба, собранная из каталогов спутниковых измерений "
                "(Hipparcos-2, Tycho-2, Gaia DR2): это данные, а не снимок. Проекция plate carrée "
                "(равнопромежуточная), эпоха ICRF/J2000: север — вверху, юг — внизу; прямое "
                "восхождение RA (небесная долгота) 0 ч в центре, RA растёт влево: "
                "x=((180°−RA) mod 360°)/360°·W, y=(90°−δ)/180°·H. Названия — общепринятые русские; "
                "МАС утверждает имена звёзд в латинской письменности, русские написания — "
                "закрепившееся употребление.",
    }
    sky = {"texture": datauri, "width": w, "height": h, "stars": stars,
           "constellations": constellations, "source": src}

    head = ("/* sky-data.js — СОБРАН ФАЙЛ tools/prepare_sky.py, НЕ РЕДАКТИРОВАТЬ ВРУЧНУЮ.\n"
            "   Источники и лицензии: assets/sky/manifest.json. Офлайн: текстура — data URI,\n"
            "   сетевых запросов нет. */\n")
    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write(head)
        f.write("window.SKY_DATA = ")
        f.write(jdump(sky))
        f.write(";\n")
    js_size = os.path.getsize(OUT_JS)
    log("app/sky-data.js: %.2f МБ" % (js_size / (1 << 20)))

    manifest = {
        "generated_by": "tools/prepare_sky.py",
        "sources": [], "output": {}, "parameters": vars(args),
        "name_policy": "Русские названия: базовый перевод — ru.po Stellarium (GPL-2.0+). "
                       "IAU (WGSN/CSN) утверждает имена в латинской письменности и не "
                       "стандартизирует русские транслитерации. name_fixes — только правки "
                       "с опорой на русскоязычные астрономические источники "
                       "(Астронет и Московский планетарий). Выбор русского написания "
                       "не объявляет остальные варианты ошибками. "
                       "Различия, где есть лишь варианты написания, НЕ правились: формы "
                       "ru.po сохранены, варианты перечислены в name_variants_kept. "
                       "Геометрия и каталожные позиции не затронуты.",
    }
    manifest["name_fixes"] = {
        msgid: {"ru": ru, "kind": kind, "source": source}
        for msgid, (ru, kind, source) in NAME_FIXES_RU.items()}
    manifest["name_variants_kept"] = dict(NAME_VARIANTS_KEPT)
    for name, (url, size) in SOURCES.items():
        path = os.path.join(SRC, name)
        if not os.path.exists(path):
            continue
        manifest["sources"].append({
            "file": "assets/sky/src/" + name, "url": url,
            "bytes": os.path.getsize(path), "sha256": sha256(path)})
    licenses = {
        "starmap_2020_4k.exr": "NASA SVS, согласно NASA Media Usage Guidelines: "
                               "контент NASA не защищён авторским правом, указание источника приветствуется",
        "starmap_2020_8k.exr": "NASA SVS, согласно NASA Media Usage Guidelines: "
                               "контент NASA не защищён авторским правом, указание источника приветствуется",
        "starmap_2020_4k_print.jpg": "NASA SVS, как выше (референс тона, в сборку не входит)",
        "constellation_figures_16k.tif": "NASA SVS, как выше",
        "celestial_grid_16k.tif": "NASA SVS, как выше",
        "hygdata_v41.csv": "HYG v4.1, CC BY-SA 4.0 (astronexus)",
        "constellationship.fab": "Stellarium western (CC BY-SA 4.0 + Free Art License, info.ini)",
        "star_names.fab": "Stellarium western (CC BY-SA 4.0 + Free Art License, info.ini)",
        "constellation_names.eng.fab": "Stellarium western (CC BY-SA 4.0 + Free Art License, info.ini)",
        "info.ini": "Исходное заявление лицензии Stellarium western",
        "stellarium_ru.po": "Stellarium translations (GPL-2.0+)",
        "skycultures_ru.po": "Stellarium translations (GPL-2.0+)",
        "texture_full.jpg": "производное от starmap_2020_8k.exr (NASA SVS)",
        "texture_full.webp": "производное от starmap_2020_8k.exr (NASA SVS)",
    }
    for s in manifest["sources"]:
        s["license"] = licenses.get(os.path.basename(s["file"]), "")
    manifest["output"] = {
        "app/sky-data.js": {"bytes": js_size, "texture_format": fmt,
                            "texture_bytes": tex_size, "width": w, "height": h,
                            "stars": len(stars), "constellations": len(constellations)}}
    with open(OUT_MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    log("манифест: %s" % OUT_MANIFEST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
