"""
A stand-in for the Supabase client, good enough for the analytics layer.

Worth stating why this is possible at all: there is not a single .rpc() call
anywhere in app/analytics/service.py. Every figure the dashboard shows is a
plain .select() followed by arithmetic in Python. So the whole module can be
tested by handing it rows and checking the numbers, with no database and no
assertions about SQL.

The stub applies eq / gte / lte / lt / gt / in_ filters for real rather than
ignoring them. That matters: some of the behaviour under test is about which
rows a query does and does not pull back, and a stub that returned
everything regardless would hide exactly the bugs worth finding.
"""
from __future__ import annotations

from typing import Any


class FakeResult:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, table: str, store: dict[str, list[dict]], log: list) -> None:
        self._table = table
        self._store = store
        self._log = log
        self._filters: list[tuple] = []
        self._single = False
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    # ── builder surface ───────────────────────────────────────────────────
    # Each of these returns self so the real chained call style works.

    def select(self, *_args, **_kwargs) -> "FakeQuery":
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(("eq", column, value))
        return self

    def neq(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(("neq", column, value))
        return self

    def gte(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(("gte", column, value))
        return self

    def lte(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(("lte", column, value))
        return self

    def gt(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(("gt", column, value))
        return self

    def lt(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(("lt", column, value))
        return self

    def in_(self, column: str, values: list) -> "FakeQuery":
        self._filters.append(("in", column, values))
        return self

    def is_(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append(("is", column, value))
        return self

    def or_(self, _expression: str) -> "FakeQuery":
        # Only used outside analytics; accepted so the chain does not break.
        return self

    def order(self, column: str, desc: bool = False, **_kwargs) -> "FakeQuery":
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> "FakeQuery":
        self._limit = count
        return self

    def single(self) -> "FakeQuery":
        self._single = True
        return self

    # ── execution ─────────────────────────────────────────────────────────

    def _matches(self, row: dict) -> bool:
        for kind, column, value in self._filters:
            actual = row.get(column)
            if kind == "eq" and actual != value:
                return False
            if kind == "neq" and actual == value:
                return False
            if kind == "in" and actual not in value:
                return False
            if kind == "is":
                wants_null = value is None or str(value).lower() == "null"
                if wants_null != (actual is None):
                    return False
            if kind in ("gte", "lte", "gt", "lt"):
                if actual is None:
                    return False
                a, b = str(actual), str(value)
                if kind == "gte" and not a >= b:
                    return False
                if kind == "lte" and not a <= b:
                    return False
                if kind == "gt" and not a > b:
                    return False
                if kind == "lt" and not a < b:
                    return False
        return True

    def execute(self) -> FakeResult:
        rows = [dict(r) for r in self._store.get(self._table, []) if self._matches(r)]

        if self._order:
            column, desc = self._order
            rows.sort(key=lambda r: (r.get(column) is None, r.get(column)), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]

        self._log.append({"table": self._table, "filters": list(self._filters)})

        if self._single:
            return FakeResult(rows[0] if rows else None)
        return FakeResult(rows)


class FakeSupabase:
    """
    Hand it a dict of {table_name: [row, ...]} and it answers queries from
    that. `queries` records what was asked, so a test can assert on the shape
    of a query as well as on its result.
    """

    def __init__(self, **tables: list[dict]) -> None:
        self.store: dict[str, list[dict]] = dict(tables)
        self.queries: list[dict] = []

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(name, self.store, self.queries)

    def filters_for(self, table: str) -> list[list[tuple]]:
        return [q["filters"] for q in self.queries if q["table"] == table]
