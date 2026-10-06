#!/usr/bin/env python3
"""Библиотека обработки реальных кадров ZTF (общая для import и generate_data).

Все величины детерминированы кэшем assets/observations и константами ниже.
Игровые участки — 128×128, север сверху в отображаемом PNG.
Обучающая выборка подготовлена отдельно из непересекающихся участков.

Фотометрическая шкала: flux = DN × 10^(−0.4·(MAGZP − CAL_ZP)), CAL_ZP=25.
Калибровка задаёт общую шкалу потока, но не устраняет изменения PSF,
шума и систематические ошибки между экспозициями.
"""
import base64
import io

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from scipy import ndimage

PATCH = 128          # игровое поле, px (центрировано на цели/позиции)
CAL_ZP = 25.0           # «нуль-пункт» общей шкалы

# отображение: asinh + приглушённый цвет (только PNG, не признаки/score)
STRETCH_ALPHA = 0.2
STRETCH_TOP = 900.0
STRETCH_STOPS = ((9, 13, 30), (24, 40, 78), (92, 132, 190), (238, 242, 250))


# --- чтение и калибровка ---------------------------------------------------

def load_fits(path):
    """FITS-вырезка → (float32 data, header)."""
    with fits.open(str(path), memmap=False) as hdul:
        data = np.asarray(hdul[0].data, dtype=np.float32)
        header = hdul[0].header.copy()
    return data, header


def calibrate(data, magzp):
    """DN → общая шкала CAL_ZP по калибровочному нуль-пункту кадра."""
    return data * np.float32(10.0 ** (-0.4 * (float(magzp) - CAL_ZP)))


def pixel_scale(header):
    """Модуль масштаба px→угловые секунды из CD-матрицы."""
    wcs = WCS(header)
    cd = wcs.pixel_scale_matrix
    return float(np.sqrt(abs(cd[0, 0] * cd[1, 1] - cd[0, 1] * cd[1, 0])) * 3600.0)


# --- выравнивание по WCS ----------------------------------------------------

def target_wcs(ra, dec, scale_arcsec, n=PATCH):
    """Общая сетка: TAN, север вверху, восток влево, центр = (ra, dec)."""
    w = WCS(naxis=2)
    w.wcs.crpix = [(n + 1) / 2.0, (n + 1) / 2.0]
    w.wcs.crval = [float(ra), float(dec)]
    s = float(scale_arcsec) / 3600.0
    w.wcs.cd = [[-s, 0.0], [0.0, -s]]  # PNG: строки растут вниз, север сверху
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.radesys = "ICRS"
    return w


def align_epoch(data, header, twcs, n=PATCH):
    """Перепроекция на заданную общую сетку; пропуски остаются NaN."""
    yy, xx = np.indices((n, n), dtype=np.float64)
    ra, dec = twcs.all_pix2world(xx, yy, 0)
    sx, sy = WCS(header).all_world2pix(ra, dec, 0)
    coords = np.stack([sy, sx])
    out = ndimage.map_coordinates(
        data, coords, order=1, mode="constant", cval=np.nan, prefilter=False)
    return out.astype(np.float32, copy=False)


# --- признаки детектора (по калиброванным кадрам, до растяжения) ------------

def robust_sigma(a):
    """Робастная σ = 1.4826·MAD."""
    med = np.median(a)
    return float(1.4826 * np.median(np.abs(a - med))) + 1e-12


def features(e1, e2):
    """(max_diff, area, peak): максимум |разности|, площадь >4σ, пик в σ."""
    diff = e2 - e1
    sigma = robust_sigma(diff[np.isfinite(diff)])
    f_max = float(np.max(np.abs(diff)))
    f_area = int(np.sum(np.abs(diff) > 4.0 * sigma))
    f_peak = float(np.max(diff) / sigma)
    return np.array([f_max, f_area, f_peak], dtype=float), diff, sigma


# --- источники и морфология (курирование артефактов) ------------------------

def detect_sources(img, k=5.0):
    """Локальные максимумы > kσ над робастным фоном (простой детектор)."""
    finite = img[np.isfinite(img)]
    bg = float(np.median(finite))
    sigma = robust_sigma(finite)
    smooth = ndimage.gaussian_filter(np.nan_to_num(img, nan=bg), 1.0)
    mx = ndimage.maximum_filter(smooth, size=5)
    peaks = (smooth == mx) & (smooth > bg + k * sigma)
    ys, xs = np.nonzero(peaks)
    return [(float(x), float(y), float(smooth[y, x] - bg)) for x, y in
            zip(xs, ys)]


def moment_width(img, x, y, box=6):
    """σ_второго момента источника (px) в квадрате box вокруг (x, y)."""
    xi, yi = int(round(x)), int(round(y))
    sub = img[max(0, yi - box):yi + box + 1, max(0, xi - box):xi + box + 1]
    sub = np.nan_to_num(sub, nan=np.nanmedian(sub) if np.isfinite(sub).any() else 0.0)
    sub = sub - np.median(sub)
    sub = np.clip(sub, 0.0, None)
    tot = float(sub.sum())
    if tot <= 0:
        return float("nan")
    yy, xx = np.mgrid[0:sub.shape[0], 0:sub.shape[1]]
    xx = xx + max(0, xi - box) - x
    yy = yy + max(0, yi - box) - y
    vxx = float((sub * xx * xx).sum() / tot)
    vyy = float((sub * yy * yy).sum() / tot)
    vxy = float((sub * xx * yy).sum() / tot)
    ev = np.linalg.eigvalsh([[vxx, vxy], [vxy, vyy]])
    return float(np.sqrt(max(ev[0], 0.0)))


def aperture_flux(img, x, y, r=5.0, ann=(9.0, 13.0)):
    """Апертурный поток с локальным фоном из кольца (для относительной фотометрии)."""
    yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
    d2 = (xx - x) ** 2 + (yy - y) ** 2
    ring = img[(d2 >= ann[0] ** 2) & (d2 <= ann[1] ** 2) & np.isfinite(img)]
    bg = float(np.median(ring)) if ring.size else 0.0
    m = (d2 <= r * r) & np.isfinite(img)
    return float(np.sum(img[m] - bg)), float(bg)


# --- отображение ------------------------------------------------------------

def stretch_rgb(arr, lo, top, alpha=STRETCH_ALPHA, stops=STRETCH_STOPS):
    v = np.clip(arr - lo, 0.0, None)
    t = np.arcsinh(v * alpha) / np.arcsinh(top * alpha)
    t = np.clip(t, 0.0, 1.0)
    xp = [0.0, 1 / 3, 2 / 3, 1.0]
    n = arr.shape[0]
    from PIL import Image
    channels = [np.interp(t, xp, [s[k] for s in stops]).reshape(n, n)
                for k in range(3)]
    return Image.fromarray(np.stack(channels, axis=-1).astype(np.uint8), mode="RGB")


def png_bytes(arr, lo, top):
    """PNG-байты кадра в фиксированном отображении (печать и data URI)."""
    buf = io.BytesIO()
    stretch_rgb(arr, lo, top).quantize(colors=256).save(
        buf, format="PNG", optimize=True)
    return buf.getvalue()


def frames_data_uris(epochs, lo, top):
    return ["data:image/png;base64," +
            base64.b64encode(png_bytes(e, lo, top)).decode("ascii")
            for e in epochs]


# --- manifest helpers -------------------------------------------------------

def sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_iso_from_mjd(mjd, seconds=False):
    import datetime
    t = datetime.datetime(1858, 11, 17) + datetime.timedelta(days=float(mjd))
    t = t.replace(microsecond=0)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")
