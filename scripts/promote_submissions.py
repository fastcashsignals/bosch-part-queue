#!/usr/bin/env python3
"""
Sync part submissions from this repo into the Bosch Part Scout catalog.

Run from a workspace that contains two checked-out repos side by side:
  queue/  -> fastcashsignals/bosch-part-queue (this repo, with submissions/)
  scout/  -> fastcashsignals/bosch-part-scout (the catalog, with parts.json)

Two kinds of submissions are processed, each timestamped in its filename:

  * submissions/data/<ts>_<sap>.json    -> add or update a part
  * submissions/deletes/<ts>_<sap>.json -> remove a part

For each part the NEWEST event wins, so a later delete removes a part and a
later resubmission brings it back. Behaviour:

  * Add (new part): full record appended, photo copied to scout/images/.
  * Update (existing part): the latest submission is applied; the Submit
    form pre-fills current values, so only real edits take effect.
  * Delete: the part is removed from parts.json and its photo deleted.

The image field carries "?v=<timestamp>" so a replaced photo shows up on
devices instead of a cached copy. The script is idempotent: re-running with
no newer events produces no changes.

Parts used on more than one machine carry "additional_cost_centers"; the key
is written only when non-empty, so parts without extras are left untouched.
"""

import glob
import json
import os
import shutil

QUEUE = "queue"
SCOUT = "scout"

DATA_DIR = os.path.join(QUEUE, "submissions", "data")
DELETES_DIR = os.path.join(QUEUE, "submissions", "deletes")
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


def clean_additional_ccs(rec, primary):
    """
    Extra cost centers a part is also used on.

    Kept out of FIELDS on purpose: the key is only written when there is
    something in it, so parts that never had extra cost centers stay exactly
    as they are instead of gaining an empty/null field (which would also make
    every such part look "updated" on every run).
    """
    raw = rec.get("additional_cost_centers") or []
    if isinstance(raw, str):
        raw = [raw]
    out = []
    for item in raw:
        cc = str(item or "").strip()
        if cc and cc != primary and cc not in out:
            out.append(cc)
    return out


def event_ts(json_file):
    """Files are named <ms-timestamp>_<sap>.json; use that for ordering."""
    head = os.path.basename(json_file).split("_", 1)[0]
    return int(head) if head.isdigit() else 0


def latest_adds():
    """{sap_id: (ts, record)} keeping the newest add/update per part."""
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
        ts = event_ts(json_file)
        if sap not in latest or ts > latest[sap][0]:
            latest[sap] = (ts, rec)
    return latest


def latest_deletes():
    """{sap_id: ts} keeping the newest delete request per part."""
    latest = {}
    for json_file in glob.glob(os.path.join(DELETES_DIR, "*.json")):
        try:
            with open(json_file) as f:
                rec = json.load(f)
        except (OSError, ValueError):
            continue
        sap = rec.get("sap_id")
        if not sap:
            continue
        ts = event_ts(json_file)
        if sap not in latest or ts > latest[sap]:
            latest[sap] = ts
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
    dst_abs = os.path.join(SCOUT, dst_rel)
    # Drop any earlier photo for this part saved under a different extension,
    # or a PNG placeholder would sit around forever once a JPEG replaces it.
    for stale in glob.glob(os.path.join(SCOUT_IMAGES, sap + ".*")):
        if os.path.abspath(stale) != os.path.abspath(dst_abs):
            try:
                os.remove(stale)
            except OSError:
                pass
    shutil.copyfile(src_img, dst_abs)
    return f"{dst_rel}?v={ts}"


def delete_photos(sap):
    for img in glob.glob(os.path.join(SCOUT_IMAGES, sap + ".*")):
        try:
            os.remove(img)
        except OSError:
            pass


def main():
    with open(PARTS_PATH) as f:
        parts = json.load(f)

    by_sap = {p.get("sap_id"): p for p in parts if p.get("sap_id")}
    os.makedirs(SCOUT_IMAGES, exist_ok=True)

    adds = latest_adds()
    dels = latest_deletes()

    added = updated = removed = 0
    remove_saps = set()

    for sap in set(adds) | set(dels):
        add_ts = adds[sap][0] if sap in adds else -1
        del_ts = dels.get(sap, -1)

        if del_ts > add_ts:
            # Delete is the most recent event for this part.
            if sap in by_sap:
                remove_saps.add(sap)
                delete_photos(sap)
                removed += 1
                print(f"Removed {sap}")
            continue

        rec = adds[sap][1]
        if sap in by_sap:
            # Existing part: apply the latest submission (fields + photo).
            entry = {key: rec.get(key) for key in FIELDS}
            extra_ccs = clean_additional_ccs(rec, entry.get("cost_center_code"))
            if extra_ccs:
                entry["additional_cost_centers"] = extra_ccs
            image_field = copy_photo(rec, sap, add_ts) or by_sap[sap].get("image")
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
            extra_ccs = clean_additional_ccs(rec, entry.get("cost_center_code"))
            if extra_ccs:
                entry["additional_cost_centers"] = extra_ccs
            image_field = copy_photo(rec, sap, add_ts)
            if image_field:
                entry["image"] = image_field
            parts.append(entry)
            by_sap[sap] = entry
            added += 1
            print(f"Added {sap} - {rec.get('name')}")

    if remove_saps:
        parts = [p for p in parts if p.get("sap_id") not in remove_saps]

    if added or updated or removed:
        with open(PARTS_PATH, "w") as f:
            f.write(json.dumps(parts, indent=2) + "\n")

    print(f"{added} added, {updated} updated, {removed} removed.")


if __name__ == "__main__":
    main()
