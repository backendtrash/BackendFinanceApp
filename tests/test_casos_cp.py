"""
CP-03, CP-04 and CP-07 of Evidencia 2, in the suite.

Until 28/11 these three cases were covered only by scripts/casos_prueba.py
against production (docs/pruebas/mapeo-casos.md). Here they run on every
pull request, against the fake database, with the expected results as
Evidencia 2 writes them.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.database import bind_db
from app.expenses import service as expenses
from app.expenses.schemas import ExpenseCreate
from app.main import app
from fakes import FakeSupabase

USER = "00000000-0000-0000-0000-000000000001"
MXN = "11111111-1111-1111-1111-111111111111"
USD = "44444444-4444-4444-4444-444444444444"
FOOD = "22222222-2222-2222-2222-222222222222"


def _currencies():
    return [{"id": MXN, "code": "MXN", "exchange_rate": "1"},
            {"id": USD, "code": "USD", "exchange_rate": "19.124116"}]


# ── CP-03 ─────────────────────────────────────────────────────────────────

async def test_cp03_an_expense_in_dollars_keeps_its_amount_and_its_pesos():
    """
    "Registrar un gasto de 100 dólares": the original amount is kept and its
    equivalent in pesos is computed at the rate in force.
    """
    fake = FakeSupabase(expenses=[], budgets=[], currencies=_currencies())
    bind_db(fake)

    row = await expenses.create_expense(USER, ExpenseCreate(
        amount=Decimal("100"), currency_id=USD, date=date.today()))

    assert Decimal(row["amount"]) == Decimal("100")
    assert row["currency_id"] == USD
    assert Decimal(row["amount_mxn"]) == Decimal("1912.41")     # 100 × 19.124116


async def test_cp03_the_rate_is_the_one_in_force_when_the_expense_is_written():
    """A later change of rate does not rewrite an expense already stored."""
    fake = FakeSupabase(expenses=[], budgets=[], currencies=_currencies())
    bind_db(fake)
    await expenses.create_expense(USER, ExpenseCreate(
        amount=Decimal("100"), currency_id=USD, date=date.today()))

    fake.rows("currencies")[1]["exchange_rate"] = "20"

    assert Decimal(fake.rows("expenses")[0]["amount_mxn"]) == Decimal("1912.41")


# ── CP-04 ─────────────────────────────────────────────────────────────────

@pytest.fixture
def signed_in(client):
    async def fake_user():
        bind_db(FakeSupabase(expenses=[], budgets=[], currencies=_currencies()))
        return AuthenticatedUser(user_id=USER, email="a@example.com")
    app.dependency_overrides[get_current_user] = fake_user
    yield client
    app.dependency_overrides.clear()


@pytest.mark.parametrize("amount", ["-50", "0"])
def test_cp04_a_negative_or_zero_amount_is_refused_naming_the_field(signed_in, amount):
    """"Registrar un gasto con monto negativo": 422 with a message naming the field."""
    response = signed_in.post("/api/v1/expenses/", json={
        "amount": amount, "currency_id": MXN, "date": date.today().isoformat()})

    assert response.status_code == 422
    fields = [e["loc"][-1] for e in response.json()["detail"]]
    assert "amount" in fields


# ── CP-07 ─────────────────────────────────────────────────────────────────

def _budget_db():
    today = date.today().replace(day=1).isoformat()
    return FakeSupabase(
        currencies=_currencies(), budget_alerts=[],
        budgets=[{"id": "b-food", "user_id": USER, "category_id": FOOD, "limit_amount": "5000",
                  "currency_id": MXN, "period": "monthly", "alert_threshold": 80,
                  "is_active": True, "created_at": "2026-11-01T00:00:00+00:00"}],
        expenses=[{"id": "e-1", "user_id": USER, "category_id": FOOD, "amount": "2000",
                   "amount_mxn": "2000", "currency_id": MXN, "date": today}],
    )


async def test_cp07_crossing_the_threshold_records_an_alert():
    """
    A $5,000 monthly budget for food with its alert at 80%: expenses that add
    up to $4,100 (82%) leave an alert in the budget's history.
    """
    fake = _budget_db()
    bind_db(fake)

    await expenses.create_expense(USER, ExpenseCreate(
        amount=Decimal("2100"), currency_id=MXN, category_id=FOOD, date=date.today()))

    alerts = fake.rows("budget_alerts")
    assert len(alerts) == 1
    assert alerts[0]["budget_id"] == "b-food"
    assert Decimal(alerts[0]["pct_spent"]) == Decimal("82.00")
    assert Decimal(alerts[0]["amount_spent"]) == Decimal("4100")


async def test_cp07_under_the_threshold_there_is_no_alert():
    fake = _budget_db()
    bind_db(fake)

    await expenses.create_expense(USER, ExpenseCreate(
        amount=Decimal("1999"), currency_id=MXN, category_id=FOOD, date=date.today()))

    assert fake.rows("budget_alerts") == []     # 3,999 of 5,000: 79.98%


async def test_cp07_one_alert_a_day_however_many_expenses_follow():
    fake = _budget_db()
    bind_db(fake)

    for amount in ("2100", "300", "500"):
        await expenses.create_expense(USER, ExpenseCreate(
            amount=Decimal(amount), currency_id=MXN, category_id=FOOD, date=date.today()))

    assert len(fake.rows("budget_alerts")) == 1
