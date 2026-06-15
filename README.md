# Bosch Part Queue

Field submission PWA for [Bosch Part Scout](https://fastcashsignals.github.io/bosch-part-scout/).

Guys take a photo of a part, enter the SAP/part number, name, cost center, and bin/location, and the submission lands in this repo. A daily cron job reviews the queue and updates the main Bosch Part Scout app.

## Live app

https://fastcashsignals.github.io/bosch-part-queue/

## Queue structure

- `submissions/images/{timestamp}_{sap}.{ext}` — part photos
- `submissions/data/{timestamp}_{sap}.json` — part data records

## Setup

1. Create a GitHub fine-grained personal access token with write access to **only** this repo.
2. Paste the token into `index.html` on the `GITHUB_TOKEN` line.
3. Commit and push.

## Processing

Daily at 6 AM EST, the queue is processed into `fastcashsignals/bosch-part-scout`:

- New SAP IDs are added to `parts.json`
- Existing SAP IDs get updated fields/photos
- Approved photos are moved to `images/{sap_id}.jpg`
- Processed submissions are deleted from this queue
