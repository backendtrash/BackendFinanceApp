"""
The test cases of Evidencia 2 (CP-01 to CP-14) that can run through the API,
against production, with the two test accounts (package 4.1).

Each case states its expected result as Evidencia 2 writes it, runs, and
prints what it obtained. Everything a case creates is tagged "[cp]" and
deleted when the case ends, pass or fail. The cases that need a browser, an
email inbox or a phone are listed as manual; they are not run here.

Usage: python scripts/casos_prueba.py path/to/isolation.env [--base-url URL]
"""
import argparse
import time
from datetime import date
from decimal import Decimal

import httpx

PRODUCTION = "https://backendfinanceapp-production.up.railway.app"
TAG = "[cp]"
D = lambda x: Decimal(str(x)).quantize(Decimal("0.01"))


class Fail(Exception):
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
    today = date.today()

    def session(who):
        c = httpx.Client(base_url=args.base_url, timeout=60)
        r = c.post("/api/v1/auth/login", json={"email": env[f"EXPOS_TEST_USER_{who}_EMAIL"],
                   "password": env[f"EXPOS_TEST_USER_{who}_PASSWORD"]}).raise_for_status().json()
        c.headers["Authorization"] = f"Bearer {r['access_token']}"
        return c, r

    a, a_login = session("A")
    b, _ = session("B")
    anon = httpx.Client(base_url=args.base_url, timeout=60)
    currencies = {x["code"]: x for x in a.get("/api/v1/currencies/").json()}
    mxn = currencies["MXN"]["id"]
    cleanup = []          # (client, path) to DELETE when the case ends

    def post(c, path, body, ok=(200, 201)):
        r = c.post(path, json=body)
        expect(r.status_code in ok, f"POST {path}: {r.status_code} {r.text[:150]}")
        return r.json()

    def expense(c, amount, **extra):
        row = post(c, "/api/v1/expenses/", {"amount": str(amount), "currency_id": mxn,
                   "date": today.isoformat(), "notes": f"{TAG} gasto", **extra})
        cleanup.append((c, f"/api/v1/expenses/{row['id']}"))
        return row

    # ── Cases ─────────────────────────────────────────────────────────────

    def cp02():
        r = anon.get("/api/v1/expenses/")
        expect(r.status_code == 401, f"{r.status_code}")
        return "la API responde 401 sin sesión (la redirección de la pantalla es manual)"

    def cp03():
        usd = currencies.get("USD")
        expect(usd and usd.get("rate_updated_at"), "USD has no fetched rate")
        row = expense(a, "100.00", currency_id=usd["id"])
        expected = D(Decimal("100") * Decimal(str(usd["exchange_rate"])))
        expect(D(row["amount"]) == D("100") and D(row["amount_mxn"]) == expected,
               f"{row['amount']} / {row['amount_mxn']} vs {expected}")
        return (f"monto original US$100.00 y equivalente ${row['amount_mxn']} MXN al tipo de cambio "
                f"{usd['exchange_rate']} (actualizado {usd['rate_updated_at'][:10]})")

    def cp04():
        r = a.post("/api/v1/expenses/", json={"amount": "-50", "currency_id": mxn,
                   "date": today.isoformat(), "notes": f"{TAG} negativo"})
        expect(r.status_code == 422, f"{r.status_code}")
        fields = [".".join(map(str, e.get("loc", []))) for e in r.json().get("detail", [])]
        expect(any("amount" in f for f in fields), f"no field named: {fields}")
        return f"422 y el detalle señala el campo `{fields[0]}`"

    def cp05():
        row = expense(b, "321.00")
        r = a.get(f"/api/v1/expenses/{row['id']}")
        expect(r.status_code == 404, f"{r.status_code}")
        expect("321" not in r.text, "B's amount in the answer")
        return "la cuenta A pide un gasto de B por su id: 404, sin ningún dato de B"

    def cp06():
        cat = post(a, "/api/v1/categories/", {"name": f"Con gastos {TAG}", "type": "expense", "color": "#888888"})
        cleanup.append((a, f"/api/v1/categories/{cat['id']}"))
        expense(a, "40.00", category_id=cat["id"])
        r = a.delete(f"/api/v1/categories/{cat['id']}")
        expect(r.status_code == 409, f"{r.status_code}")
        return f"409: \"{str(r.json().get('detail'))[:90]}\""

    def cp07():
        cat = post(a, "/api/v1/categories/", {"name": f"Alimentos {TAG}", "type": "expense", "color": "#77AA33"})
        cleanup.append((a, f"/api/v1/categories/{cat['id']}"))
        budget = post(a, "/api/v1/budgets/", {"category_id": cat["id"], "limit_amount": "5000.00",
                      "currency_id": mxn, "period": "monthly", "alert_threshold": 80})
        cleanup.append((a, f"/api/v1/budgets/{budget['id']}"))
        for amount in ("2000.00", "2100.00"):
            expense(a, amount, category_id=cat["id"])
        alerts = [x for x in a.get(f"/api/v1/budgets/{budget['id']}/alerts").json()]
        expect(alerts, "no alert in the budget's history")
        return f"gastos por $4,100 de $5,000: alerta registrada en el historial al {alerts[0]['pct_spent']}%"

    def cp08_09():
        rule = post(a, "/api/v1/recurring/", {"type": "expense", "amount": "77.00", "currency_id": mxn,
                    "frequency": "monthly", "start_date": today.isoformat(), "description": f"{TAG} regla"})
        cleanup.append((a, f"/api/v1/recurring/{rule['id']}"))
        made = lambda: [e for e in a.get("/api/v1/expenses/", params={"limit": 100}).json()["data"]
                        if e.get("recurring_rule_id") == rule["id"]]
        post(a, "/api/v1/recurring/process", {})
        first = made()
        cleanup.extend((a, f"/api/v1/expenses/{e['id']}") for e in first)
        nxt = a.get(f"/api/v1/recurring/{rule['id']}").json()["next_due_date"]
        expect(len(first) == 1, f"{len(first)} movements after the first run")
        expect(nxt[:7] != today.isoformat()[:7], f"next charge did not move a month: {nxt}")
        post(a, "/api/v1/recurring/process", {})
        second = made()
        cleanup.extend((a, f"/api/v1/expenses/{e['id']}") for e in second if e not in first)
        expect(len(second) == 1, f"{len(second)} movements after the second run")
        return (f"CP-08: 1 movimiento y siguiente cargo el {nxt}. "
                f"CP-09: la segunda corrida no generó ninguno")

    def cp10():
        routes = ["/api/v1/analytics/dashboard", "/api/v1/analytics/monthly", "/api/v1/analytics/categories",
                  "/api/v1/analytics/weekly", "/api/v1/analytics/budget-progress", "/api/v1/analytics/net-worth",
                  "/api/v1/analytics/trends", "/api/v1/analytics/projected"]
        codes = {p.rsplit("/", 1)[1]: b.get(p).status_code for p in routes}
        expect(all(v == 200 for v in codes.values()), f"{codes}")
        expect(D(b.get("/api/v1/analytics/dashboard").json()["total_expenses"]) == 0, "B is not empty")
        return "cuenta sin movimientos (B): las 8 consultas de analítica responden 200 con totales en cero"

    def cp11():
        rows = []
        off = 0
        while True:
            page = a.get("/api/v1/expenses/", params={"limit": 100, "offset": off}).json()["data"]
            rows += page
            off += 100
            if len(page) < 100:
                break
        expect(len(rows) >= 190, f"only {len(rows)} movements")
        y, m = today.year, today.month
        # 20 calls: near the threshold a handful of calls passes or fails by
        # luck. The network alone (/health) is measured the same way, so the
        # result says how much of the time is the server's.
        def timed(path, **params):
            out = []
            for _ in range(20):
                t0 = time.perf_counter()
                r = a.get(path, params=params)
                out.append((time.perf_counter() - t0) * 1000)
            out.sort()
            return sum(out) / len(out), out[17], r

        net, _, _ = timed("/health")
        avg, p90, r = timed("/api/v1/analytics/year-over-year", year=y, month=m)
        mine = sum((D(e["amount_mxn"]) for e in rows if e["date"][:7] == f"{y}-{m:02d}"), Decimal("0"))
        totals_ok = D(r.json()["current"]["expenses"]) == mine
        detail = (f"{len(rows)} gastos en doce meses; comparación anual: media {avg:.0f} ms, p90 {p90:.0f} ms "
                  f"en 20 llamadas (la red sola, {net:.0f} ms); total del mes ${mine:,} "
                  f"{'igual' if totals_ok else 'DISTINTO'} a la suma de las filas")
        expect(totals_ok and avg < 500, detail)
        return detail

    def cp13():
        r = anon.post("/api/v1/auth/refresh", json={"refresh_token": a_login["refresh_token"]})
        expect(r.status_code == 200 and r.json().get("access_token"), f"{r.status_code}")
        c = httpx.Client(base_url=args.base_url, timeout=60,
                         headers={"Authorization": f"Bearer {r.json()['access_token']}"})
        expect(c.get("/api/v1/auth/me").status_code == 200, "new token rejected")
        return "la API entrega un token nuevo con el de renovación y lo acepta (la parte del formulario es manual)"

    cases = [
        ("CP-02", "Sin sesión, la ruta de gastos redirige al acceso y la API responde 401", cp02),
        ("CP-03", "Gasto de 100 dólares: se guarda el monto original y su equivalente en pesos", cp03),
        ("CP-04", "Gasto negativo: 422 con un mensaje que identifica el campo", cp04),
        ("CP-05", "A pide por id un gasto de B: responde como si no existiera", cp05),
        ("CP-06", "Borrar una categoría con gastos: se impide y se explica", cp06),
        ("CP-07", "Presupuesto de $5,000 al 80%, gastos por $4,100: alerta en el historial", cp07),
        ("CP-08 y CP-09", "La regla genera su movimiento y avanza un mes; repetir no genera otro", cp08_09),
        ("CP-10", "Usuario sin movimientos: las gráficas responden vacías, sin error", cp10),
        ("CP-11", "200 movimientos en 12 meses: comparación anual en menos de 500 ms y totales correctos", cp11),
        ("CP-13", "Con el token vencido, se renueva de forma transparente", cp13),
    ]

    print(f"Casos de prueba por la API, {today.strftime('%d/%m/%Y')}, contra {args.base_url}\n")
    print("| Caso | Resultado esperado (Evidencia 2) | Resultado obtenido | Estado |\n|---|---|---|---|")
    for cid, expected, case in cases:
        cleanup.clear()
        try:
            got, state = case(), "✅ Pasa"
        except (Fail, httpx.HTTPError, KeyError, TypeError) as e:
            got, state = f"{type(e).__name__}: {e}", "❌ Falla"
        finally:
            left = [p for c, p in reversed(cleanup) if c.delete(p).status_code not in (200, 204, 404)]
        if left:
            got += f" · no se pudo limpiar: {', '.join(left)}"
        print(f"| {cid} | {expected} | {got} | {state} |")


if __name__ == "__main__":
    main()
