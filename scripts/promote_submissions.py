#!/usr/bin/env python3
"""
Promote part submissions from this repo into the Bosch Part Scout catalog.

Run from a workspace that contains two checked-out repos side by side:
  queue/  -> fastcashsignals/bosch-part-queue (this repo, with submissions/)
  scout/  -> fastcashsignals/bosch-part-scout (the catalog, with parts.json)

For each part, the LATEST submission (by timestamp) is used:

  * New part (sap_id not in the catalog): the full record is appended and
    its photo copied into scout/images/<sap_id>.<ext>.

  * Existing part: the latest submission is applied (photo + fields). The
    Submit form pre-fills the part's current values, so a resubmission only
    changes what the tech actually edited (commonly: adding/replacing the
    photo). This is what lets a tech fill in a photo or fix a detail later
    by submitting the same part again.

The image field carries a "?v=<timestamp>" cache-buster so a replaced photo
shows up on devices instead of the old cached copy. The script is
idempotent: re-running with no new submissions produces no changes.
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


def submission_ts(json_file):
    """Worker names files <ms-timestamp>_<sap>.json; use that for ordering."""
    base = os.path.basename(json_file)
    head = base.split("_", 1)[0]
    return int(head) if head.isdigit() else 0


def latest_per_sap():
    """Return {sap_id: (ts, record)} keeping only the newest submission."""
    latest = {}
    for json_file in glob.glob(os.path.join(DATA_DIR, "*.json")):
        try:
            with open(json_file) as f:
                rec = json.load(f)
        except (OSError, ValueError):
            continue
        sap = rec.get("sap_id")
        if not sap:
            continue
        ts = submission_ts(json_file)
        if sap not in latest or ts > latest[sap][0]:
            latest[sap] = (ts, rec)
    return latest


def copy_photo(rec, sap, ts):
    """Copy the submission photo into the catalog; return the image field."""
    src_rel = rec.get("image_path")
    if not src_rel:
        return None
    src_img = os.path.join(QUEUE, src_rel)
    if not os.path.isfile(src_img):
        return None
    ext = os.path.splitext(src_img)[1] or ".jpg"
    dst_rel = f"images/{sap}{ext}"
    shutil.copyfile(src_img, os.path.join(SCOUT, dst_rel))
    return f"{dst_rel}?v={ts}"


def main():
    with open(PARTS_PATH) as f:
        parts = json.load(f)

    by_sap = {p.get("sap_id"): p for p in parts if p.get("sap_id")}
    os.makedirs(SCOUT_IMAGES, exist_ok=True)

    added = 0
    updated = 0
    for sap, (ts, rec) in latest_per_sap().items():
        if sap in by_sap:
            # Existing part: apply the latest submission (fields + photo).
            # The Submit form pre-fills the current values, so unchanged
            # fields stay the same and only real edits take effect.
            entry = {key: rec.get(key) for key in FIELDS}
            image_field = copy_photo(rec, sap, ts) or by_sap[sap].get("image")
            if image_field:
                entry["image"] = image_field
            if entry != by_sap[sap]:
                by_sap[sap].clear()
                by_sap[sap].update(entry)
                updated += 1
                print(f"Updated {sap} - {rec.get('name')}")
        else:
            # New part: add the full record.
            entry = {key: rec.get(key) for key in FIELDS}
            image_field = copy_photo(rec, sap, ts)
            if image_field:
                entry["image"] = image_field
            parts.append(entry)
            by_sap[sap] = entry
            added += 1
            print(f"Added {sap} - {rec.get('name')}")

    if added or updated:
        with open(PARTS_PATH, "w") as f:
            f.write(json.dumps(parts, indent=2) + "\n")

    print(f"{added} part(s) added, {updated} part(s) updated.")


if __name__ == "__main__":
    main()
