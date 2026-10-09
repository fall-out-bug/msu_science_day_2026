#!/usr/bin/env python3
"""Embed locally stored fictional scenery; never modifies scientific images."""
import base64
import io
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
art = {}
for key, name in (("room", "observatory-v1.png"), ("mentor", "nika-v1.png")):
    source = ROOT / "assets" / "nightshift" / name
    if not source.exists():
        if key == "room":
            raise FileNotFoundError(source)
        continue
    buffer = io.BytesIO()
    Image.open(source).save(buffer, "WEBP", quality=88, method=6)
    art[key] = "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
(ROOT / "app" / "nightshift-art.js").write_text(
    "/* Generated fictional scenery; sources: assets/nightshift/CREDITS.md. */\n"
    + "window.NIGHTSHIFT_ART = " + json.dumps(art) + ";\n", encoding="utf-8")
print("Embedded art:", ", ".join(art))
