#!/usr/bin/env python3
"""200 игровых и 300 обучающих участков из раздельных квадрантов ZTF.

Никаких нарисованных источников и подмен пикселей. FITS загружаются из IRSA;
координаты каждого участка вычисляются по WCS исходного наблюдения.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from urllib.request import urlopen

import numpy as np
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import realdata as rd
OUT = ROOT / "assets/observations"
RAW = OUT / "demo-quadrants"
EXPOSURES = ("20231007507292", "20231029496447", "20231110430868")
SIZE = rd.PATCH
SCALE = 1.01286  # arcsec/pixel; native ZTF scale, not a change of angular extent
EXCLUDE = (143.79799404615386, 83.9734582153846)  # physical SN 2023tyk position


def source_url(exposure, quadrant):
    name = f"ztf_{exposure}_000872_zr_c10_o_q{quadrant}_sciimg.fits"
    return (f"https://irsa.ipac.caltech.edu/ibe/data/ztf/products/sci/"
            f"{exposure[:4]}/{exposure[4:8]}/{exposure[8:]}/{name}")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_frames(quadrant):
    frames, epochs = [], []
    for exposure in EXPOSURES:
        url = source_url(exposure, quadrant)
        path = RAW / url.rsplit("/", 1)[1]
        if not path.exists():
            temporary = path.with_suffix(".download")
            with urlopen(url, timeout=180) as response, temporary.open("wb") as out:
                while block := response.read(1024 * 1024):
                    out.write(block)
            temporary.replace(path)
        with fits.open(path, memmap=False) as hdus:
            data = np.asarray(hdus[0].data, dtype=np.float32)
            header = hdus[0].header.copy()
        if data.ndim != 2 or int(header["INFOBITS"]) != 0:
            raise ValueError(f"Непригодный исходный FITS: {path}")
        data *= np.float32(10 ** (-0.4 * (float(header["MAGZP"]) - 25)))
        frames.append((data, WCS(header)))
        mjd = float(header["OBSJD"]) - 2400000.5
        epochs.append({
            "file": str(path.relative_to(OUT)), "url": url,
            "sha256": sha256(path), "mjd": mjd,
            "date": Time(mjd, format="mjd", scale="utc").isot + "Z",
            "row": {"field": 872, "ccdid": 10, "qid": quadrant},
            "header": {"magzp": float(header["MAGZP"]),
                       "exptime": float(header["EXPTIME"]),
                       "seeing": float(header["SEEING"]),
                       "maglim": float(header["MAGLIM"]),
                       "filter": str(header["FILTER"]), "infobits": 0},
        })
    return frames, epochs


def patch_wcs(ra, dec):
    return rd.target_wcs(ra, dec, SCALE, n=SIZE)


def extract_patch(frames, ra, dec):
    """Calibrated frames → north-up patches, native bounds, subtracted medians."""
    yy, xx = np.mgrid[:SIZE, :SIZE]
    world = patch_wcs(ra, dec).all_pix2world(xx, yy, 0)
    arrays, boxes, backgrounds = [], [], []
    for data, native in frames:
        px, py = native.all_world2pix(*world, 0)
        if (px.min() < 1 or py.min() < 1 or
                px.max() >= data.shape[1] - 2 or
                py.max() >= data.shape[0] - 2):
            return None
        boxes.append([float(px.min()), float(py.min()),
                      float(px.max()), float(py.max())])
        patch = map_coordinates(data, [py, px], order=1,
                                mode="constant", cval=np.nan,
                                prefilter=False)
        if not np.isfinite(patch).all():
            return None
        background = float(np.median(patch))
        backgrounds.append(background)
        arrays.append(patch - background)
    return np.stack(arrays), boxes, backgrounds


def prepare_field(quadrant, count):
    frames, epochs = fetch_frames(quadrant)
    reference = frames[0][1]
    excluded_x, excluded_y = reference.all_world2pix(*EXCLUDE, 0)
    yy, xx = np.mgrid[:SIZE, :SIZE]
    candidates = []
    # The north-up footprints rotate with position on this near-polar field.
    # Check actual bilinear source pixels, not overlapping bounding boxes.
    for y in range(80, 3000, 153):
        for x in range(80, 3000, 153):
            if quadrant == 3 and np.hypot(x - excluded_x, y - excluded_y) < 360:
                continue
            ra, dec = [float(v) for v in reference.all_pix2world(x, y, 0)]
            extracted = extract_patch(frames, ra, dec)
            if extracted is None:
                continue
            arrays, boxes, backgrounds = extracted
            entry = {"ra": ra, "dec": dec, "scale_arcsec": SCALE,
                     "native_center": [x, y], "native_footprints": boxes,
                     "backgrounds": backgrounds, "epochs": epochs}
            candidates.append((entry, arrays))
    if len(candidates) < count:
        raise RuntimeError(f"q{quadrant}: only {len(candidates)} valid patches; need {count}")
    chosen = [candidates[i] for i in np.linspace(0, len(candidates) - 1,
                                                count, dtype=int)]
    used = [np.zeros(data.size, dtype=bool) for data, _ in frames]
    for entry, _ in chosen:
        world = patch_wcs(entry["ra"], entry["dec"]).all_pix2world(xx, yy, 0)
        for occupied, (data, native) in zip(used, frames):
            px, py = native.all_world2pix(*world, 0)
            lo = np.floor(py).astype(int) * data.shape[1] + np.floor(px).astype(int)
            pixels = np.unique(np.concatenate([lo.ravel() + offset
                for offset in (0, 1, data.shape[1], data.shape[1] + 1)]))
            if occupied[pixels].any():
                raise RuntimeError("Пересекающиеся исходные пиксели участков")
            occupied[pixels] = True
    print(f"q{quadrant}: {len(candidates)} valid, {count} selected; no overlap", flush=True)
    return [entry for entry, _ in chosen], np.stack([a for _, a in chosen])


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    demo_entries, demo = prepare_field(3, 200)
    train_entries, train = prepare_field(4, 300)
    archive = OUT / "demo-fields.npz"
    np.savez_compressed(archive, demo=demo, train=train)
    provenance = {
        "version": 1, "archive": archive.name, "sha256": sha256(archive),
        "demo": demo_entries, "train": train_entries,
        "processing": "Три настоящих наблюдения ZTF r, 30 с. Нуль-пункт 25; "
            "WCS-перепроекция с билинейной интерполяцией на 128×128 пикселей, "
            "север сверху и восток слева в центре каждого участка. Из каждого "
            "кадра вычтена его медиана фона. PSF не уравнивалась: seeing и шум "
            "могут давать различия. Никакие источники не добавлены и не удалены.",
        "split": "200 демонстрационных участков: поле 872, CCD 10, q3; "
            "300 обучающих: q4 того же поля. Участки не пересекаются в "
            "исходных кадрах; область SN 2023tyk исключена из демонстрации.",
        "limitations": "Это не случайная выборка всего неба и не независимые "
            "ночи проверки. Обучающие участки не размечены как физически "
            "неизменные; ранг не является вероятностью события. Ошибки "
            "калибровки, PSF и шум общие для соседних участков.",
    }
    (OUT / "demo-provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"demo": list(demo.shape), "train": list(train.shape),
                      "archive_bytes": archive.stat().st_size,
                      "finite": bool(np.isfinite(demo).all() and np.isfinite(train).all())}))


if __name__ == "__main__":
    main()
