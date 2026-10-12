"""
Shared test fixtures.

Two things have to happen before app.main can be imported at all, and both
are the reason this file exists rather than a plain fixture module.

1. Settings are validated at import time. app/config.py declares the four
   SUPABASE_* variables as required, and app/auth/dependencies.py builds
   JWKS_URL from the URL while the module is still being imported. Missing
   any of them is an immediate ValidationError, not a test failure.

2. The Supabase client checks the *shape* of its key in its constructor and
   raises SupabaseException("Invalid API key") on anything that is not three
   dot-separated base64url segments. A placeholder like "test" does not get
   past it, so the dummy keys below are JWT-shaped on purpose.

Neither value is a real credential and nothing here reaches the network.
"""
import os

# Must run before the first `import app.*` anywhere in the test session.
os.environ.setdefault("SUPABASE_URL", "https://test-project.supabase.co")
os.environ.setdefault(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYW5vbiJ9.test-signature",
)
os.environ.setdefault(
    "SUPABASE_SERVICE_ROLE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.test-signature",
)
os.environ.setdefault("DEBUG", "False")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    """
    A TestClient that deliberately does NOT run the application lifespan.

    Starlette only runs startup and shutdown when TestClient is used as a
    context manager. That matters here: the lifespan in app/main.py starts
    APScheduler and then immediately calls process_due_rules(), which would
    reach for a real Supabase project on the first test and write
    transactions if it ever found one.

    Routing, dependency resolution and middleware all work without it, which
    is everything these tests need.
    """
    return TestClient(app)


@pytest.fixture(scope="session")
def raw_client() -> TestClient:
    """
    Same app, but server exceptions are returned as 500 responses instead of
    being re-raised into the test.

    Needed to observe what a real client would receive when a handler raises
    something it did not catch. With the default TestClient the exception
    propagates and the status code is never produced.
    """
    return TestClient(app, raise_server_exceptions=False)
