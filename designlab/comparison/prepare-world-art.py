#!/usr/bin/env python3
"""Package generated Arkhyz room variants; retain Nika base art bytes."""
import base64
import hashlib
import io
import json
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
script = HERE / 'world-art.js'
art = json.loads(script.read_text().split('window.NIGHTSHIFT_ART = ', 1)[1].rstrip().removesuffix(';'))
sources = {}
for key, filename in [('room', 'observatory-arkhyz-night-v1.png'), ('roomDawn', 'observatory-arkhyz-dawn-v1.png'), ('mentorSuccess', 'nika-success-v1.png')]:
    path = HERE / 'art' / filename
    with Image.open(path) as source:
        buffer = io.BytesIO()
        source.save(buffer, 'WEBP', quality=88, method=6)
        art[key] = 'data:image/webp;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')
        sources[key] = {'file': 'art/' + filename, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'size': list(source.size), 'mode': source.mode}
script.write_text('/* Fictional scene artwork; credits: world-art-credits.md. */\nwindow.NIGHTSHIFT_ART = ' + json.dumps(art) + ';\n')
path = HERE / 'world-provenance.json'
provenance = json.loads(path.read_text())
provenance['art'] = 'Arkhyz-inspired night room and matching dawn generated using built-in Imagegen. Nika base identity retained. Scientific pixels are separate.'
provenance['artSha256'] = hashlib.sha256(script.read_bytes()).hexdigest()
provenance['sceneVariants'] = sources
provenance['sceneVariantPrompts'] = ['art/scene-prompts.md', 'art/arkhyz-prompts.md']
path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'keys': list(art), 'sources': sources}))
