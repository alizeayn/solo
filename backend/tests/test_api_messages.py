"""API tests for message routing (chat, steer, stop, new task)."""

from __future__ import annotations


def _send(test_client, project_id: str, content: str):
    return test_client.post(
        f"/api/projects/{project_id}/messages", json={"content": content}
    )


def test_informational_question_is_answered_from_snapshot(authed, make_project):
    project = make_project(authed)
    response = _send(authed, project["id"], "how many files are there?")
    assert response.status_code == 201
    body = response.json()
    assert body["intent"] == "CHAT_OR_EXPLAIN"
    assert body["message"]["role"] == "assistant"
    assert body["message"]["content"]
    assert body["task_id"] is not None


def test_coding_request_starts_a_task(authed, make_project, wait_for_terminal):
    project = make_project(authed)
    body = _send(authed, project["id"], "add a login page").json()
    assert body["intent"] == "START_CODING_TASK"
    assert body["task_id"] is not None
    final = wait_for_terminal(authed, body["task_id"])
    assert final["status"] == "COMPLETED"
    assert final["task_type"] == "CODING"


def test_follow_up_while_running_steers_the_same_task(
    slow_authed, make_project, wait_for_terminal
):
    project = make_project(slow_authed)
    started = slow_authed.post(
        "/api/tasks", json={"project_id": project["id"], "instruction": "build it"}
    ).json()
    task_id = started["id"]

    body = _send(slow_authed, project["id"], "also update the changelog").json()
    assert body["intent"] == "STEER_ACTIVE_TASK"
    assert body["task_id"] == task_id

    final = wait_for_terminal(slow_authed, task_id)
    assert final["status"] == "COMPLETED"


def test_question_while_running_does_not_interrupt_task(
    slow_authed, make_project, wait_for_terminal
):
    project = make_project(slow_authed)
    started = slow_authed.post(
        "/api/tasks", json={"project_id": project["id"], "instruction": "build it"}
    ).json()
    task_id = started["id"]

    body = _send(slow_authed, project["id"], "what files changed so far?").json()
    assert body["intent"] == "CHAT_OR_EXPLAIN"
    # A separate question task is created; the coding task is untouched.
    assert body["task_id"] != task_id

    detail = slow_authed.get(f"/api/tasks/{task_id}").json()
    assert detail["status"] in ("QUEUED", "RUNNING", "COMPLETED")
    assert wait_for_terminal(slow_authed, task_id)["status"] == "COMPLETED"


def test_stop_cancels_the_active_task(slow_authed, make_project, wait_for_terminal):
    project = make_project(slow_authed)
    started = slow_authed.post(
        "/api/tasks", json={"project_id": project["id"], "instruction": "long job"}
    ).json()

    body = _send(slow_authed, project["id"], "stop").json()
    assert body["intent"] == "STOP_ACTIVE_TASK"
    assert body["task_id"] == started["id"]

    assert wait_for_terminal(slow_authed, started["id"])["status"] == "CANCELLED"


def test_stop_without_active_task_is_harmless(authed, make_project):
    project = make_project(authed)
    body = _send(authed, project["id"], "stop").json()
    assert body["intent"] == "STOP_ACTIVE_TASK"
    assert body["task_id"] is None
    assert "no active task" in body["message"]["content"].lower()


def test_message_history_is_returned_in_order(authed, make_project):
    project = make_project(authed)
    _send(authed, project["id"], "hello there")
    _send(authed, project["id"], "how many files are there?")

    history = authed.get(f"/api/projects/{project['id']}/messages").json()
    roles = [message["role"] for message in history]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert history[0]["content"] == "hello there"


def test_messages_for_unknown_project(authed):
    assert authed.get("/api/projects/nope/messages").status_code == 404
    assert _send(authed, "nope", "hi").status_code == 404
