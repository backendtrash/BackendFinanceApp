"""
The test cases that need the screen (package 4.1) and the two-account
isolation test in the browser (package 4.2), in a real Chromium driven by
Playwright against the published frontend.

  CP-02  without a session, the expenses screen sends you to sign in
  CP-06  deleting a category in use: the screen says why it cannot
  CP-10  an account with no movements: the charts show their empty message
  CP-13  the token expires while a form is open: it is renewed, the form is
         sent and nothing typed is lost (the API answers 401 once to the
         form's request, which is what an expired token looks like)
  CP-14  the eleven screens at a phone's size (emulated, iPhone 13): no
         horizontal overflow. A real phone is still needed to sign it off.
  4.2    the eleven screens with account A and with account B; B's screens
         must not show A's data, which is tagged "[seed-h4]"

Screenshots go to the directory given. What a case creates through the API is
tagged "[cp-ui]" and deleted at the end. CP-01 (sign-up with a real email)
stays manual.

Usage: python scripts/pruebas_navegador.py path/to/isolation.env out_dir
Needs: pip install playwright && python -m playwright install chromium
"""
import sys
from datetime import date
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

FRONT = "https://frontend-finance-app.vercel.app"
API = "https://backendfinanceapp-production.up.railway.app"
SCREENS = ["dashboard", "expenses", "earnings", "weeks", "budgets", "recurring",
           "projected", "goals", "categories", "analytics", "settings"]
A_TAG, TAG = "[seed-h4]", "[cp-ui]"

env = dict(l.strip().split("=", 1) for l in open(sys.argv[1], encoding="utf-8")
           if "=" in l and not l.lstrip().startswith("#"))
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
creds = {w: (env[f"EXPOS_TEST_USER_{w}_EMAIL"], env[f"EXPOS_TEST_USER_{w}_PASSWORD"]) for w in "AB"}
results = []


def record(case, expected, got, ok, evidence):
    results.append((case, expected, got, "✅ Pasa" if ok else "❌ Falla", evidence))


def api(who):
    c = httpx.Client(base_url=API, timeout=60)
    email, pw = creds[who]
    c.headers["Authorization"] = "Bearer " + c.post("/api/v1/auth/login", json={
        "email": email, "password": pw}).raise_for_status().json()["access_token"]
    return c


def sign_in(page, who):
    email, pw = creds[who]
    page.goto(f"{FRONT}/login")
    page.fill('input[type="email"]', email)
    page.fill('input[type="password"]', pw)
    page.click('button[type="submit"]')
    page.wait_for_url("**/dashboard", timeout=30000)
    page.wait_for_load_state("networkidle")


def visit(page, screen):
    page.goto(f"{FRONT}/{screen}")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(800)


with sync_playwright() as pw:
    browser = pw.chromium.launch()

    # ── CP-02 ─────────────────────────────────────────────────────────────
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(f"{FRONT}/expenses")
    page.wait_for_load_state("networkidle")
    ok = "/login" in page.url
    page.screenshot(path=OUT / "cp02-sin-sesion.png")
    record("CP-02 (pantalla)", "Sin sesión, la dirección de gastos lleva a la pantalla de acceso",
           f"/expenses terminó en {page.url.replace(FRONT, '')}", ok, "cp02-sin-sesion.png")
    ctx.close()

    # ── CP-10 (account B, no movements) ───────────────────────────────────
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    sign_in(page, "B")
    seen = []
    for screen in ("dashboard", "analytics"):
        visit(page, screen)
        page.screenshot(path=OUT / f"cp10-vacio-{screen}.png", full_page=True)
        text = page.inner_text("body")
        seen += [m for m in ("No expenses this month", "No data available", "No projection data available")
                 if m in text]
    ok = bool(seen) and not errors
    record("CP-10 (pantalla)", "Con la cuenta B, las gráficas muestran su mensaje de vacío, sin error",
           f"mensajes: {sorted(set(seen))}; errores de la página: {len(errors)}", ok,
           "cp10-vacio-dashboard.png, cp10-vacio-analytics.png")

    # ── 4.2: the eleven screens, A and B ──────────────────────────────────
    leaks, a_shows = [], []
    for who, c in (("A", browser.new_context(viewport={"width": 1440, "height": 900})), ("B", ctx)):
        p = c.new_page()
        if who == "A":
            sign_in(p, "A")
        for screen in SCREENS:
            visit(p, screen)
            p.screenshot(path=OUT / f"aislamiento-{who}-{screen}.png", full_page=True)
            has_a = A_TAG in p.inner_text("body")
            if who == "A" and has_a:
                a_shows.append(screen)
            if who == "B" and has_a:
                leaks.append(screen)
        c.close()
    record("4.2 Aislamiento en el navegador",
           "En las once pantallas, B no ve ningún dato de A",
           f"A ve sus datos en {len(a_shows)} pantallas ({', '.join(a_shows)}); "
           f"B ve datos de A en {len(leaks)}" + (f": {', '.join(leaks)}" if leaks else ""),
           not leaks and len(a_shows) >= 5, "aislamiento-A-*.png, aislamiento-B-*.png (22 capturas)")

    # ── CP-06 (account A) ─────────────────────────────────────────────────
    a = api("A")
    mxn = next(x["id"] for x in a.get("/api/v1/currencies/").json() if x["code"] == "MXN")
    cat = a.post("/api/v1/categories/", json={"name": f"En uso {TAG}", "type": "expense",
                 "color": "#AA5500"}).json()
    exp = a.post("/api/v1/expenses/", json={"amount": "12.00", "currency_id": mxn, "category_id": cat["id"],
                 "date": date.today().isoformat(), "notes": f"{TAG} gasto"}).json()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page_errors = []
    page.on("pageerror", lambda e: page_errors.append(str(e)))
    page.on("dialog", lambda d: d.accept())
    try:
        sign_in(page, "A")
        visit(page, "categories")
        # The list is rendered twice (desktop and mobile layouts); click the
        # copy that is on screen.
        buttons = page.locator(
            f"xpath=//p[normalize-space()='En uso {TAG}']/ancestor::div[.//button][1]//button[normalize-space()='✕']")
        next(b for b in buttons.all() if b.is_visible()).click()
        page.wait_for_timeout(2500)
        page.screenshot(path=OUT / "cp06-borrar-categoria-en-uso.png", full_page=True)
        text = page.inner_text("body").lower()
        explained = any(w in text for w in ("still has movements", "movimientos", "reassign", "in use", "cannot"))
        still = any(x["id"] == cat["id"] for x in a.get("/api/v1/categories/").json())
        record("CP-06 (pantalla)", "Al borrar una categoría en uso, se impide y la pantalla explica por qué",
               f"la categoría sigue: {still}; la pantalla explica el motivo: {explained}"
               + (f"; error no manejado en la página: {page_errors[0][:80]}" if page_errors else ""),
               still and explained, "cp06-borrar-categoria-en-uso.png")
    finally:
        a.delete(f"/api/v1/expenses/{exp['id']}")
        a.delete(f"/api/v1/categories/{cat['id']}")

    # ── CP-13: token expires while a form is open ─────────────────────────
    visit(page, "categories")
    state = {"failed": 0, "refreshed": 0}

    def expire_once(route):
        if route.request.method == "POST" and state["failed"] == 0:
            state["failed"] += 1
            route.fulfill(status=401, content_type="application/json",
                          body='{"detail": "Token has expired"}')
        else:
            route.continue_()

    page.route("**/api/v1/categories/", expire_once)
    page.on("request", lambda r: state.__setitem__("refreshed", state["refreshed"] + 1)
            if r.url.endswith("/api/v1/auth/refresh") else None)
    name = f"Formulario {TAG}"
    page.get_by_role("button", name="New Category").first.click()
    page.fill('input[placeholder="e.g. Gym, Coffee, Side project..."]', name)
    page.get_by_role("button", name="Create Category").click()
    page.wait_for_timeout(4000)
    page.screenshot(path=OUT / "cp13-token-vencido.png", full_page=True)
    created = [x for x in a.get("/api/v1/categories/").json() if x["name"] == name]
    record("CP-13 (formulario)", "Con el token vencido, se renueva y el formulario se envía sin perder datos",
           f"401 simulado: {state['failed']}; renovaciones del token: {state['refreshed']}; "
           f"categoría guardada con el nombre escrito: {bool(created)}",
           state["failed"] == 1 and state["refreshed"] >= 1 and len(created) == 1, "cp13-token-vencido.png")
    for x in created:
        a.delete(f"/api/v1/categories/{x['id']}")
    ctx.close()

    # ── CP-14: phone size, emulated ───────────────────────────────────────
    ctx = browser.new_context(**pw.devices["iPhone 13"])
    page = ctx.new_page()
    sign_in(page, "A")
    overflow = []
    for screen in SCREENS:
        visit(page, screen)
        page.screenshot(path=OUT / f"cp14-movil-{screen}.png", full_page=True)
        if page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
            overflow.append(screen)
    record("CP-14 (emulado)", "Las once pantallas en un teléfono, legibles y sin desbordamiento horizontal",
           f"tamaño de iPhone 13 (390×844), emulado: desbordan {len(overflow)}"
           + (f" ({', '.join(overflow)})" if overflow else ""), not overflow, "cp14-movil-*.png (11 capturas)")
    ctx.close()
    browser.close()

print(f"Pruebas en el navegador, {date.today().strftime('%d/%m/%Y')}, contra {FRONT}\n")
print("| Caso | Resultado esperado | Resultado obtenido | Estado | Evidencia |\n|---|---|---|---|---|")
for r in results:
    print("| " + " | ".join(r) + " |")
