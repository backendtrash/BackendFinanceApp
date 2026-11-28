"""
Screenshots for the user manual (docs/manual-usuario.md), taken in a real
Chromium against the published frontend with a test account.

Usage: python scripts/capturas_manual.py path/to/isolation.env out_dir
Needs: pip install playwright && python -m playwright install chromium
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

FRONT = "https://frontend-finance-app.vercel.app"
SCREENS = [("01-registro", "register", False), ("02-acceso", "login", False),
           ("03-panel", "dashboard", True), ("04-analisis", "analytics", True),
           ("05-vista-semanal", "weeks", True), ("06-gastos", "expenses", True),
           ("07-ingresos", "earnings", True), ("08-presupuestos", "budgets", True),
           ("09-recurrentes", "recurring", True), ("10-plan", "projected", True),
           ("11-metas", "goals", True), ("12-categorias", "categories", True),
           ("13-configuracion", "settings", True), ("14-aviso", "privacidad", False)]

env = dict(l.strip().split("=", 1) for l in open(sys.argv[1], encoding="utf-8")
           if "=" in l and not l.lstrip().startswith("#"))
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    public = browser.new_context(viewport={"width": 1440, "height": 900})
    private = browser.new_context(viewport={"width": 1440, "height": 900})
    page = private.new_page()
    page.goto(f"{FRONT}/login")
    page.fill('input[type="email"]', env["EXPOS_TEST_USER_A_EMAIL"])
    page.fill('input[type="password"]', env["EXPOS_TEST_USER_A_PASSWORD"])
    page.click('button[type="submit"]')
    page.wait_for_url("**/dashboard", timeout=30000)
    anon = public.new_page()
    for name, route, signed_in in SCREENS:
        p = page if signed_in else anon
        p.goto(f"{FRONT}/{route}")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(1200)
        p.screenshot(path=out / f"{name}.png")
        print("ok", name)
    browser.close()
