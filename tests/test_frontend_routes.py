"""
Every API call the frontend makes has a route here.

Defect 28 was two Settings buttons calling routes the backend never had;
both answered 404 and one did nothing visible. Nothing caught it: the unit
tests know only the backend and the isolation suite knows only the routes
it calls. This test reads the frontend's source, lists every call to the
API (method and path), and checks each against this app's routes.

It also fails a call that would only work through a redirect: FastAPI
answers /expenses with a 307 to /expenses/, and behind Railway's proxy that
redirect points at http://, which a page served over https refuses.

Needs the frontend repository: FRONTEND_DIR points at its root. Without it
the test is skipped, except in CI (EXPOS_REQUIRE_FRONTEND=1), where a
missing checkout fails rather than passing as skipped.
"""
import os
import re
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.routing import APIRoute

from app.main import app

FRONTEND_DIR = os.environ.get("FRONTEND_DIR")
REQUIRED = os.environ.get("EXPOS_REQUIRE_FRONTEND") == "1"

# Calls the frontend can make but never does while a feature is switched
# off. Each names the switch; the exemption lapses when the switch is on.
SWITCHED_OFF = {
    "/api/v1/sinking-funds": ("src/hooks/useQueries.ts", "export const SINKING_FUNDS_ENABLED = false"),
}

CALL = re.compile(
    r"\b(?:apiClient|axios)\s*\.\s*(get|post|put|patch|delete)\s*(?:<[^()]*?>)?\s*\(\s*"
    r"(?:(['\"`])(.*?)\2)?",
    re.S,
)
CONST = re.compile(r"\bconst\s+(\w+)\s*=\s*(['\"`])(/[^'\"`]*)\2")
COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)


def frontend_calls(sources: dict[str, str]) -> tuple[list[tuple], list[str]]:
    """
    (method, path, where) for every API call in the given {file: text}, and
    a list of calls whose path could not be read. Template parameters become
    {param}; query strings are dropped.
    """
    calls, unreadable = [], []
    for name, text in sources.items():
        text = COMMENT.sub("", text)
        consts = {m.group(1): m.group(3) for m in CONST.finditer(text)}
        for m in CALL.finditer(text):
            method, path = m.group(1).upper(), m.group(3)
            where = f"{name}:{text[:m.start()].count(chr(10)) + 1}"
            if path is None:
                unreadable.append(where)
                continue
            path = path.replace("${apiClient.defaults.baseURL}", "")
            path = re.sub(r"\$\{(\w+)\}", lambda v: consts.get(v.group(1), v.group(0)), path)
            path = re.sub(r"\$\{[^}]*\}", "{param}", path).split("?")[0]
            if not path.startswith("/api/"):
                unreadable.append(where)
                continue
            calls.append((method, path, where))
    return calls, unreadable


# A typed path parameter only takes values of its type. "monthly" is not a
# UUID, so /recurring/monthly does not reach /recurring/{rule_id}: the API
# would answer 422. A {param} from a frontend template could be anything,
# so it matches any parameter.
PARAM_VALUE = {
    UUID: r"[0-9a-fA-F-]{36}",
    int:  r"[0-9]+",
}


def _route_patterns() -> list[tuple[str, re.Pattern, str]]:
    patterns = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            types = {p.name: p.field_info.annotation for p in route.dependant.path_params}

            def segment(m):
                value = PARAM_VALUE.get(types.get(m.group(1)), r"[^/{}]+")
                return rf"(?:{value}|\{{param\}})"

            rx = re.compile("^" + re.sub(r"\{(\w+)(?::\w+)?\}", segment, route.path) + "$")
            for method in route.methods:
                patterns.append((method, rx, route.path))
    return patterns


def check(calls: list[tuple]) -> list[str]:
    """Problems with the given calls, against this app's routes."""
    patterns = _route_patterns()

    def served(method, path):
        return any(m == method and rx.match(path) for m, rx, _ in patterns)

    problems = []
    for method, path, where in calls:
        if served(method, path):
            continue
        other = path[:-1] if path.endswith("/") else path + "/"
        if served(method, other):
            problems.append(f"{method} {path} ({where}) only answers through a redirect to {other}")
        else:
            problems.append(f"{method} {path} ({where}) has no route")
    return problems


def _load_frontend() -> dict[str, str]:
    root = Path(FRONTEND_DIR)
    return {
        str(p.relative_to(root)).replace("\\", "/"): p.read_text(encoding="utf-8-sig")
        for p in (root / "src").rglob("*")
        if p.suffix in (".ts", ".tsx")
    }


# ── The checker itself, without the frontend ─────────────────────────────

def test_the_checker_finds_a_missing_route_and_a_redirect():
    calls, unreadable = frontend_calls({"fake.ts": '''
        const BASE = '/api/v1/expenses'
        apiClient.get<Thing[]>(`${BASE}/`)                 // fine
        apiClient.delete(`/api/v1/expenses/${id}`)         // fine
        apiClient.get(
          '/api/v1/no-such-thing')                         // missing
        apiClient.get('/api/v1/expenses')                  // redirect only
        apiClient.post(`${apiClient.defaults.baseURL}/api/v1/auth/refresh`, body)
        apiClient.get('/api/v1/goals/not-a-uuid')          // 422: id is a UUID
        apiClient.get(url)                                 // unreadable
    '''})

    problems = check(calls)

    assert len(calls) == 6 and len(unreadable) == 1
    assert any("no-such-thing" in p and "no route" in p for p in problems)
    assert any("GET /api/v1/expenses " in p and "redirect" in p for p in problems)
    assert any("not-a-uuid" in p for p in problems)
    assert len(problems) == 3


# ── The real frontend ─────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def sources():
    if not FRONTEND_DIR:
        if REQUIRED:
            pytest.fail("EXPOS_REQUIRE_FRONTEND=1 but FRONTEND_DIR is not set")
        pytest.skip("FRONTEND_DIR not set: the frontend checkout is not available")
    found = _load_frontend()
    assert found, f"no .ts/.tsx files under {FRONTEND_DIR}/src"
    return found


def test_every_frontend_call_has_a_route(sources):
    calls, unreadable = frontend_calls(sources)
    assert not unreadable, "API calls whose path the test cannot read:\n  " + "\n  ".join(unreadable)
    assert len(calls) > 50, f"only {len(calls)} calls found; the parser has likely broken"

    live = []
    for method, path, where in calls:
        prefix = next((p for p in SWITCHED_OFF if path.startswith(p)), None)
        if prefix:
            file, switch = SWITCHED_OFF[prefix]
            assert switch in sources[file], (
                f"{path} is exempt only while '{switch}' holds in {file}; it no longer does"
            )
            continue
        live.append((method, path, where))

    problems = check(live)
    assert not problems, "Frontend calls the API does not serve:\n  " + "\n  ".join(problems)
