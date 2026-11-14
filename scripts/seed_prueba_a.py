"""
Loads a year of realistic data into a test account, through the API.

For checking the essential charts and the PDF report against known figures
(package 3.4) and for test case CP-11 (about 200 movements over 12 months).
Everything it creates is tagged "[seed-h4]" in its notes or name, and a
second run creates nothing that already exists.

Only for the test accounts. Usage:

    python scripts/seed_prueba_a.py path/to/isolation.env [--base-url URL]

The env file holds EXPOS_TEST_USER_A_EMAIL and EXPOS_TEST_USER_A_PASSWORD.
"""
import argparse
import calendar
import random
import sys
from datetime import date

import httpx

PRODUCTION = "https://backendfinanceapp-production.up.railway.app"
TAG = "[seed-h4]"

# name, color, typical amount, spread, movements per month
CATEGORIES = [
    ("Comida", "#E07A5F", 220, 90, 9),
    ("Transporte", "#3D405B", 120, 50, 5),
    ("Servicios", "#81B29A", 650, 150, 2),
]
SALARY = 18000


def load_env(path):
    env = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v
    return env


def months_back(n, today):
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("env_file")
    ap.add_argument("--base-url", default=PRODUCTION)
    args = ap.parse_args()
    env = load_env(args.env_file)

    c = httpx.Client(base_url=args.base_url, timeout=60)
    login = c.post("/api/v1/auth/login", json={
        "email": env["EXPOS_TEST_USER_A_EMAIL"], "password": env["EXPOS_TEST_USER_A_PASSWORD"]})
    login.raise_for_status()
    c.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    def ok(r):
        if r.status_code >= 400:
            sys.exit(f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text[:300]}")
        return r.json()

    currencies = {x["code"]: x["id"] for x in ok(c.get("/api/v1/currencies/"))}
    mxn, usd = currencies["MXN"], currencies.get("USD")

    # ── Categories ────────────────────────────────────────────────────────
    existing = {x["name"]: x["id"] for x in ok(c.get("/api/v1/categories/"))}
    cat_ids = {}
    for name, color, *_ in CATEGORIES:
        full = f"{name} {TAG}"
        cat_ids[name] = existing.get(full) or ok(c.post("/api/v1/categories/", json={
            "name": full, "color": color, "icon": "tag", "type": "expense"}))["id"]

    # ── Budget first, so the expenses trigger its alert ───────────────────
    budgets = ok(c.get("/api/v1/budgets/"))
    budgets = budgets if isinstance(budgets, list) else budgets.get("data", [])
    if not any(b.get("category_id") == cat_ids["Comida"] for b in budgets):
        ok(c.post("/api/v1/budgets/", json={
            "category_id": cat_ids["Comida"], "limit_amount": "2000.00",
            "currency_id": mxn, "period": "monthly", "alert_threshold": 80}))

    # ── Movements ─────────────────────────────────────────────────────────
    today = date.today()
    seeded = [e for e in ok(c.get("/api/v1/expenses/", params={"limit": 100}))["data"]
              if (e.get("notes") or "").startswith(TAG)]
    created = 0
    if seeded:
        print(f"movements already seeded ({len(seeded)}+ found); not adding more")
    else:
        rnd = random.Random(2026)
        for y, m in months_back(12, today):
            last = today.day if (y, m) == (today.year, today.month) else calendar.monthrange(y, m)[1]
            ok(c.post("/api/v1/earnings/", json={
                "amount": str(SALARY), "currency_id": mxn, "date": date(y, m, 1).isoformat(),
                "notes": f"{TAG} Sueldo"}))
            created += 1
            for name, _, typical, spread, per_month in CATEGORIES:
                for _ in range(per_month):
                    ok(c.post("/api/v1/expenses/", json={
                        "amount": f"{max(20, typical + rnd.randint(-spread, spread)):.2f}",
                        "currency_id": mxn, "category_id": cat_ids[name],
                        "date": date(y, m, rnd.randint(1, last)).isoformat(),
                        "notes": f"{TAG} {name}"}))
                    created += 1
        if usd:
            ok(c.post("/api/v1/expenses/", json={
                "amount": "25.00", "currency_id": usd, "category_id": cat_ids["Servicios"],
                "date": today.isoformat(), "notes": f"{TAG} Suscripción en dólares"}))
            created += 1
        print(f"movements created: {created}")

    # ── Recurring rule, goal, projected costs ─────────────────────────────
    rules = ok(c.get("/api/v1/recurring/"))
    if not any((r.get("description") or "").startswith(TAG) for r in rules):
        ok(c.post("/api/v1/recurring/", json={
            "type": "expense", "amount": "4500.00", "currency_id": mxn, "frequency": "monthly",
            "day_of_month": 5, "category_id": cat_ids["Servicios"], "description": f"{TAG} Renta"}))

    goals = ok(c.get("/api/v1/goals/"))
    goals = goals if isinstance(goals, list) else goals.get("data", [])
    if not any(TAG in (g.get("name") or "") for g in goals):
        ok(c.post("/api/v1/goals/", json={
            "name": f"Fondo de emergencia {TAG}"[:60], "type": "fixed_amount",
            "target_amount": "20000.00", "currency_id": mxn}))

    projected = ok(c.get("/api/v1/projected/"))
    names = {p.get("name") for p in projected}
    for name, amount, freq, extra, cat in [
        (f"Renta {TAG}", "4500.00", "monthly", {"day_of_month": 5}, "Servicios"),
        (f"Súper {TAG}", "700.00", "weekly", {}, "Comida"),
    ]:
        if name not in names:
            ok(c.post("/api/v1/projected/", json={
                "name": name, "amount": amount, "currency_id": mxn, "frequency": freq,
                "category_id": cat_ids[cat], **extra}))

    print("done")


if __name__ == "__main__":
    main()
