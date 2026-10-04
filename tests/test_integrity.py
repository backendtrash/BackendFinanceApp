"""
The three integrity rules from section 3.3 of the status report.

  RF07  processing the same day twice must not duplicate movements
  RF04  a category with movements must not be deletable
  3.3   the full data reset has to cover every module, not three of them

Each of these was a real gap, so each test here fails against the code as
it was before this change rather than merely describing what it already did.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.categories import service as categories_service
from app.recurring import service as recurring_service
from fakes import FakeSupabase


USER_A = "aaaaaaaa-0000-0000-0000-000000000001"
USER_B = "bbbbbbbb-0000-0000-0000-000000000002"
CURRENCY_MXN = "11111111-1111-1111-1111-111111111111"
CAT_FOOD = "22222222-2222-2222-2222-222222222222"


def _rule(rule_id="rule-1", *, days_overdue=0, frequency="monthly",
          user_id=USER_A, type_="expense", amount="100.00", **extra):
    rule = {
        "id": rule_id,
        "user_id": user_id,
        "type": type_,
        "amount": amount,
        "currency_id": CURRENCY_MXN,
        "category_id": None,
        "description": "Rent",
        "frequency": frequency,
        "start_date": (date.today() - timedelta(days=365)).isoformat(),
        "end_date": None,
        "next_due_date": (date.today() - timedelta(days=days_overdue)).isoformat(),
        "day_of_week": None,
        "day_of_month": None,
        "is_active": True,
    }
    rule.update(extra)
    return rule


def _store(*rules) -> FakeSupabase:
    return FakeSupabase(
        recurring_rules=list(rules),
        currencies=[{"id": CURRENCY_MXN, "exchange_rate": "1", "code": "MXN"}],
        expenses=[],
        earnings=[],
    )


# ── RF07: processing twice must not duplicate ─────────────────────────────

async def test_processing_twice_in_one_day_creates_one_transaction(monkeypatch):
    """
    The headline rule. Run the engine, run it again immediately, and the
    second run must find nothing left to do.
    """
    fake = _store(_rule())
    monkeypatch.setattr(recurring_service, "supabase_admin", fake)

    first = await recurring_service.process_due_rules()
    second = await recurring_service.process_due_rules()

    assert first["created"] == 1
    assert second["created"] == 0, "the second run duplicated the transaction"
    assert len(fake.rows("expenses")) == 1


async def test_a_five_week_backlog_is_drained_in_one_run(monkeypatch):
    """
    calculate_next_due_date advances one interval at a time. Before this
    change the engine applied exactly one per invocation, so a rule five
    weeks overdue stayed overdue and every extra call that day wrote
    another transaction. Now the backlog is drained in one pass and the
    cursor ends in the future.
    """
    fake = _store(_rule(days_overdue=35, frequency="weekly"))
    monkeypatch.setattr(recurring_service, "supabase_admin", fake)

    result = await recurring_service.process_due_rules()

    assert result["created"] == 6, "one per missed week, plus today's"
    assert len({e["date"] for e in fake.rows("expenses")}) == 6, "all distinct dates"

    cursor = date.fromisoformat(fake.rows("recurring_rules")[0]["next_due_date"])
    assert cursor > date.today(), "cursor must end in the future"

    # And a second run the same day finds nothing.
    again = await recurring_service.process_due_rules()
    assert again["created"] == 0


async def test_the_cursor_is_claimed_before_the_transaction_is_written(monkeypatch):
    """
    Order matters more than it looks. Writing first and advancing second
    means a crash in between leaves the transaction committed and the
    cursor unmoved, so the next run writes it again.

    Claiming first inverts that: a crash loses an occurrence instead of
    duplicating one, which for money is the right way to fail.
    """
    fake = _store(_rule())
    monkeypatch.setattr(recurring_service, "supabase_admin", fake)

    await recurring_service.process_due_rules()

    sequence = [
        (q["table"], q["op"]) for q in fake.queries
        if (q["table"] == "recurring_rules" and q["op"] == "update")
        or (q["table"] == "expenses" and q["op"] == "insert")
    ]
    assert sequence.index(("recurring_rules", "update")) < \
           sequence.index(("expenses", "insert")), \
        "the transaction was written before the cursor was claimed"


async def test_the_claim_is_conditional_on_the_value_that_was_read(monkeypatch):
    """
    The claim filters on next_due_date as well as id. That is what makes
    two concurrent runners safe: both read the same value, only one update
    can match it, and the loser gets zero rows back and stops.
    """
    fake = _store(_rule())
    monkeypatch.setattr(recurring_service, "supabase_admin", fake)

    await recurring_service.process_due_rules()

    claims = fake.ops_on("recurring_rules", "update")
    claim = next(c for c in claims if "next_due_date" in c["payload"])
    filtered_columns = {column for _, column, _ in claim["filters"]}

    assert filtered_columns == {"id", "next_due_date"}, (
        "the claim must be conditional on next_due_date, otherwise it "
        "overwrites whatever another runner just wrote"
    )


async def test_a_lost_claim_writes_nothing(monkeypatch):
    """
    Simulates another runner getting there first: the conditional update
    matches no row, so no transaction may be written.
    """
    fake = _store(_rule())
    monkeypatch.setattr(recurring_service, "supabase_admin", fake)

    original_table = fake.table

    def table(name):
        query = original_table(name)
        if name == "recurring_rules":
            real_execute = query.execute

            def execute():
                result = real_execute()
                if query._op == "update" and "next_due_date" in (query._payload or {}):
                    return type(result)([])      # the claim matched nothing
                return result

            query.execute = execute
        return query

    fake.table = table

    result = await recurring_service.process_due_rules()

    assert result["created"] == 0
    assert fake.rows("expenses") == [], "wrote a transaction without claiming it"


async def test_an_inactive_rule_is_never_processed(monkeypatch):
    fake = _store(_rule(is_active=False))
    monkeypatch.setattr(recurring_service, "supabase_admin", fake)

    result = await recurring_service.process_due_rules()
    assert result["created"] == 0


async def test_a_rule_past_its_end_date_is_deactivated_not_processed(monkeypatch):
    fake = _store(_rule(
        days_overdue=10,
        end_date=(date.today() - timedelta(days=5)).isoformat(),
    ))
    monkeypatch.setattr(recurring_service, "supabase_admin", fake)

    result = await recurring_service.process_due_rules()

    assert result["created"] == 0
    assert fake.rows("recurring_rules")[0]["is_active"] is False


async def test_processing_can_be_scoped_to_one_user(monkeypatch):
    """
    POST /process now passes the caller's id. It used to process every
    user's rules, which let any authenticated user drive the whole table's
    scheduling on demand.
    """
    fake = _store(
        _rule("rule-a", user_id=USER_A),
        _rule("rule-b", user_id=USER_B),
    )
    monkeypatch.setattr(recurring_service, "supabase_admin", fake)

    result = await recurring_service.process_due_rules(user_id=USER_A)

    assert result["created"] == 1
    assert {e["user_id"] for e in fake.rows("expenses")} == {USER_A}


async def test_the_scheduler_still_processes_every_user(monkeypatch):
    """Called with no user_id — the nightly job's path — nothing is scoped."""
    fake = _store(
        _rule("rule-a", user_id=USER_A),
        _rule("rule-b", user_id=USER_B),
    )
    monkeypatch.setattr(recurring_service, "supabase_admin", fake)

    result = await recurring_service.process_due_rules()

    assert result["created"] == 2
    assert {e["user_id"] for e in fake.rows("expenses")} == {USER_A, USER_B}


async def test_income_rules_write_to_earnings(monkeypatch):
    fake = _store(_rule(type_="income"))
    monkeypatch.setattr(recurring_service, "supabase_admin", fake)

    await recurring_service.process_due_rules()

    assert len(fake.rows("earnings")) == 1
    assert fake.rows("expenses") == []


# ── RF04: a category in use cannot be deleted ─────────────────────────────

def _categories_store(**referencing) -> FakeSupabase:
    tables = {
        "categories": [{"id": CAT_FOOD, "user_id": USER_A, "name": "Food"}],
        "expenses": [], "earnings": [], "budgets": [],
        "recurring_rules": [], "projected_costs": [], "goals": [],
    }
    tables.update(referencing)
    return FakeSupabase(**tables)


async def test_an_unused_category_can_be_deleted(monkeypatch):
    fake = _categories_store()
    monkeypatch.setattr(categories_service, "supabase_admin", fake)

    assert await categories_service.delete_category(CAT_FOOD, USER_A) is True
    assert fake.rows("categories") == []


@pytest.mark.parametrize(
    "table,column",
    [
        ("expenses", "category_id"),
        ("earnings", "category_id"),
        ("budgets", "category_id"),
        ("recurring_rules", "category_id"),
        ("projected_costs", "category_id"),
        ("goals", "savings_category_id"),
    ],
)
async def test_a_referenced_category_is_refused(monkeypatch, table, column):
    """
    Every table that points at a category must block the delete. goals is
    the one that is easy to miss, because it uses savings_category_id.
    """
    fake = _categories_store(**{
        table: [{"id": "row-1", "user_id": USER_A, column: CAT_FOOD}]
    })
    monkeypatch.setattr(categories_service, "supabase_admin", fake)

    with pytest.raises(categories_service.CategoryInUse) as raised:
        await categories_service.delete_category(CAT_FOOD, USER_A)

    assert raised.value.counts == {table: 1}
    assert fake.rows("categories"), "the category was deleted anyway"


async def test_the_refusal_reports_counts_per_table(monkeypatch):
    """The client needs to tell the user what is in the way, not just that
    something is."""
    fake = _categories_store(
        expenses=[
            {"id": "e1", "user_id": USER_A, "category_id": CAT_FOOD},
            {"id": "e2", "user_id": USER_A, "category_id": CAT_FOOD},
        ],
        budgets=[{"id": "b1", "user_id": USER_A, "category_id": CAT_FOOD}],
    )
    monkeypatch.setattr(categories_service, "supabase_admin", fake)

    with pytest.raises(categories_service.CategoryInUse) as raised:
        await categories_service.delete_category(CAT_FOOD, USER_A)

    assert raised.value.counts == {"expenses": 2, "budgets": 1}


async def test_another_users_rows_do_not_block_the_delete(monkeypatch):
    """
    The reference count is scoped to the owner. Without that, one user's
    expense could block another user's delete — which both leaks the fact
    that the row exists and denies the owner an operation.
    """
    fake = _categories_store(
        expenses=[{"id": "e1", "user_id": USER_B, "category_id": CAT_FOOD}]
    )
    monkeypatch.setattr(categories_service, "supabase_admin", fake)

    assert await categories_service.delete_category(CAT_FOOD, USER_A) is True


async def test_the_delete_endpoint_answers_409(client, monkeypatch):
    """End to end: the exception becomes a 409 carrying the counts."""
    fake = _categories_store(
        expenses=[{"id": "e1", "user_id": USER_A, "category_id": CAT_FOOD}]
    )
    monkeypatch.setattr(categories_service, "supabase_admin", fake)

    async def fake_user():
        from app.auth.dependencies import AuthenticatedUser
        return AuthenticatedUser(user_id=USER_A, email="a@example.com")

    from app.auth.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = fake_user
    try:
        response = client.delete(f"/api/v1/categories/{CAT_FOOD}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["references"] == {"expenses": 1}


# ── 3.3: the full data reset covers every module ──────────────────────────

async def test_every_module_has_a_bulk_delete():
    """
    The report lists five modules missing one. This asserts the route
    exists for all eight, so the Settings screen can actually clear
    everything it offers to clear.
    """
    from fastapi.routing import APIRoute
    from app.main import app

    deletes = {
        route.path for route in app.routes
        if isinstance(route, APIRoute) and "DELETE" in route.methods
    }

    for module in ["expenses", "earnings", "recurring", "budgets",
                   "goals", "projected", "categories", "preferences"]:
        assert f"/api/v1/{module}/" in deletes, f"{module} has no bulk delete"


async def test_bulk_delete_only_touches_the_callers_rows(monkeypatch):
    from app.expenses import service as expenses_service

    fake = FakeSupabase(expenses=[
        {"id": "e1", "user_id": USER_A},
        {"id": "e2", "user_id": USER_A},
        {"id": "e3", "user_id": USER_B},
    ])
    monkeypatch.setattr(expenses_service, "supabase_admin", fake)

    deleted = await expenses_service.delete_all_expenses(USER_A)

    assert deleted == 2
    assert [r["id"] for r in fake.rows("expenses")] == ["e3"]


async def test_wiping_categories_skips_the_ones_still_in_use(monkeypatch):
    """
    A full reset deletes movements first, so by the time categories are
    wiped nothing references them. If something still does, it is reported
    rather than silently deleted — the same reasoning as the 409.
    """
    fake = FakeSupabase(
        categories=[
            {"id": "c1", "user_id": USER_A, "name": "Unused"},
            {"id": "c2", "user_id": USER_A, "name": "Still Used"},
            {"id": "sys", "user_id": None, "name": "System"},
        ],
        expenses=[{"id": "e1", "user_id": USER_A, "category_id": "c2"}],
        earnings=[], budgets=[], recurring_rules=[], projected_costs=[], goals=[],
    )
    monkeypatch.setattr(categories_service, "supabase_admin", fake)

    result = await categories_service.delete_all_categories(USER_A)

    assert result["deleted"] == 1
    assert result["skipped"] == {"Still Used": 1}

    remaining = {c["id"] for c in fake.rows("categories")}
    assert remaining == {"c2", "sys"}, "a system category was deleted"


async def test_resetting_preferences_writes_defaults_rather_than_deleting(monkeypatch):
    from app.preferences import service as preferences_service

    fake = FakeSupabase(user_preferences=[
        {"id": "p1", "user_id": USER_A, "week_start_day": 5},
    ])
    monkeypatch.setattr(preferences_service, "supabase_admin", fake)

    row = await preferences_service.reset_preferences(USER_A)

    assert row["week_start_day"] == 1
    assert len(fake.rows("user_preferences")) == 1, "the row should persist"
    assert fake.rows("user_preferences")[0]["id"] == "p1", "id should be stable"
