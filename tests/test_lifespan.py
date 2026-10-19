"""
With SCHEDULER_ENABLED=false the application starts without the scheduler
and without the startup catch-up — what the isolation workflow relies on
when it starts the API only to test it.
"""
from fastapi.testclient import TestClient

from app import scheduler as scheduler_module
from app.config import settings
from app.main import app


def test_disabled_scheduler_starts_nothing(monkeypatch):
    catchups = []

    async def fake_catchup():
        catchups.append(True)
        return {"created": 0}

    monkeypatch.setattr(settings, "scheduler_enabled", False)
    monkeypatch.setattr(scheduler_module, "run_startup_catchup", fake_catchup)

    # The context manager runs the real lifespan, startup and shutdown.
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert not scheduler_module.scheduler.running
        assert client.get("/scheduler").json() == {"running": False, "jobs": []}

    assert catchups == [], "the startup catch-up ran with the scheduler disabled"
