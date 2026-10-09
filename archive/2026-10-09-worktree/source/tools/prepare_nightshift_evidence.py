#!/usr/bin/env python3
"""Derive overlay anchors from existing local ZTF evidence; never fetch data.

Run with the project's .venv/bin/python. --check verifies generated artifacts.
The original science pipeline and embedded observations are read-only inputs.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import sys

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import generate_data as gd
from tools import realdata as rd

ORDER = ('s02', 's08', 's10', 's01', 's07', 's11', 's04', 's06', 's03')
OBS = ROOT / 'assets/observations'
OUT = ROOT / 'verification/nightshift-evidence'
JS = ROOT / 'app/nightshift-evidence.js'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def point(x, y):
    x, y = float(x), float(y)
    if not (np.isfinite([x, y]).all() and 0 <= x < 128 and 0 <= y < 128):
        raise ValueError(f'Anchor outside the image: {(x, y)}')
    return {'x': round(x, 4), 'y': round(y, 4)}


def artifact_anchor(entry, game, target):
    """Brightest positive excess supported by the instrument's defect mask.

    Match all four native pixels contributing to each bilinear game pixel.
    This gives one reproducible marker on a region, not a physical centroid.
    """
    epoch, bit = entry['mask_evidence']['epoch'], entry['mask_evidence']['bit']
    epochs = sorted(entry['epochs'], key=lambda e: e['mjd'])
    src = entry['mask_evidence']['sources'][epoch]
    science_header = rd.load_fits(OBS / epochs[epoch]['file'])[1]
    with fits.open(OBS / src['file'], memmap=False) as hdus:
        mask = np.asarray(hdus[0].data, dtype=np.uint16)
    yy, xx = np.indices((128, 128))
    world = target.all_pix2world(xx, yy, 0)
    px, py = WCS(science_header).all_world2pix(*world, 0)
    ix, iy = np.floor(px).astype(int), np.floor(py).astype(int)
    support = np.zeros((128, 128), dtype=bool)
    for dy, dx in ((0, 0), (0, 1), (1, 0), (1, 1)):
        support |= (mask[iy + dy, ix + dx] & (1 << bit)) != 0
    if not support.any():
        raise ValueError('No mask support on this game image')
    other = np.median(np.delete(game, epoch, axis=0), axis=0)
    excess = game[epoch] - other
    y, x = np.unravel_index(np.argmax(np.where(support, excess, -np.inf)), excess.shape)
    if excess[y, x] <= 0:
        raise ValueError('No positive artifact excess on mask-supported pixels')
    anchors = [None, None, None]
    anchors[epoch] = point(x, y)
    diagnostic = {'epoch': epoch, 'mask_bit': bit,
                  'supported_game_pixels': int(support.sum()),
                  'anchor_excess_calibrated_flux': float(excess[y, x]),
                  'mask_file': src['file']}
    return anchors, diagnostic


def build():
    manifest = read_json(OBS / 'manifest.json')
    data_text = (ROOT / 'app/data.js').read_text(encoding='utf-8')
    data = json.loads(data_text.split('window.GAME_DATA =', 1)[1].strip().rstrip(';'))
    if rd.sha256_file(OBS / 'manifest.json') != data['meta']['dataset']['manifest_sha256']:
        raise ValueError('Embedded frames reference another observation manifest')
    curated, curated_provenance = gd.load_prepared('curated')
    demo, _ = gd.load_prepared('demo')
    lo, top = gd.display_constants(demo['train'])
    motion_path = OBS / 'motion-fields/_research/acquire_report.json'
    motion_report = read_json(motion_path)
    groups = {label: iter(sorted(k for k, e in manifest['cases'].items()
                                if e['label'] == label)) for label in set(gd.CONTACT_LAYOUT)}
    keys = {f's{i:02d}': next(groups[label]) for i, label in enumerate(gd.CONTACT_LAYOUT, 1)}
    embedded = {c['id']: c for c in data['contact']}
    evidence, report, frames = {}, {}, {}
    used_files = {'manifest.json', 'curated-fields.npz', 'curated-provenance.json',
                  'demo-fields.npz', 'demo-provenance.json',
                  'motion-fields/_research/acquire_report.json'}
    for cid in ORDER:
        key, case = keys[cid], embedded[cid]
        entry = manifest['cases'][key]
        if case['type'] != entry['label'] or [case['ra'], case['dec']] != entry['patch_center']:
            raise ValueError(f'Case mapping changed: {cid}')
        for epoch in entry['epochs']:
            path = OBS / epoch['file']
            if rd.sha256_file(path) != manifest['files'][epoch['file']]['sha256']:
                raise ValueError(f'Source hash mismatch: {path}')
            used_files.add(epoch['file'])
        if key in curated:
            game = curated[key]
            center = (curated_provenance['cases'][key]['ra'],
                      curated_provenance['cases'][key]['dec'])
            scale = entry['scale_arcsec']
        else:
            game, scale, center = gd.field_stack(entry)
        twcs = rd.target_wcs(*center, scale)
        frame_hashes = []
        frames[cid] = []
        for array, uri in zip(game, case['frames'], strict=True):
            png = base64.b64decode(uri.split(',', 1)[1], validate=True)
            original = Image.open(io.BytesIO(png)).convert('RGB')
            rebuilt = Image.open(io.BytesIO(rd.png_bytes(array, lo, top))).convert('RGB')
            if original.size != (128, 128) or not np.array_equal(np.asarray(original), np.asarray(rebuilt)):
                raise ValueError(f'Cached science array does not match embedded PNG: {cid}')
            frames[cid].append(original)
            frame_hashes.append(hashlib.sha256(png).hexdigest())
        row = {'width': 128, 'height': 128, 'targets': [None] * 3}
        detail = {'case_key': key, 'epochs_mjd': [e['mjd'] for e in sorted(entry['epochs'], key=lambda e: e['mjd'])],
                  'scale_arcsec': scale, 'png_sha256': frame_hashes,
                  'embedded_png_matches_science_cache': True}
        if entry['label'] == 'mover':
            measurement = motion_report[key]['meas']
            if not motion_report[key]['ok'] or measurement['patch_center'] != list(center):
                raise ValueError('Motion report does not match current patch')
            if not np.isclose(measurement['scale_as'], scale, rtol=0, atol=1e-10):
                raise ValueError('Motion centroid report uses another image scale')
            rows = measurement['measured']
            epoch_mags = sorted(entry['epoch_mags'], key=lambda e: e['mjd'])
            if len(rows) != 3 or any(not np.isclose(m['mag_r'], e['mag'], rtol=0, atol=1e-10)
                                     for m, e in zip(rows, epoch_mags, strict=True)):
                raise ValueError('Motion centroid report does not match current epoch photometry')
            row['targets'] = [point(*twcs.all_world2pix(m['ra'], m['dec'], 0)) for m in rows]
            for p, m in zip(row['targets'], rows, strict=True):
                if np.hypot(p['x'] - m['x'], p['y'] - m['y']) > 0.001:
                    raise ValueError('Motion report pixel/WCS orientation mismatch')
            row.update(kind='motion',
                       note='Измеренные центроиды в каждой экспозиции; положение сверено с эфемеридой. Это не оценка точности орбиты.',
                       source=f'assets/observations/motion-fields/_research/acquire_report.json: {key}.meas.measured; manifest.json: {key}.skybot')
            detail['measured_world_positions'] = [{'ra': m['ra'], 'dec': m['dec']} for m in rows]
        elif entry['label'] == 'artifact':
            for src in entry['mask_evidence']['sources']:
                if rd.sha256_file(OBS / src['file']) != src['sha256']:
                    raise ValueError('Mask hash mismatch')
                used_files.add(src['file'])
            row['targets'], detail['artifact'] = artifact_anchor(entry, game, twcs)
            row.update(kind='artifact',
                       note='Точка на помехе: максимум положительной разности внутри области, подтверждённой исходной маской ZTF. В других кадрах помехи здесь нет; точка не обозначает физический центр следа.',
                       source=f'assets/observations/manifest.json: {key}.mask_evidence; cached ZTF sciimg/mskimg WCS')
        elif entry['label'] == 'normal':
            measured = curated_provenance['cases'][key]['measured_sources']
            first, *others = measured
            row['targets'] = [point(first['x'], first['y']) for _ in range(3)]
            row['controls'] = [point(s['x'], s['y']) for s in others]
            row.update(kind='comparison',
                       note='Яркая звезда с измеренным почти постоянным апертурным потоком; это опорная точка сравнения, а не найденная аномалия.',
                       source=f'assets/observations/curated-provenance.json: {key}.measured_sources')
        else:
            target = point(*twcs.all_world2pix(entry['ra'], entry['dec'], 0))
            row['targets'] = [target.copy() for _ in range(3)]
            note = 'Каталожная позиция источника на общей WCS-сетке; изменение блеска подтверждено независимой фотометрией, а не яркостью одного пикселя.'
            if key == 'sn2023tyk':
                row['targets'][0] = None
                note = ('Каталожная позиция SN 2023tyk. На обычном снимке свет смешан с соседним источником в 2,4″; это не отдельный центроид SN. '
                        'В первом кадре нет измерения SN: null. Октябрьская и ноябрьская точки имеют разностную PSF-фотометрию.')
            if entry.get('aperture_check', {}).get('comparison_stars'):
                row['controls'] = [point(*s['position']) for s in entry['aperture_check']['comparison_stars']]
            photometry_field = 'photometry_alerce' if key == 'sn2023tyk' else 'epoch_mags'
            source = (f'assets/observations/manifest.json: {key}.ra/dec, epochs, {photometry_field}; '
                      'tools/realdata.py: target_wcs')
            if row.get('controls'):
                source += f'; manifest.json: {key}.aperture_check.comparison_stars'
            row.update(kind='photometry', note=note, source=source)
        evidence[cid], report[cid] = row, detail
    sources = {str((OBS / f).relative_to(ROOT)): rd.sha256_file(OBS / f) for f in sorted(used_files)}
    report = {'coordinate_contract': 'Zero-based pixel centers, top-left origin; x right, y down. North up, east left. No PNG flip. For CSS percentages use (x+0.5)/128 and (y+0.5)/128.',
              'input_sha256': sources, 'display': {'lo': lo, 'top': top}, 'cases': report}
    return evidence, report, frames


def preview(evidence, frames):
    zoom, gap, title = 3, 12, 24
    size = 128 * zoom
    sheet = Image.new('RGB', (3 * (size + gap) + gap, len(ORDER) * (size + title + gap) + gap), '#152039')
    draw = ImageDraw.Draw(sheet)
    for n, cid in enumerate(ORDER):
        for epoch, frame in enumerate(frames[cid]):
            x0, y0 = gap + epoch * (size + gap), gap + n * (size + title + gap) + title
            sheet.paste(frame.resize((size, size), Image.Resampling.NEAREST), (x0, y0))
            p = evidence[cid]['targets'][epoch]
            draw.text((x0, y0 - title + 4), f'{cid} | frame {epoch + 1} | {evidence[cid]["kind"]}' + (' | null' if p is None else ''), fill='white')
            if p is not None:
                x, y = x0 + (p['x'] + 0.5) * zoom, y0 + (p['y'] + 0.5) * zoom
                draw.ellipse((x - 18, y - 18, x + 18, y + 18), outline='#fcb75a', width=2)
                draw.line((x - 5, y, x + 5, y), fill='#fcb75a', width=1)
                draw.line((x, y - 5, x, y + 5), fill='#fcb75a', width=1)
            for p in evidence[cid].get('controls', []):
                x, y = x0 + (p['x'] + 0.5) * zoom, y0 + (p['y'] + 0.5) * zoom
                draw.ellipse((x - 15, y - 15, x + 15, y + 15), outline='#70e7de', width=2)
    output = io.BytesIO()
    sheet.save(output, format='PNG')
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='check existing outputs without writing')
    args = parser.parse_args()
    evidence, report, frames = build()
    js = ('// Generated offline by tools/prepare_nightshift_evidence.py; coordinates are PNG pixel centers.\n'
          + 'window.NIGHTSHIFT_EVIDENCE = ' + json.dumps(evidence, ensure_ascii=False, indent=2) + ';\n')
    outputs = {JS: js.encode(), OUT / 'report.json': (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode(),
               OUT / 'overlays.png': preview(evidence, frames)}
    for path, content in outputs.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != content:
                raise ValueError(f'Generated artifact is stale: {path.relative_to(ROOT)}')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    print(f'{"Checked" if args.check else "Prepared"} {len(evidence)} cases; all 27 embedded PNGs match source-cache pixels; offline.')
    for cid, row in evidence.items():
        print(cid, row['kind'], row['targets'])


if __name__ == '__main__':
    main()
