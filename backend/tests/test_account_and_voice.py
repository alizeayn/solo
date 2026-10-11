"""Tests for account management and the narration (voice output) pipeline."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.container import Container
from app.main import create_app
from app.services.account_service import AccountError, AccountService
from app.services.narration import (
    NarrationLine,
    NarrationService,
    Priority,
    RecordingTransport,
)
from tests.conftest import ADMIN

# --------------------------------------------------------------------------- #
# Narration: ordering, coalescing, barge-in
# --------------------------------------------------------------------------- #
async def test_only_milestones_are_queued_and_delivered_in_order():
    transport = RecordingTransport()
    service = NarrationService(transport=transport, min_interval=0)
    await service.start()
    try:
        await service.announce("Inspecting the module.", kind="progress")
        await service.announce("The task is complete.", kind="outcome", priority=Priority.IMPORTANT)
        await asyncio.sleep(0.05)
    finally:
        await service.stop()
    # Important outranks progress, so it is delivered first.
    assert [line.text for line in transport.lines] == [
        "The task is complete.",
        "Inspecting the module.",
    ]


async def test_a_newer_progress_line_supersedes_a_queued_older_one():
    transport = RecordingTransport()
    service = NarrationService(transport=transport, min_interval=0)
    # Do not start the worker: inspect the queue directly.
    await service.announce("Found the module.", kind="progress")
    await service.announce("Tests pass.", kind="progress")

    queued = [line.text for line in service._queue]  # noqa: SLF001 - queue semantics under test
    assert queued == ["Tests pass."], "a stale progress line must be dropped"


async def test_progress_never_displaces_an_important_line():
    service = NarrationService(min_interval=0)
    await service.announce("Task complete.", kind="outcome", priority=Priority.IMPORTANT)
    await service.announce("Found the module.", kind="progress")
    queued = {line.text for line in service._queue}  # noqa: SLF001
    assert queued == {"Task complete.", "Found the module."}


async def test_identical_consecutive_lines_are_not_repeated():
    transport = RecordingTransport()
    service = NarrationService(transport=transport, min_interval=0)
    await service.start()
    try:
        await service.announce("Working on it.")
        await asyncio.sleep(0.02)
        await service.announce("Working on it.")
        await asyncio.sleep(0.05)
    finally:
        await service.stop()
    assert len(transport.lines) == 1


async def test_interrupt_drops_progress_but_keeps_errors():
    service = NarrationService(min_interval=0)
    await service.announce("Something failed.", kind="error", priority=Priority.CRITICAL)
    await service.announce("Found the module.", kind="progress")

    dropped = await service.interrupt("user")
    assert dropped == 1
    assert [line.text for line in service._queue] == ["Something failed."]  # noqa: SLF001
    assert service.listening is True

    # While listening, new progress is refused rather than queued over the user.
    assert await service.announce("More progress.", kind="progress") is None
    assert service.dropped >= 2

    await service.resume()
    assert service.listening is False
    assert await service.announce("Carrying on.", kind="progress") is not None


async def test_interrupt_stops_in_flight_speech():
    transport = RecordingTransport()
    service = NarrationService(transport=transport, min_interval=0)
    await service.interrupt("user")
    assert transport.stops == 1


async def test_the_queue_is_bounded():
    service = NarrationService(min_interval=0, max_queue=4)
    for index in range(20):
        await service.announce(f"Line {index}", kind="outcome", priority=Priority.IMPORTANT)
    assert len(service._queue) <= 4  # noqa: SLF001
    assert service.dropped > 0


async def test_empty_lines_are_ignored():
    service = NarrationService(min_interval=0)
    assert await service.announce("   ") is None
    assert service._queue == []  # noqa: SLF001


async def test_a_failing_transport_never_breaks_the_pipeline():
    class Broken(NarrationTransport := type):  # placeholder to keep the name local
        pass

    class Failing:
        name = "failing"

        async def deliver(self, line: NarrationLine) -> None:
            raise RuntimeError("no audio device")

        async def stop(self) -> None:
            return None

    service = NarrationService(transport=Failing(), min_interval=0)
    await service.start()
    try:
        await service.announce("Still queued.")
        await asyncio.sleep(0.05)
        assert service.state()["queued"] == 0, "the worker must not die on a transport error"
    finally:
        await service.stop()
    del Broken


async def test_state_is_honest_about_audio(tmp_path):
    service = NarrationService(min_interval=0)
    state = service.state()
    assert state["transport"] == "recording"
    assert state["audio_available"] is False, "no audio transport ships in this phase"
    assert state["listening"] is False


async def test_lines_are_published_to_the_bus():
    class Bus:
        def __init__(self) -> None:
            self.messages: list[dict] = []

        async def publish(self, message: dict) -> None:
            self.messages.append(message)

    bus = Bus()
    service = NarrationService(bus=bus, min_interval=0)
    await service.start()
    try:
        await service.announce("Hello.")
        await asyncio.sleep(0.05)
    finally:
        await service.stop()

    channels = {message["channel"] for message in bus.messages}
    assert "narration" in channels


# --------------------------------------------------------------------------- #
# Account service
# --------------------------------------------------------------------------- #
@pytest.fixture
async def container(settings_factory):
    instance = await Container.create(settings_factory())
    try:
        yield instance
    finally:
        await instance.close()


async def _make_user(container, username="admin", password="first-password"):
    return await container.auth.setup(username, password)


async def test_account_describe(container):
    await _make_user(container)
    async with container.session_factory() as session:
        from app.repositories import UserRepository

        user = await UserRepository(session).get_by_username("admin")
    described = await container.account.describe(user.id, current_token="t")
    assert described["username"] == "admin"
    assert described["role"] == "owner"
    assert described["active_sessions"] == 1


async def test_change_username_requires_the_current_password(container):
    await _make_user(container)
    async with container.session_factory() as session:
        from app.repositories import UserRepository

        user = await UserRepository(session).get_by_username("admin")

    with pytest.raises(AccountError, match="current password is incorrect"):
        await container.account.change_username(
            user.id, new_username="someone", current_password="wrong"
        )

    changed = await container.account.change_username(
        user.id, new_username="owner", current_password="first-password"
    )
    assert changed == "owner"


@pytest.mark.parametrize("candidate", ["ab", "has space", "-leading", "a" * 65, "bad!"])
async def test_invalid_usernames_are_rejected(container, candidate):
    await _make_user(container)
    async with container.session_factory() as session:
        from app.repositories import UserRepository

        user = await UserRepository(session).get_by_username("admin")
    with pytest.raises(AccountError):
        await container.account.change_username(
            user.id, new_username=candidate, current_password="first-password"
        )


async def test_change_password_requires_the_current_password(container):
    await _make_user(container)
    async with container.session_factory() as session:
        from app.repositories import UserRepository

        user = await UserRepository(session).get_by_username("admin")

    with pytest.raises(AccountError, match="current password is incorrect"):
        await container.account.change_password(
            user.id, current_password="wrong", new_password="second-password"
        )
    # The old password still works, so nothing changed.
    assert await container.auth.login("admin", "first-password") is not None


@pytest.mark.parametrize("candidate", ["short", ""])
async def test_short_passwords_are_rejected(container, candidate):
    await _make_user(container)
    async with container.session_factory() as session:
        from app.repositories import UserRepository

        user = await UserRepository(session).get_by_username("admin")
    with pytest.raises(AccountError, match="at least 8"):
        await container.account.change_password(
            user.id, current_password="first-password", new_password=candidate
        )


async def test_reusing_the_same_password_is_rejected(container):
    await _make_user(container)
    async with container.session_factory() as session:
        from app.repositories import UserRepository

        user = await UserRepository(session).get_by_username("admin")
    with pytest.raises(AccountError, match="must differ"):
        await container.account.change_password(
            user.id, current_password="first-password", new_password="first-password"
        )


async def test_changing_the_password_revokes_other_sessions_but_keeps_the_current_one(
    container,
):
    token = await _make_user(container)
    assert token is not None
    second = await container.auth.login("admin", "first-password")
    assert second is not None

    async with container.session_factory() as session:
        from app.repositories import UserRepository

        user = await UserRepository(session).get_by_username("admin")

    revoked = await container.account.change_password(
        user.id,
        current_password="first-password",
        new_password="second-password",
        current_token=token,
    )
    assert revoked == 1

    # The session that made the change survives…
    assert await container.auth.resolve(token) is not None
    # …the other one does not…
    assert await container.auth.resolve(second) is None
    # …and the new password works while the old one does not.
    assert await container.auth.login("admin", "second-password") is not None
    assert await container.auth.login("admin", "first-password") is None


async def test_new_password_survives_a_restart(settings_factory):
    """A changed password must persist, not just live in memory."""
    settings = settings_factory()
    first = await Container.create(settings)
    try:
        await first.auth.setup("admin", "first-password")
        async with first.session_factory() as session:
            from app.repositories import UserRepository

            user = await UserRepository(session).get_by_username("admin")
        await first.account.change_password(
            user.id, current_password="first-password", new_password="second-password"
        )
    finally:
        await first.close()

    second = await Container.create(settings)
    try:
        assert await second.auth.login("admin", "second-password") is not None
        assert await second.auth.login("admin", "first-password") is None
    finally:
        await second.close()


async def test_revoke_other_sessions(container):
    token = await _make_user(container)
    assert token is not None
    other = await container.auth.login("admin", "first-password")
    assert other is not None
    async with container.session_factory() as session:
        from app.repositories import UserRepository

        user = await UserRepository(session).get_by_username("admin")

    assert await container.account.revoke_other_sessions(user.id, token) == 1
    assert await container.auth.resolve(token) is not None
    assert await container.auth.resolve(other) is None


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(settings_factory):
    with TestClient(create_app(settings_factory())) as test_client:
        assert test_client.post("/api/auth/setup", json=ADMIN).status_code == 201
        yield test_client


def test_account_endpoints_require_authentication(settings_factory):
    with TestClient(create_app(settings_factory())) as anon:
        assert anon.get("/api/account").status_code == 401
        assert anon.put("/api/account/password", json={}).status_code == 401
        assert anon.get("/api/voice/state").status_code == 401


def test_read_account(client):
    body = client.get("/api/account").json()
    assert body["username"] == "admin"
    assert body["role"] == "owner"
    assert body["active_sessions"] >= 1


def test_change_username_through_the_api(client):
    response = client.put(
        "/api/account/username",
        json={"new_username": "owner", "current_password": ADMIN["password"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["username"] == "owner"

    # The session survives, and the new username is what identifies it.
    assert client.get("/api/account").json()["username"] == "owner"
    assert client.get("/api/auth/me").json()["username"] == "owner"


def test_change_username_with_a_wrong_password_is_rejected(client):
    response = client.put(
        "/api/account/username",
        json={"new_username": "owner", "current_password": "not-the-password"},
    )
    assert response.status_code == 400
    assert "incorrect" in response.json()["detail"]
    assert client.get("/api/account").json()["username"] == "admin"


def test_change_password_through_the_api_keeps_the_session(client):
    response = client.put(
        "/api/account/password",
        json={"current_password": ADMIN["password"], "new_password": "a-better-password"},
    )
    assert response.status_code == 200, response.text

    # Still signed in on this browser…
    assert client.get("/api/account").status_code == 200
    # …and the new password works at the login endpoint.
    client.post("/api/auth/logout")
    assert client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "a-better-password"},
    ).status_code == 200
    assert client.post(
        "/api/auth/login", json={"username": "admin", "password": ADMIN["password"]}
    ).status_code == 401


def test_change_password_rejects_a_short_password(client):
    response = client.put(
        "/api/account/password",
        json={"current_password": ADMIN["password"], "new_password": "short"},
    )
    assert response.status_code == 422


def test_revoke_other_sessions_endpoint(client):
    body = client.post("/api/account/sessions/revoke").json()
    assert body["active_sessions"] == 1
    assert client.get("/api/account").status_code == 200


def test_voice_state_reports_a_real_pipeline_without_audio(client):
    body = client.get("/api/voice/state").json()
    assert body["transport"] == "recording"
    assert body["audio_available"] is False, "audio must not be claimed before Phase 4"
    assert body["phase"] == "narration-foundation"
    assert "recent" in body


def test_voice_interrupt_and_resume(client):
    interrupted = client.post("/api/voice/interrupt", json={"reason": "user"}).json()
    assert interrupted["listening"] is True
    resumed = client.post("/api/voice/resume").json()
    assert resumed["listening"] is False


def test_voice_history(client):
    assert client.get("/api/voice/history").json() == []
    assert client.get("/api/voice/history", params={"limit": 0}).status_code == 400


def test_task_milestones_reach_the_narration_channel(client, make_project, wait_for_terminal):
    """A completed task must produce something the voice channel could say."""
    project = make_project(client, "voice-demo")
    task = client.post(
        "/api/tasks",
        json={"project_id": project["id"], "instruction": "add a health endpoint"},
    ).json()
    wait_for_terminal(client, task["id"])

    history = client.get("/api/voice/history").json()
    assert history, "the narration pipeline received nothing from a completed task"
    kinds = {line["kind"] for line in history}
    assert "outcome" in kinds or "progress" in kinds or "summary" in kinds
    assert all(line["text"] for line in history), "empty lines must never be queued"
