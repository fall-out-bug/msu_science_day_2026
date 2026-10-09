#!/usr/bin/env python3
"""Export existing science arrays for an offline image-comparison probe."""
import base64
import io
import json
from pathlib import Path
import shutil
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import generate_data as gd
from tools import realdata as rd

HERE = Path(__file__).resolve().parent


def main():
    manifest = json.loads((gd.OBS / 'manifest.json').read_text())
    raw = (ROOT / 'app/data.js').read_text().split('window.GAME_DATA =', 1)[1].strip().rstrip(';')
    embedded = {c['id']: c for c in json.loads(raw)['contact']}
    curated, _ = gd.load_prepared('curated')
    demo, _ = gd.load_prepared('demo')
    lo, top = gd.display_constants(demo['train'])
    rows, evidence = [], {}
    sources = ['manifest.json', 'curated-fields.npz', 'curated-provenance.json',
               'demo-fields.npz', 'demo-provenance.json']
    for cid, key, name in [('s02','mover1','Участок 01'), ('s07','mover2','Участок 02'),
                            ('s04','artifact_spike','Участок 03')]:
        entry = manifest['cases'][key]
        images = curated[key] if key in curated else gd.field_stack(entry)[0]
        hashes = []
        for frame, uri in zip(images, embedded[cid]['frames'], strict=True):
            png = base64.b64decode(uri.split(',')[1])
            original = np.asarray(Image.open(io.BytesIO(png)).convert('RGB'))
            rebuilt = np.asarray(Image.open(io.BytesIO(rd.png_bytes(frame, lo, top))).convert('RGB'))
            assert np.array_equal(original, rebuilt), f'{cid}: science/preview mismatch'
            import hashlib
            hashes.append(hashlib.sha256(png).hexdigest())
        for epoch in entry['epochs']:
            path = gd.OBS / epoch['file']
            assert rd.sha256_file(path) == manifest['files'][epoch['file']]['sha256']
            sources.append(epoch['file'])
        # One fixed scale/noise threshold per field, independent of player setting.
        noise = max(rd.robust_sigma(images[1] - images[0]), rd.robust_sigma(images[2] - images[0]))
        rows.append(dict(id=cid, name=name, source='Архив ZTF / IRSA',
            dates=[o['date'] for o in embedded[cid]['observations']],
            frames=embedded[cid]['frames'], arrays=[frame.reshape(-1).tolist() for frame in images],
            sources=[[dict(x=x, y=y, peak=peak) for x,y,peak in rd.detect_sources(frame, k=5)] for frame in images],
            displayTop=top, noise=noise))
        evidence[cid] = dict(case_key=key, previews_equal_science=True, png_sha256=hashes,
                            noise=noise, display_top=top)
    payload = dict(cases=rows, provenance='provenance.json')
    (HERE / 'data.js').write_text('window.COMPARISON_DATA = ' + json.dumps(payload, separators=(',',':')) + ';\n')
    provenance = dict(cases=evidence,
        input_sha256={str((gd.OBS / p).relative_to(ROOT)):rd.sha256_file(gd.OBS / p) for p in sorted(set(sources))},
        coordinate_contract='128x128, zero-based centers, x right, y down; render center at x+.5,y+.5',
        operation='frame[epoch] - amount * frame[0]; signed display, fixed intensity scale per field',
        display_gain=8,
        tracking_sources='Blind local maxima from realdata.detect_sources(k=5) on each raw calibrated frame. No truth seeds.',
        limits=['No PSF matching; stationary sources can leave residuals.',
                'Detection peaks are not objects or classes.',
                'All images archived; epoch toggle does not request a new observation.',
                'No ML in this comparison-only experiment.'],
        acknowledgments=manifest['survey'])
    (HERE / 'provenance.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2)+'\n')
    vendor = HERE / 'vendor'
    vendor.mkdir(exist_ok=True)
    for p in (ROOT / 'designlab/trajectory/vendor').iterdir():
        if p.is_file():
            shutil.copyfile(p, vendor / p.name)
    print(json.dumps(dict(cases=len(rows), displayTop=top, noise=[r['noise'] for r in rows],
                         data_bytes=(HERE/'data.js').stat().st_size)))


if __name__ == '__main__':
    main()
