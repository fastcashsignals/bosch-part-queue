#!/usr/bin/env python3
"""
Check that the part-submission pipeline is actually working, and say so loudly
when it is not.

Run by .github/workflows/pipeline-health.yml on a weekday schedule. It exits
non-zero when something is wrong, because a failed scheduled workflow is what
GitHub emails the repo owner about.

The fault this exists for: the Worker's GitHub token expires, submissions stop
saving, and nothing records it — no commit, no workflow run, no error anywhere
except on a tech's phone. In September 2026 that went unnoticed for three days.
The Worker's "?health=1" endpoint exists so check_worker() can see it directly.

Three checks:
  1. The Worker can still authenticate to GitHub (i.e. a submission would save).
  2. No promote or deploy run has failed in the last 7 days.
  3. Every submission that is old enough to have been promoted has reached the
     catalog.

Quiet is NOT a failure. The catalog was completed on 2026-09-13, so stretches
with no submissions are normal and must never raise an alert on their own.

Environment:
  WORKER_URL   base URL of the Cloudflare Worker
  GH_TOKEN     token that can read this repo (the workflow's own GITHUB_TOKEN)
  SCOUT_TOKEN  token that can read the catalog repo (SCOUT_REPO_TOKEN)
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

QUEUE_REPO = os.environ.get("GITHUB_REPOSITORY", "fastcashsignals/bosch-part-queue")
SCOUT_REPO = "fastcashsignals/bosch-part-scout"
WORKER_URL = os.environ.get("WORKER_URL", "https://bosch-part-queue.fastcashsignals.workers.dev")

# How long after a submission we still consider promotion "in flight" rather
# than broken. The workflow normally finishes within a minute.
PROMOTE_GRACE = timedelta(minutes=20)
LOOKBACK = timedelta(days=7)

TOKEN_REASONS = {
    "no_token": "GITHUB_TOKEN is not set on the Worker at all.",
    "token_rejected": "The Worker's GITHUB_TOKEN has expired or been revoked.",
    "token_forbidden": "The Worker's GITHUB_TOKEN no longer has access to this repo.",
}

CLOUDFLARE_FIX = (
    "Fix it in Cloudflare: Workers & Pages -> bosch-part-queue -> Settings -> "
    "Variables and Secrets -> GITHUB_TOKEN. See the token runbook."
)
SCOUT_FIX = (
    "Usually SCOUT_REPO_TOKEN: bosch-part-queue -> Settings -> Secrets and "
    "variables -> Actions."
)

problems = []


def fail(msg):
    """Record a problem and emit it as a GitHub Actions error annotation."""
    problems.append(msg)
    print(f"::error::{msg}")


def get_json(url, token=None, timeout=30):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "bosch-pipeline-health",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r), r.status


def parse_ts(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def check_worker():
    """Can a tech submit right now?"""
    print("\n== Can the Worker still save submissions? ==")
    url = f"{WORKER_URL}/?health=1"
    try:
        body, status = get_json(url)
    except urllib.error.HTTPError as e:
        try:
            body = json.load(e)
        except Exception:
            body = {}
        status = e.code
    except Exception as e:
        fail(f"Could not reach the Worker at all ({e.__class__.__name__}). "
             "It may be down, or the URL changed.")
        return

    reason = body.get("reason")
    print(f"HTTP {status} — {json.dumps(body)}")

    if status == 200 and body.get("submissions_working"):
        print("OK: the Worker can reach GitHub, so submissions would save.")
        return

    if reason in TOKEN_REASONS:
        fail(f"Techs CANNOT submit. {TOKEN_REASONS[reason]} {CLOUDFLARE_FIX}")
    else:
        fail(f"Techs CANNOT submit (reason: {reason or 'unknown'}). "
             "GitHub itself may be having trouble — re-run this job before "
             "changing anything.")


def check_workflow_failures(token):
    """Has any pipeline run failed recently?"""
    print("\n== Did any pipeline run fail in the last 7 days? ==")
    since = datetime.now(timezone.utc) - LOOKBACK
    for wf, what in (
        ("promote-submissions.yml",
         f"Submissions are saving but may not be reaching the catalog. {SCOUT_FIX}"),
        ("deploy-worker.yml",
         "The live Worker may not match this repo."),
    ):
        url = (f"https://api.github.com/repos/{QUEUE_REPO}"
               f"/actions/workflows/{wf}/runs?per_page=50")
        try:
            data, _ = get_json(url, token)
        except Exception as e:
            fail(f"Could not read {wf} runs ({e}).")
            continue

        bad = [r for r in data.get("workflow_runs", [])
               if r.get("conclusion") == "failure"
               and parse_ts(r["created_at"]) >= since]

        if not bad:
            print(f"{wf}: no failures in the last 7 days")
            continue
        for r in bad:
            print(f"  {r['created_at']}  {r.get('display_title','')[:60]}  {r['html_url']}")
        fail(f"{len(bad)} {wf} run(s) failed in the last 7 days. {what}")


def newest_commit_matching(repo, token, predicate):
    data, _ = get_json(f"https://api.github.com/repos/{repo}/commits?per_page=50", token)
    for c in data:
        if predicate(c["commit"]["message"]):
            return parse_ts(c["commit"]["committer"]["date"]), c["commit"]["message"]
    return None, None


def check_catalog_caught_up(gh_token, scout_token):
    """Did submissions actually reach the catalog?"""
    print("\n== Did every submission reach the catalog? ==")
    try:
        sub_at, sub_msg = newest_commit_matching(
            QUEUE_REPO, gh_token, lambda m: m.startswith("Part submission:"))
        sync_at, _ = newest_commit_matching(
            SCOUT_REPO, scout_token,
            lambda m: "Sync catalog from submissions" in m)
    except Exception as e:
        fail(f"Could not compare the two repos ({e}). If this is a 401 or 404 on "
             f"the catalog repo, SCOUT_REPO_TOKEN is likely bad. {SCOUT_FIX}")
        return

    print(f"newest submission:   {sub_at or 'none in the last 50 commits'}"
          + (f"  ({sub_msg})" if sub_msg else ""))
    print(f"newest catalog sync: {sync_at or 'none in the last 50 commits'}")

    if sub_at is None:
        print("No recent submissions, so nothing to promote. "
              "This is normal — the catalog is complete.")
        return
    if sync_at is None:
        fail("A submission exists but no catalog sync was found at all. " + SCOUT_FIX)
        return
    if sync_at >= sub_at:
        print("OK: the catalog is caught up with submissions.")
        return
    if datetime.now(timezone.utc) - sub_at < PROMOTE_GRACE:
        print("Newest submission is very recent; promotion may still be running. "
              "Not an error.")
        return

    fail(f"A submission from {sub_at:%Y-%m-%d %H:%M}Z never reached the catalog "
         f"(newest sync {sync_at:%Y-%m-%d %H:%M}Z). Submissions are saving but not "
         f"being promoted. {SCOUT_FIX}")


def main():
    gh_token = os.environ.get("GH_TOKEN")
    scout_token = os.environ.get("SCOUT_TOKEN")

    check_worker()
    if gh_token:
        check_workflow_failures(gh_token)
    else:
        fail("GH_TOKEN was not provided, so workflow runs could not be checked.")
    if gh_token and scout_token:
        check_catalog_caught_up(gh_token, scout_token)
    else:
        fail("SCOUT_TOKEN was not provided, so the catalog could not be checked.")

    print()
    if problems:
        print(f"{len(problems)} problem(s) found:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print("Pipeline healthy — techs can submit, and submissions reach the catalog.")


if __name__ == "__main__":
    main()
