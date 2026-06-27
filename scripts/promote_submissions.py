#!/usr/bin/env python3
"""
Promote part submissions from this repo into the Bosch Part Scout catalog.

Run from a workspace that contains two checked-out repos side by side:
  queue/  -> fastcashsignals/bosch-part-queue (this repo, with submissions/)
  scout/  -> fastcashsignals/bosch-part-scout (the catalog, with parts.json)

For each submission in queue/submissions/data/*.json whose sap_id is NOT
already in scout/parts.json, the part is appended to the catalog and its
photo is copied into scout/images/<sap_id>.<ext>.

Parts that already exist in the catalog are skipped, so manual edits to
parts.json (e.g. moving a part to a different cost center) are never
overwritten by a later sync.
"""

import glob
import json
import os
import shutil

QUEUE = "queue"
SCOUT = "scout"

DATA_DIR = os.path.join(QUEUE, "submissions", "data")
PARTS_PATH = os.path.join(SCOUT, "parts.json")
SCOUT_IMAGES = os.path.join(SCOUT, "images")

# Order of keys to match existing catalog records.
FIELDS = [
    "sap_id",
    "name",
    "category",
    "bin",
    "manufacturer",
    "model_number",
    "description",
    "cost_center_code",
]


def main():
    with open(PARTS_PATH) as f:
        parts = json.load(f)

    existing = {p.get("sap_id") for p in parts if p.get("sap_id")}
    os.makedirs(SCOUT_IMAGES, exist_ok=True)

    added = 0
    for json_file in sorted(glob.glob(os.path.join(DATA_DIR, "*.json"))):
        with open(json_file) as f:
            rec = json.load(f)

        sap = rec.get("sap_id")
        if not sap or sap in existing:
            continue

        entry = {key: rec.get(key) for key in FIELDS}

        # Copy the photo into the catalog if present.
        src_rel = rec.get("image_path")
        if src_rel:
            src_img = os.path.join(QUEUE, src_rel)
            if os.path.isfile(src_img):
                ext = os.path.splitext(src_img)[1] or ".jpg"
                dst_rel = f"images/{sap}{ext}"
                shutil.copyfile(src_img, os.path.join(SCOUT, dst_rel))
                entry["image"] = dst_rel

        parts.append(entry)
        existing.add(sap)
        added += 1
        print(f"Added {sap} - {rec.get('name')}")

    if added:
        with open(PARTS_PATH, "w") as f:
            f.write(json.dumps(parts, indent=2) + "\n")

    print(f"{added} part(s) promoted to catalog.")


if __name__ == "__main__":
    main()
