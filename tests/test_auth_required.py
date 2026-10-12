"""
Every protected endpoint rejects an unauthenticated request with 401.

This is the evidence for H3 — "at least half the backend modules respond
with authentication". It covers all of them.

The cases are generated from the application's own route table rather than
written out by hand. That is the point: a hand-written list silently stops
covering the API the moment someone adds an endpoint, whereas this cannot
drift. Add a route tomorrow and it is tested tomorrow.

Token *shape* handling is covered separately in test_auth_tokens.py; this
file is only concerned with whether a route is reachable with no token at
all.

A route counts as protected when get_current_user appears anywhere in its
dependency tree. The six that do not are asserted separately below, so that
making an endpoint public is a deliberate act that has to be recorded here
rather than something that can happen by accident.
"""
import pytest
from fastapi.routing import APIRoute

from app.main import app
from app.auth.dependencies import get_current_user


# The only endpoints that may be reached without a token.
#   auth    — you cannot hold a token before logging in
#   health  — Railway polls these, and an unauthenticated probe is the point
PUBLIC = {
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("GET",  "/"),
    ("GET",  "/health"),
    ("GET",  "/scheduler"),
}

# Stand-ins for path parameters. The values only have to survive parsing —
# authentication is refused long before anything looks for these rows.
PATH_VALUES = {
    "week_year":   "2026",
    "week_number": "40",
}
PLACEHOLDER_UUID = "00000000-0000-0000-0000-000000000001"


def _is_protected(dependant) -> bool:
    if getattr(dependant, "call", None) is get_current_user:
        return True
    return any(_is_protected(d) for d in getattr(dependant, "dependencies", []))


def _fill(path: str) -> str:
    out = path
    while "{" in out:
        start = out.index("{")
        end = out.index("}", start)
        name = out[start + 1:end]
        out = out[:start] + PATH_VALUES.get(name, PLACEHOLDER_UUID) + out[end + 1:]
    return out


def _module(path: str) -> str:
    rest = path.replace("/api/v1/", "").lstrip("/")
    return rest.split("/")[0] if rest else "root"


def _collect():
    protected, public = [], []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            entry = (method, route.path, _fill(route.path))
            (protected if _is_protected(route.dependant) else public).append(entry)
    return protected, public


PROTECTED_ROUTES, PUBLIC_ROUTES = _collect()


@pytest.mark.parametrize(
    "method,path,url",
    PROTECTED_ROUTES,
    ids=[f"{_module(p)}::{m} {p}" for m, p, _ in PROTECTED_ROUTES],
)
def test_protected_endpoint_rejects_missing_token(client, method, path, url):
    """No Authorization header at all must be 401, never 403 and never 200."""
    response = client.request(method, url)

    assert response.status_code == 401, (
        f"{method} {path} returned {response.status_code} without a token; "
        f"expected 401. Body: {response.text[:200]}"
    )
    # The frontend keys its refresh logic off this header.
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_public_endpoints_are_exactly_the_expected_set():
    """
    Pins which endpoints are reachable without a token.

    If this fails, an endpoint changed its protection. Either a new public
    route appeared, which needs justifying, or a route that should be public
    was accidentally locked.
    """
    found = {(m, p) for m, p, _ in PUBLIC_ROUTES}
    assert found == PUBLIC, (
        f"unexpectedly public: {sorted(found - PUBLIC)}\n"
        f"no longer public:    {sorted(PUBLIC - found)}"
    )


def test_every_module_has_protected_coverage():
    """
    The report asks for at least one test per module. Rather than trust that
    the parametrised sweep happened to reach them all, assert it.
    """
    expected = {
        "analytics", "auth", "budgets", "categories", "currencies",
        "earnings", "expenses", "goals", "preferences", "projected",
        "recurring",
    }
    covered = {_module(p) for _, p, _ in PROTECTED_ROUTES}
    assert expected <= covered, f"no protected route tested for: {expected - covered}"
