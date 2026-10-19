"""
Defect 15: Settings -> "Delete account" called DELETE /api/v1/auth/account,
a route that did not exist, so the button always failed.
"""
import pytest
from gotrue.errors import AuthApiError

from app.auth import router as auth_router
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.main import app

USER = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def signed_in(client):
    async def fake_user():
        return AuthenticatedUser(user_id=USER, email="a@example.com")
    app.dependency_overrides[get_current_user] = fake_user
    yield client
    app.dependency_overrides.clear()


def test_deleting_your_account_removes_your_auth_user(signed_in, monkeypatch):
    deleted = []
    monkeypatch.setattr(auth_router, "delete_auth_user", deleted.append)

    response = signed_in.delete("/api/v1/auth/account")

    assert response.status_code == 204
    assert deleted == [USER], "must delete exactly the caller's own user"


def test_the_route_takes_no_user_id_from_the_request(signed_in, monkeypatch):
    """
    The id comes only from the verified token. Anything a client sends is
    ignored, so no request can name someone else's account.
    """
    deleted = []
    monkeypatch.setattr(auth_router, "delete_auth_user", deleted.append)

    signed_in.request(
        "DELETE", "/api/v1/auth/account?user_id=someone-else",
        json={"user_id": "someone-else"},
    )

    assert deleted == [USER]


def test_a_supabase_failure_is_reported_not_swallowed(signed_in, monkeypatch):
    def fail(user_id):
        raise AuthApiError("upstream refused", 500, None)
    monkeypatch.setattr(auth_router, "delete_auth_user", fail)

    response = signed_in.delete("/api/v1/auth/account")

    assert response.status_code == 502
    assert "Nothing was removed" in response.json()["detail"]
