"""Shared pytest fixtures.

Every test gets an isolated data directory, its own SQLite database and its own
application instance, so tests never interfere with each other or with a
developer's real ``data/`` directory.
"""

from __future__ import annotations

import itertools
import time
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ADMIN = {"username": "admin", "password": "correct-horse-battery"}
TERMINAL = ("COMPLETED", "FAILED", "CANCELLED")


@pytest.fixture
def settings_factory(tmp_path) -> Callable[..., Settings]:
    """Return a factory producing Settings bound to unique temp directories."""
    counter = itertools.count()

    def _factory(**overrides) -> Settings:
        values: dict = {
            "app_data_dir": tmp_path / f"data-{next(counter)}",
            "agent_backend": "mock",
            "mock_step_delay": 0.0,
            "app_env": "test",
            "log_level": "WARNING",
        }
        values.update(overrides)
        return Settings(**values)

    return _factory


def _client_for(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


@pytest.fixture
def client(settings_factory) -> TestClient:
    with _client_for(settings_factory()) as test_client:
        yield test_client


@pytest.fixture
def slow_client(settings_factory) -> TestClient:
    """Client whose mock agent pauses between steps (for concurrency tests)."""
    with _client_for(settings_factory(mock_step_delay=0.2)) as test_client:
        yield test_client


def _authenticate(test_client: TestClient) -> TestClient:
    response = test_client.post("/api/auth/setup", json=ADMIN)
    assert response.status_code == 201, response.text
    return test_client


@pytest.fixture
def authed(client) -> TestClient:
    return _authenticate(client)


@pytest.fixture
def slow_authed(slow_client) -> TestClient:
    return _authenticate(slow_client)


@pytest.fixture
def wait_for_terminal() -> Callable[..., dict]:
    """Return a polling helper that waits for a task to reach a final state."""

    def _wait(
        test_client: TestClient,
        task_id: str,
        *,
        timeout: float = 15.0,
        terminal: tuple[str, ...] = TERMINAL,
    ) -> dict:
        deadline = time.monotonic() + timeout
        last: dict | None = None
        while time.monotonic() < deadline:
            response = test_client.get(f"/api/tasks/{task_id}")
            assert response.status_code == 200, response.text
            last = response.json()
            if last["status"] in terminal:
                return last
            time.sleep(0.02)
        raise AssertionError(f"task {task_id} never reached {terminal}; last={last}")

    return _wait


@pytest.fixture
def make_project() -> Callable[[TestClient, str], dict]:
    """Create a project through the API and return its JSON representation."""

    def _make(test_client: TestClient, name: str = "demo") -> dict:
        response = test_client.post("/api/projects", json={"name": name})
        assert response.status_code == 201, response.text
        return response.json()

    return _make
