"""
The five essential charts (design table 6) against the account's own rows.

For a test account and a month, reads every expense and earning through the
API, recomputes each chart's figures from those rows, and prints them next
to what the API returns for the chart, as a Markdown table:

  1. Summary cards       /analytics/dashboard
  2. Spending donut      /analytics/categories
  3. Income vs expenses  /analytics/monthly
  4. Budget progress     /analytics/budget-progress
  5. Weekly cash flow    /analytics/dashboard-weekly

Usage: python scripts/verificar_graficas.py path/to/isolation.env [--year Y --month M]
"""
import argparse
import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

import httpx

PRODUCTION = "https://backendfinanceapp-production.up.railway.app"
D = lambda x: Decimal(str(x)).quantize(Decimal("0.01"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("env_file")
    ap.add_argument("--base-url", default=PRODUCTION)
    ap.add_argument("--year", type=int, default=date.today().year)
    ap.add_argument("--month", type=int, default=date.today().month)
    args = ap.parse_args()
    env = dict(l.strip().split("=", 1) for l in open(args.env_file, encoding="utf-8")
               if "=" in l and not l.lstrip().startswith("#"))
    y, m = args.year, args.month

    c = httpx.Client(base_url=args.base_url, timeout=60)
    tok = c.post("/api/v1/auth/login", json={"email": env["EXPOS_TEST_USER_A_EMAIL"],
                 "password": env["EXPOS_TEST_USER_A_PASSWORD"]}).raise_for_status().json()["access_token"]
    c.headers["Authorization"] = f"Bearer {tok}"
    get = lambda p, **q: c.get(p, params=q).raise_for_status().json()

    def rows(path):
        out, off = [], 0
        while True:
            page = get(path, limit=100, offset=off)["data"]
            out += page
            if len(page) < 100:
                return out
            off += 100

    exp, inc = rows("/api/v1/expenses/"), rows("/api/v1/earnings/")
    first, last = date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
    in_month = lambda r: first <= date.fromisoformat(r["date"]) <= last
    total = lambda rs: sum((D(r["amount_mxn"]) for r in rs), Decimal("0"))
    cats = {x["id"]: x["name"] for x in get("/api/v1/categories/")}

    lines = [f"Cuenta de prueba, {calendar.month_name[m]} {y}. {len(exp)} gastos y {len(inc)} ingresos leídos.\n",
             "| Gráfica | Cifra | Desde las filas | API | |", "|---|---|---|---|---|"]
    bad = 0

    def row(chart, what, mine, api):
        nonlocal bad
        same = D(mine) == D(api)
        bad += not same
        lines.append(f"| {chart} | {what} | {D(mine):,} | {D(api):,} | {'✅' if same else '❌'} |")

    # 1. Summary cards
    dash = get("/api/v1/analytics/dashboard", year=y, month=m)
    e_m, i_m = [r for r in exp if in_month(r)], [r for r in inc if in_month(r)]
    row("1. Tarjetas", "Ingresos del mes", total(i_m), dash["total_income"])
    row("1. Tarjetas", "Gastos del mes", total(e_m), dash["total_expenses"])
    row("1. Tarjetas", "Balance", total(i_m) - total(e_m), dash["net_balance"])
    row("1. Tarjetas", "Proyectado (= /projected/monthly)",
        get("/api/v1/projected/monthly", year=y, month=m)["total_projected_mxn"], dash["projected_monthly"])

    # 2. Donut
    donut = get("/api/v1/analytics/categories", year=y, month=m)
    by_cat = defaultdict(Decimal)
    for r in e_m:
        by_cat[r.get("category_id")] += D(r["amount_mxn"])
    for item in donut["categories"]:
        row("2. Dona", item["category_name"], by_cat[item["category_id"]], item["total_amount"])
    row("2. Dona", "Suma de categorías = gastos del mes", total(e_m), donut["total_expenses"])

    # 3. Income vs expenses, six months
    monthly = get("/api/v1/analytics/monthly", months_back=6)
    for p in monthly["months"]:
        a = date(p["year"], p["month"], 1)
        b = date(p["year"], p["month"], calendar.monthrange(p["year"], p["month"])[1])
        within = lambda r: a <= date.fromisoformat(r["date"]) <= b
        row("3. Ingresos vs gastos", f"{p['month_label']} gastos",
            total([r for r in exp if within(r)]), p["total_expenses"])
        row("3. Ingresos vs gastos", f"{p['month_label']} ingresos",
            total([r for r in inc if within(r)]), p["total_income"])

    # 4. Budget progress (current period)
    for b in get("/api/v1/analytics/budget-progress")["budgets"]:
        scope = [r for r in exp if in_month(r)]
        budget = next(x for x in get("/api/v1/budgets/") if x["id"] == b["budget_id"])
        if budget.get("category_id"):
            scope = [r for r in scope if r.get("category_id") == budget["category_id"]]
        spent = total(scope)
        row("4. Presupuestos", f"{b['category_name']}: gastado", spent, b["spent_amount"])
        row("4. Presupuestos", f"{b['category_name']}: % usado",
            round(spent / D(b["limit_amount"]) * 100, 2), b["pct_spent"])

    # 5. Weekly cash flow
    weekly = get("/api/v1/analytics/dashboard-weekly", year=y, month=m)
    for w in weekly["weeks"]:
        a, b = date.fromisoformat(w["week_start"]), date.fromisoformat(w["week_end"])
        within = lambda r: a <= date.fromisoformat(r["date"]) <= b
        row("5. Flujo semanal", f"{w['week_label']} gastos",
            total([r for r in exp if within(r)]), w["total_expenses"])
    row("5. Flujo semanal", "Suma de semanas proyectadas = mes",
        sum((D(w["projected_weekly"]) for w in weekly["weeks"]), Decimal("0")), weekly["projected_monthly"])

    lines.append(f"\n**{'Todo cuadra' if not bad else f'{bad} diferencias'}**.")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
