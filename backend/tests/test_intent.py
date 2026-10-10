"""Tests for deterministic intent routing."""

from __future__ import annotations

import pytest

from app.domain import Intent
from app.services.intent import IntentRouter

router = IntentRouter()


@pytest.mark.parametrize(
    "message",
    ["stop", "Cancel this", "abort the run", "  Halt ", "terminate"],
)
def test_stop_intents(message):
    assert router.classify(message, has_active_task=True) is Intent.STOP_ACTIVE_TASK


@pytest.mark.parametrize(
    "message",
    ["add a login page", "fix the failing test", "implement retries", "refactor auth"],
)
def test_coding_requests_start_a_task(message):
    assert router.classify(message, has_active_task=False) is Intent.START_CODING_TASK


@pytest.mark.parametrize(
    "message",
    ["how many files are there?", "explain the architecture", "what is running?"],
)
def test_questions_are_answered(message):
    assert router.classify(message, has_active_task=False) is Intent.CHAT_OR_EXPLAIN


@pytest.mark.parametrize(
    "message",
    ["also fix the typo", "instead use aiohttp", "wait, change the name"],
)
def test_follow_ups_steer_the_active_task(message):
    assert router.classify(message, has_active_task=True) is Intent.STEER_ACTIVE_TASK


def test_coding_request_while_busy_steers_instead_of_starting_second_writer():
    assert (
        router.classify("add another endpoint", has_active_task=True)
        is Intent.STEER_ACTIVE_TASK
    )


def test_question_while_busy_does_not_steer():
    assert (
        router.classify("what files changed so far?", has_active_task=True)
        is Intent.CHAT_OR_EXPLAIN
    )


def test_empty_message_needs_clarification():
    assert router.classify("   ", has_active_task=False) is Intent.NEEDS_CLARIFICATION
