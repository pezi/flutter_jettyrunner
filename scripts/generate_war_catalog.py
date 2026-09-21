#!/usr/bin/env python3
"""Generate the downloadable catalog after building Android-compatible WARs."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent / "war_repository"
demos = json.loads((root / "demos.json").read_text())
for demo in demos:
    war = root / demo["fileName"]
    if war.parent != root or not war.is_file():
        raise ValueError(f"Missing WAR: {demo['fileName']}")
    demo["sizeBytes"] = war.stat().st_size
    with war.open("rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        demo["sha256"] = digest.hexdigest()
(root / "wars.json").write_text(
    json.dumps({"schemaVersion": 1, "wars": demos}, ensure_ascii=False, indent=2) + "\n"
)
print(f"Generated catalog for {len(demos)} WARs in {root}")
