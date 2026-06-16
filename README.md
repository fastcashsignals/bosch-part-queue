# Bosch Part Queue

Field submission PWA for [Bosch Part Scout](https://fastcashsignals.github.io/bosch-part-scout/).

Guys take a photo of a part, enter the SAP/part number, name, cost center, and bin/location, and the submission lands in this repo. A daily cron job reviews the queue and updates the main Bosch Part Scout app.

## Live app

https://fastcashsignals.github.io/bosch-part-queue/

## Architecture

```
PWA  --(photo + data)-->  Cloudflare Worker  --(GitHub API)-->  bosch-part-queue repo
                                                                  |
                                                                  v
                                                          daily processor
                                                                  |
                                                                  v
                                                        bosch-part-scout repo
```

The Cloudflare Worker holds the GitHub token securely so the PWA doesn't expose it.

## Queue structure

- `submissions/images/{timestamp}_{sap}.{ext}` — part photos
- `submissions/data/{timestamp}_{sap}.json` — part data records

## Deploying the Worker

1. Sign up / log in at https://cloudflare.com
2. Install Wrangler or use the Cloudflare dashboard
3. Create a fine-grained GitHub PAT with **Contents: Read and write** for this repo only
4. Set `GITHUB_TOKEN` as a secret in the Worker
5. Deploy and copy the Worker URL
6. Paste the URL into `index.html` on the `WORKER_URL` line
7. Commit and push

## Processing

Daily at 6 AM EST, the queue is processed into `fastcashsignals/bosch-part-scout`:

- New SAP IDs are added to `parts.json`
- Existing SAP IDs get updated fields/photos
- Approved photos are moved to `images/{sap_id}.jpg`
- Processed submissions are deleted from this queue
