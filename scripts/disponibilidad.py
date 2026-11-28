"""
Availability of production over a period, from the uptime workflow's runs
(meta M5, RNF-04).

Each run of .github/workflows/uptime.yml is one sample, taken every 5
minutes: success means the API and the frontend both answered. Prints the
samples, the failures with their time, and the percentage.

Usage: python scripts/disponibilidad.py [desde AAAA-MM-DD] [hasta AAAA-MM-DD]
The repository is public, so no token is needed.
"""
import sys
from datetime import datetime, timezone

import httpx

REPO = "backendtrash/BackendFinanceApp"
since = sys.argv[1] if len(sys.argv) > 1 else "2026-11-28"
until = sys.argv[2] if len(sys.argv) > 2 else datetime.now(timezone.utc).date().isoformat()

runs, page = [], 1
with httpx.Client(timeout=30) as c:
    while True:
        r = c.get(f"https://api.github.com/repos/{REPO}/actions/workflows/uptime.yml/runs",
                  params={"per_page": 100, "page": page, "status": "completed",
                          "created": f"{since}..{until}"})
        r.raise_for_status()
        batch = r.json()["workflow_runs"]
        runs += batch
        if len(batch) < 100:
            break
        page += 1

samples = [x for x in runs if x["event"] == "schedule"]
down = [x for x in samples if x["conclusion"] != "success"]
if not samples:
    sys.exit(f"No samples between {since} and {until}.")
first = min(x["created_at"] for x in samples)
last = max(x["created_at"] for x in samples)
pct = (len(samples) - len(down)) / len(samples) * 100
print(f"Periodo: {first} a {last} (UTC)")
print(f"Muestras: {len(samples)} · caídas: {len(down)} · disponibilidad: {pct:.2f}%")
for x in down:
    print(f"  caída: {x['created_at']} ({x['conclusion']}) {x['html_url']}")
