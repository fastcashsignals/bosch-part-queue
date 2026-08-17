# Bosch Part Queue

Submission backend for [Bosch Parts](https://fastcashsignals.github.io/bosch-part-scout/).

Techs take a photo of a part and enter the SAP/part number, name, cost center(s), and bin/location. The submission lands in this repo, and a GitHub Action immediately syncs it into the main Bosch Parts catalog.

## Live app

The submission form now lives inside the main app — https://fastcashsignals.github.io/bosch-part-scout/

This repo's own Pages URL (`/bosch-part-queue/`) is just a redirect there, kept so old bookmarks and installed shortcuts still work.

## Architecture

```
App  --(photo + data)-->  Cloudflare Worker  --(GitHub API)-->  bosch-part-queue repo
                                                                  |
                                                    push triggers promote-submissions
                                                                  |
                                                                  v
                                                        bosch-part-scout repo
                                                            (parts.json)
```

The Cloudflare Worker holds the GitHub token so the app never exposes it.

## Queue structure

- `submissions/images/{timestamp}_{sap}.{ext}` — part photos
- `submissions/data/{timestamp}_{sap}.json` — part add/update records
- `submissions/deletes/{timestamp}_{sap}.json` — part delete markers (PIN-gated)

## Processing

`.github/workflows/promote-submissions.yml` runs on every push to `main` that
touches `submissions/data/**` or `submissions/deletes/**` — i.e. as soon as the
Worker commits a submission. It can also be run manually via *workflow_dispatch*.
There is **no scheduled/cron job**; syncing is push-triggered.

The workflow checks out this repo and `bosch-part-scout` side by side, runs
`scripts/promote_submissions.py`, then commits and pushes any catalog changes.

For each SAP ID the **newest event wins**, so a later delete removes a part and a
later resubmission brings it back:

- New SAP IDs are added to `parts.json`
- Existing SAP IDs get their fields and photo updated
- Photos are copied to `images/{sap_id}.jpg` with a `?v=<timestamp>` cache-buster
- Parts with a delete marker as their newest event are removed, along with their photo

Submissions are **not** deleted after processing. The script re-derives catalog
state from the full submission history on every run, which is what makes it
idempotent — so the history is load-bearing, not leftover clutter.

## Deploying the Worker

Worker deploys are automated: any push to `main` touching `worker/**` triggers
`.github/workflows/deploy-worker.yml`, which runs `wrangler deploy`. No manual
dashboard steps are needed for code changes.

First-time setup only:

1. Create a fine-grained GitHub PAT with **Contents: Read and write** on this repo, and set it as the Worker secret `GITHUB_TOKEN`
2. Set the Worker secret `DELETE_PIN` — the PIN techs must enter to delete a part
3. Confirm `ALLOWED_ORIGIN` in `worker/wrangler.toml` matches the app's origin
4. Copy the deployed Worker URL into the app's `WORKER_URL` line

Secrets are set with `wrangler secret put <NAME>` (or via the Cloudflare
dashboard) — never commit them.

## Repo secrets

Configured under **Settings → Secrets and variables → Actions**:

- `SCOUT_REPO_TOKEN` — write access to `bosch-part-scout`, used to push catalog updates
- `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` — used to deploy the Worker
