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

from postgrest.exceptions import APIError


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
        # Writes are declared before their filters (.update(...).eq(...)),
        # so the operation is recorded here and applied at execute().
        self._op = "select"
        self._payload: Any = None

    # ── builder surface ───────────────────────────────────────────────────
    # Each of these returns self so the real chained call style works.

    def select(self, *_args, **_kwargs) -> "FakeQuery":
        return self

    def insert(self, payload: Any) -> "FakeQuery":
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict) -> "FakeQuery":
        self._op = "update"
        self._payload = payload
        return self

    def upsert(self, payload: dict, on_conflict: str | None = None) -> "FakeQuery":
        self._op = "upsert"
        self._payload = payload
        self._conflict = on_conflict
        return self

    def delete(self) -> "FakeQuery":
        self._op = "delete"
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
        self._single = "single"
        return self

    def maybe_single(self) -> "FakeQuery":
        self._single = "maybe"
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
        table = self._store.setdefault(self._table, [])
        self._log.append({
            "table": self._table,
            "op": self._op,
            "filters": list(self._filters),
            "payload": self._payload,
        })

        if self._op == "insert":
            incoming = (
                self._payload if isinstance(self._payload, list) else [self._payload]
            )
            written = []
            for row in incoming:
                row = dict(row)
                row.setdefault("id", f"{self._table}-{len(table) + len(written) + 1}")
                written.append(row)
            table.extend(written)
            return FakeResult(written)

        if self._op == "upsert":
            row = dict(self._payload)
            key = getattr(self, "_conflict", None)
            if key:
                for existing in table:
                    if existing.get(key) == row.get(key):
                        existing.update(row)
                        return FakeResult([dict(existing)])
            row.setdefault("id", f"{self._table}-{len(table) + 1}")
            table.append(row)
            return FakeResult([dict(row)])

        if self._op == "update":
            touched = []
            for existing in table:
                if self._matches(existing):
                    existing.update(self._payload)
                    touched.append(dict(existing))
            # Postgrest returns the affected rows; an empty list is how a
            # conditional update reports that it matched nothing.
            return FakeResult(touched)

        if self._op == "delete":
            removed = [dict(r) for r in table if self._matches(r)]
            self._store[self._table] = [r for r in table if not self._matches(r)]
            return FakeResult(removed)

        rows = [dict(r) for r in table if self._matches(r)]

        if self._order:
            column, desc = self._order
            rows.sort(key=lambda r: (r.get(column) is None, r.get(column)), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]

        # Mirrors postgrest-py exactly, because the difference is where bugs
        # hide. .single() demands exactly one row and RAISES otherwise — it
        # does not return None. An earlier version of this stub returned None,
        # which made the stub kinder than the database: every service that
        # used .single() for a lookup that can legitimately miss looked fine
        # here and returned 500 against real Supabase (defects 18-20).
        # .maybe_single() returns None from execute() itself when there is no
        # row — not a result whose .data is None.
        if self._single == "maybe" and not rows:
            return None
        if self._single:
            if len(rows) != 1:
                raise APIError({
                    "code": "PGRST116",
                    "message": "JSON object requested, multiple (or no) rows returned",
                    "details": f"The result contains {len(rows)} rows",
                    "hint": None,
                })
            return FakeResult(rows[0])
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

    def ops_on(self, table: str, op: str) -> list[dict]:
        return [
            q for q in self.queries
            if q["table"] == table and q["op"] == op
        ]

    def rows(self, table: str) -> list[dict]:
        return self.store.get(table, [])
