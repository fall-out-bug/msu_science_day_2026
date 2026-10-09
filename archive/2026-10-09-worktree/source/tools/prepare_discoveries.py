#!/usr/bin/env python3
"""Prepare the discovery stories from measured Kepler fluxes and ZTF images."""
from __future__ import annotations

import hashlib
import base64
import io
import json
from pathlib import Path
import tarfile
import sys
from urllib.request import urlopen

import numpy as np
from astropy.io import fits
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import realdata as rd
DEST = ROOT / "assets" / "discoveries"
URL = "https://archive.stsci.edu/missions/kepler/lightcurves/0114/011442793/kplr011442793_lc_Q011111110111011101.tar"
PAPER = "https://arxiv.org/abs/1712.05044"
# Published best-fit ephemeris, Shallue & Vanderburg, Table 5. BJD_TDB days.
PERIOD = 14.44912
EPOCH = 2455644.3488


def prepare_supernova():
    """Actual ZTF science and pipeline difference images, not drawn transients."""
    ra, dec = 143.79799404615386, 83.9734582153846
    target = rd.target_wcs(ra, dec, 1.01286, n=128)
    frames, provenance = [], []
    for exposure in ("20231007507292", "20231110430868"):
        observation = {}
        for product, suffix, extension in (("science", "sciimg.fits", 0),
                                             ("difference", "scimrefdiffimg.fits.fz", 1)):
            filename = f"ztf_{exposure}_000872_zr_c10_o_q3"
            url = (f"https://irsa.ipac.caltech.edu/ibe/data/ztf/products/sci/"
                   f"{exposure[:4]}/{exposure[4:8]}/{exposure[8:]}/{filename}_{suffix}"
                   f"?center={ra},{dec}&size=160arcsec&gzip=false")
            path = DEST / f"{filename}_{product}.fits"
            if not path.exists():
                with urlopen(url, timeout=120) as response:
                    path.write_bytes(response.read())
            with fits.open(path) as hdus:
                image, header = hdus[extension].data, hdus[extension].header
                image = rd.align_epoch(rd.calibrate(image, header["MAGZP"]),
                                       header, target, n=128)
                date = rd.utc_iso_from_mjd(float(header["OBSJD"]) - 2400000.5)
            if not np.isfinite(image).all():
                raise ValueError(f"Incomplete supernova observation: {path}")
            if product == "science":
                image -= np.median(image)
                rendered = rd.stretch_rgb(image, 0, 300)
            else:
                # Signed difference: grey is zero, white positive, black negative.
                value = np.clip(0.5 + np.arcsinh(image * 0.2) /
                                (2 * np.arcsinh(120 * 0.2)), 0, 1)
                rendered = Image.fromarray((value * 255).astype(np.uint8))
            stream = io.BytesIO()
            rendered.save(stream, format="PNG", optimize=True)
            observation[product] = "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")
            observation[product + "Source"] = url.split("?")[0]
            observation["date"] = date
            provenance.append({"file": path.name, "url": url, "date": date,
                               "sha256": rd.sha256_file(path), "product": product})
        frames.append(observation)
    note = ("Настоящие продукты ZTF из IRSA: sciimg и scimrefdiffimg. Разность "
            "с опорным изображением уже рассчитана конвейером ZTF с согласованием "
            "изображений; это не наши нарисованные точки. Мы выровняли вырезки по WCS "
            "вокруг координат SN 2023tyk, привели поток к нуль-пункту 25 и применили "
            "одинаковую шкалу к обеим датам. На обычных кадрах медиана фона вычтена, "
            "шкала asinh: α = 0,2, верхний уровень 300. На разностях: знаковый asinh, "
            "α = 0,2, диапазон −120…+120; серый означает нулевую разность. "
            "Север сверху, восток слева; ширина участка около 2,2 угловой минуты.")
    return {"frames": frames, "ra": ra, "dec": dec, "note": note,
            "credit": "ZTF / Caltech / IPAC / IRSA. SN 2023tyk = ZTF23abhvlji."}, {
            "sources": provenance, "processing": note}


def prepare() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    archive = DEST / "kepler90-long-cadence.tar"
    if not archive.exists():
        with urlopen(URL, timeout=120) as response:
            archive.write_bytes(response.read())
    samples = []
    sources = []
    with tarfile.open(archive) as tar:
        for member in sorted(tar.getmembers(), key=lambda m: m.name):
            if not member.name.endswith("_llc.fits"):
                continue
            with tar.extractfile(member) as source:
                raw = source.read()
            with fits.open(io.BytesIO(raw)) as hdus:
                h, table = hdus[1].header, hdus[1].data
                time = np.asarray(table["TIME"], dtype=float)
                flux = np.asarray(table["PDCSAP_FLUX"], dtype=float)
                valid = np.isfinite(time) & np.isfinite(flux) & (flux > 0) & (table["SAP_QUALITY"] == 0)
                time, flux = time[valid] + h["BJDREFI"] + h.get("BJDREFF", 0), flux[valid]
                orbit = np.rint((time - EPOCH) / PERIOD).astype(int)
                phase = time - EPOCH - orbit * PERIOD
                # Each event is normalized to a local baseline measured outside
                # the published 2.8-hour transit. No synthetic transit/model fit.
                for event in np.unique(orbit):
                    group = orbit == event
                    near = group & (np.abs(phase) <= 0.5)
                    baseline = near & (np.abs(phase) >= 0.18)
                    if np.count_nonzero(baseline) < 12 or np.count_nonzero(near) < 20:
                        continue
                    median = np.median(flux[baseline])
                    scatter = 1.4826 * np.median(np.abs(flux[baseline] - median))
                    clean = baseline & (np.abs(flux - median) <= 4 * scatter)
                    if np.count_nonzero(clean) < 12:
                        continue
                    slope, intercept = np.polyfit(phase[clean], flux[clean], 1)
                    relative = (flux[near] / (slope * phase[near] + intercept) - 1) * 1e6
                    samples.extend(zip(phase[near] * 24, relative))
                sources.append({"file": Path(member.name).name, "sha256": hashlib.sha256(raw).hexdigest(),
                                "quarter": int(hdus[0].header["QUARTER"]), "validMeasurements": len(time),
                                "start": hdus[0].header.get("DATE-OBS"), "end": hdus[0].header.get("DATE-END")})
    points = np.array(samples)
    bins = []
    for left in np.arange(-12, 12, 0.5):
        selected = points[(points[:, 0] >= left) & (points[:, 0] < left + 0.5), 1]
        # Robust clipping only removes isolated extreme measurements, not based
        # on phase or an expected transit. Counts and uncertainty remain visible.
        median = np.median(selected)
        mad = 1.4826 * np.median(np.abs(selected - median))
        selected = selected[np.abs(selected - median) <= 4 * mad]
        bins.append([round(float(left + 0.25), 2), round(float(np.mean(selected)), 2),
                     round(float(np.std(selected, ddof=1) / np.sqrt(len(selected))), 2), len(selected)])
    supernova, supernova_provenance = prepare_supernova()
    data = {
        "kepler90": {
            "period": PERIOD, "epochBjdTdb": EPOCH, "points": np.round(points, 2).tolist(), "bins": bins,
            "count": len(points), "quarters": [s["quarter"] for s in sources], "source": URL, "paper": PAPER,
            "credit": "NASA / Kepler / MAST. Обработка публичных измерений для этой игры.",
            "note": "Измерения PDCSAP_FLUX с SAP_QUALITY = 0. Для каждого прохождения линейный уровень яркости звезды оценён по измерениям за 4,32–12 часов до и после середины транзита; поток разделён на этот уровень. Это нормировка яркости звезды, а не вычитание фона неба. Время сложено с периодом 14,44912 суток и эпохой BJD_TDB 2455644,3488 из таблицы 5 статьи. Средние рассчитаны в интервалах по 30 минут с отсечением выбросов дальше четырёх робастных оценок σ (σ = 1,4826 MAD); отрезки показывают стандартную ошибку среднего. Это наша обработка архивных измерений, не график авторов статьи и не повторное открытие планеты.",
        },
        "sn2023tyk": supernova,
    }
    (DEST / "provenance.json").write_text(json.dumps({"url": URL, "archiveSha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "paper": PAPER, "files": sources, "processing": data["kepler90"]["note"],
        "sn2023tyk": supernova_provenance}, ensure_ascii=False, indent=2) + "\n")
    (ROOT / "app" / "discovery-data.js").write_text("window.DISCOVERY_DATA=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print(json.dumps({"files": len(sources), "measurements": len(points), "bins": len(bins)}, ensure_ascii=False))


if __name__ == "__main__":
    prepare()
