#!/usr/bin/env python3
"""Verify the optional ZEEKR 9X case assets after extraction."""
from hashlib import sha256
from pathlib import Path
import json
import sys

case = Path(__file__).resolve().parent
data = json.loads((case / "provenance.json").read_text(encoding="utf-8"))
missing = []
bad = []
for item in data["files"]:
    path = case / item["path"]
    if not path.is_file():
        missing.append(item["path"])
    elif sha256(path.read_bytes()).hexdigest() != item["sha256"]:
        bad.append(item["path"])
for name in ("final/index.html", "final/app.js", "final/model.js", "final/model.glb", "final/vendor/three.module.js", "final/vendor/LICENSE"):
    if not (case / name).is_file() and name not in missing:
        missing.append(name)
print(f"checked={len(data['files'])} missing={len(missing)} hash_mismatch={len(bad)}")
for name in missing:
    print(f"MISSING {name}", file=sys.stderr)
for name in bad:
    print(f"HASH_MISMATCH {name}", file=sys.stderr)
raise SystemExit(1 if missing or bad else 0)
