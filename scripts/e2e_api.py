"""
The main user flows, end to end, through the API (package 3.5).

Signs in as a test account and walks each flow the way the frontend does,
checking the result at every step. Everything a flow creates is tagged
"[e2e]" and deleted when it ends, pass or fail. Prints one Markdown row per
flow: result, what was checked, and the date.

A flow that cannot be checked yet says so as PENDIENTE, with the reason;
it never passes by default. Sign-up with email confirmation, deleting an
account and the PDF report are browser flows and are not here.

Usage: python scripts/e2e_api.py path/to/isolation.env [--base-url URL]
"""
import argparse
import calendar
from datetime import date
from decimal import Decimal

import httpx

PRODUCTION = "https://backendfinanceapp-production.up.railway.app"
TAG = "[e2e]"
D = lambda x: Decimal(str(x)).quantize(Decimal("0.01"))


class Fail(Exception):
    pass


class Pending(Exception):
    pass


def expect(cond, msg):
    if not cond:
        raise Fail(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("env_file")
    ap.add_argument("--base-url", default=PRODUCTION)
    args = ap.parse_args()
    env = dict(l.strip().split("=", 1) for l in open(args.env_file, encoding="utf-8")
               if "=" in l and not l.lstrip().startswith("#"))

    c = httpx.Client(base_url=args.base_url, timeout=60)
    tok = c.post("/api/v1/auth/login", json={"email": env["EXPOS_TEST_USER_A_EMAIL"],
                 "password": env["EXPOS_TEST_USER_A_PASSWORD"]}).raise_for_status().json()["access_token"]
    c.headers["Authorization"] = f"Bearer {tok}"
    today = date.today()
    currencies = {x["code"]: x for x in c.get("/api/v1/currencies/").json()}
    mxn = currencies["MXN"]["id"]
    cleanup = []          # (path) to DELETE when the flow ends

    def post(path, body, status=(200, 201)):
        r = c.post(path, json=body)
        expect(r.status_code in status, f"POST {path}: {r.status_code} {r.text[:150]}")
        return r.json()

    def move(kind, amount, **extra):
        body = {"amount": str(amount), "currency_id": mxn, "date": today.isoformat(),
                "notes": f"{TAG} {kind}", **extra}
        row = post(f"/api/v1/{kind}/", body)
        cleanup.append(f"/api/v1/{kind}/{row['id']}")
        return row

    # ── Flows ─────────────────────────────────────────────────────────────

    def crud(kind):
        row = move(kind, "123.45")
        expect(D(c.get(f"/api/v1/{kind}/{row['id']}").json()["amount_mxn"]) == D("123.45"), "read back")
        r = c.patch(f"/api/v1/{kind}/{row['id']}", json={"amount": "200.00"})
        expect(r.status_code == 200 and D(r.json()["amount"]) == D("200"), f"edit: {r.status_code}")
        expect(c.delete(f"/api/v1/{kind}/{row['id']}").status_code in (200, 204), "delete")
        expect(c.get(f"/api/v1/{kind}/{row['id']}").status_code == 404, "deleted row answers 404")
        return "alta, lectura, edición del monto, borrado y 404 después"

    def import_json():
        rows = [{"amount": str(10 + i), "currency_id": mxn, "date": today.isoformat(),
                 "notes": f"{TAG} import {i}"} for i in range(3)]
        result = post("/api/v1/expenses/import", rows)
        expect(result.get("created") == 3, f"created {result.get('created')} of 3")
        found = [e for e in c.get("/api/v1/expenses/", params={"limit": 100}).json()["data"]
                 if (e.get("notes") or "").startswith(f"{TAG} import")]
        cleanup.extend(f"/api/v1/expenses/{e['id']}" for e in found)
        expect(len(found) == 3, f"{len(found)} imported rows found")
        return "3 gastos importados en un lote y encontrados en el listado"

    def budget_alert():
        # Cleanup runs in reverse: the budget goes before its category, which
        # the API (rightly) refuses to delete while a budget points at it.
        cat = post("/api/v1/categories/", {"name": f"Alerta {TAG}", "type": "expense", "color": "#AA3333"})
        cleanup.append(f"/api/v1/categories/{cat['id']}")
        budget = post("/api/v1/budgets/", {"category_id": cat["id"], "limit_amount": "100.00",
                      "currency_id": mxn, "period": "monthly", "alert_threshold": 80})
        cleanup.append(f"/api/v1/budgets/{budget['id']}")
        move("expenses", "90.00", category_id=cat["id"])
        alerts = [a for a in c.get("/api/v1/budgets/alerts").json() if a["budget_id"] == budget["id"]]
        expect(alerts, "no alert after spending 90% of the budget")
        return f"presupuesto de $100 al 80%: gasto de $90 → alerta al {alerts[0]['pct_spent']}%"

    def recurring():
        rule = post("/api/v1/recurring/", {"type": "expense", "amount": "77.00", "currency_id": mxn,
                    "frequency": "weekly", "start_date": today.isoformat(), "description": f"{TAG} regla"})
        cleanup.append(f"/api/v1/recurring/{rule['id']}")
        expect(rule["next_due_date"] == today.isoformat(), f"next due {rule['next_due_date']}")
        first = post("/api/v1/recurring/process", {})
        mine = [t for t in first["transactions"] if str(t.get("recurring_rule_id")) == rule["id"]
                or t.get("rule_id") == rule["id"]]
        made = [e for e in c.get("/api/v1/expenses/", params={"limit": 100}).json()["data"]
                if e.get("recurring_rule_id") == rule["id"]]
        cleanup.extend(f"/api/v1/expenses/{e['id']}" for e in made)
        expect(len(made) == 1, f"{len(made)} movements from the rule after the first run")
        second = post("/api/v1/recurring/process", {})
        again = [e for e in c.get("/api/v1/expenses/", params={"limit": 100}).json()["data"]
                 if e.get("recurring_rule_id") == rule["id"]]
        expect(len(again) == 1, f"second run left {len(again)} movements: not idempotent")
        after = c.get(f"/api/v1/recurring/{rule['id']}").json()["next_due_date"]
        expect(after > today.isoformat(), f"next due did not advance: {after}")
        return (f"regla con cargo hoy: 1 movimiento y siguiente cargo {after}; "
                f"segunda corrida, ninguno nuevo (CP-08 y CP-09)")

    def goal():
        # start_amount, as the frontend sends it: money saved before the goal.
        # The goal gets its own new savings category, so nothing else counts.
        g = post("/api/v1/goals/", {"name": f"Meta {TAG}", "type": "fixed_amount", "target_amount": "1000.00",
                 "currency_id": mxn, "start_amount": "250.00"})
        cleanup.append(f"/api/v1/goals/{g['id']}")
        got = c.get(f"/api/v1/goals/{g['id']}").json()
        expect(D(got.get("current_savings") or 0) == D("250"), f"saved {got.get('current_savings')}, expected 250")
        expect(D(got.get("pct_complete") or 0) == D("25"), f"progress {got.get('pct_complete')}%, expected 25%")
        return "meta de $1,000 con $250 iniciales: $250 ahorrados, avance del 25%"

    def projected_vs_real():
        p = c.get("/api/v1/analytics/projected").json()
        expect(D(p["total_variance"]) == D(p["total_real"]) - D(p["total_projected"]), "variance")
        expect("projected_future" in p, "projected_future missing")
        return (f"a la fecha ${D(p['total_projected']):,} proyectado contra ${D(p['total_real']):,} real; "
                f"futuro aparte ${D(p['projected_future']):,}")

    def dashboard():
        d = c.get("/api/v1/analytics/dashboard").json()
        expect(D(d["net_balance"]) == D(d["total_income"]) - D(d["total_expenses"]), "net balance")
        card = c.get("/api/v1/projected/monthly", params={"year": today.year, "month": today.month}).json()
        expect(D(d["projected_monthly"]) == D(card["total_projected_mxn"]), "card vs projection")
        return (f"ingresos ${D(d['total_income']):,}, gastos ${D(d['total_expenses']):,}, "
                f"proyectado ${D(d['projected_monthly']):,} = /projected/monthly")

    def usd():
        cur = currencies.get("USD")
        if not cur:
            raise Pending("no existe USD en el catálogo (defecto 36)")
        if not cur.get("rate_updated_at"):
            raise Pending("el tipo de cambio de USD aún no se ha consultado (defecto 36)")
        row = move("expenses", "100.00", currency_id=cur["id"])
        expected = D(Decimal("100") * Decimal(str(cur["exchange_rate"])))
        expect(D(row["amount_mxn"]) == expected, f"{row['amount_mxn']} vs {expected}")
        return f"gasto de US$100 → ${row['amount_mxn']} MXN al tipo de cambio {cur['exchange_rate']} (CP-03)"

    def export():
        r = c.get("/api/v1/export")
        expect(r.status_code == 200 and "attachment" in r.headers.get("content-disposition", ""), "download")
        listed = c.get("/api/v1/expenses/", params={"limit": 1}).json()["total"]
        expect(r.json()["counts"]["expenses"] == listed, f"{r.json()['counts']['expenses']} vs {listed}")
        return f"archivo descargable con {listed} gastos, igual que el listado"

    def recurring_month():
        last = calendar.monthrange(today.year, today.month)[1]
        r = c.get("/api/v1/recurring/monthly", params={"year": today.year, "month": today.month})
        expect(r.status_code == 200, f"{r.status_code}")
        return f"lo que cobran las reglas en el mes: ${D(r.json()['expense_total']):,} (defecto 30; {last} días)"

    flows = [
        ("Gastos: alta, edición y borrado", lambda: crud("expenses")),
        ("Ingresos: alta, edición y borrado", lambda: crud("earnings")),
        ("Importación de gastos", import_json),
        ("Presupuesto con alerta al pasar el umbral", budget_alert),
        ("Regla recurrente que genera su movimiento", recurring),
        ("Meta de ahorro con avance", goal),
        ("Costo proyectado contra gasto real", projected_vs_real),
        ("Panel principal", dashboard),
        ("Movimiento en dólares", usd),
        ("Exportación de datos", export),
        ("Recurrentes del mes", recurring_month),
    ]

    print(f"Flujos de extremo a extremo por la API, {today.strftime('%d/%m/%Y')}, contra {args.base_url}\n")
    print("| Flujo | Resultado | Qué se comprobó |\n|---|---|---|")
    for name, flow in flows:
        cleanup.clear()
        try:
            detail, result = flow(), "✅ Pasa"
        except Pending as e:
            detail, result = str(e), "⏳ Pendiente"
        except (Fail, httpx.HTTPError, KeyError) as e:
            detail, result = f"{type(e).__name__}: {e}", "❌ Falla"
        finally:
            left = [p for p in reversed(cleanup) if c.delete(p).status_code not in (200, 204, 404)]
        if left:
            detail += f" · no se pudo limpiar: {', '.join(left)}"
        print(f"| {name} | {result} | {detail} |")


if __name__ == "__main__":
    main()
