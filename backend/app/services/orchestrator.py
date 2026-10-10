"""Task orchestration.

The orchestrator is the backend source of truth for task lifecycle. It:

* persists every task/event transition before broadcasting it,
* keeps at most one modifying task per project,
* routes user messages to chat / steering / cancellation / new task,
* never trusts model output to execute commands or paths.

Phase 1 drives a mock adapter; Phase 2 swaps in Pi RPC without changing this
module's contract.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from functools import partial

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..adapters.base import AgentEvent, CodingAgentAdapter
from ..config import Settings
from ..domain import EventType, Intent, TERMINAL_STATUSES, TaskStatus, TaskType
from ..models import Task
from ..repositories import (
    ConversationRepository,
    EventRepository,
    ProjectRepository,
    TaskRepository,
)
from ..schemas import EventOut, MessageOut, TaskOut
from .context import build_snapshot, offline_answer
from .event_bus import EventBus
from .intent import IntentRouter
from .project_service import resolve_project_root

logger = logging.getLogger(__name__)


class TaskConflictError(RuntimeError):
    """Raised when a second modifying task is requested for a busy project."""


class OrchestratorService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        bus: EventBus,
        adapter: CodingAgentAdapter,
        settings: Settings,
        router: IntentRouter | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._bus = bus
        self._adapter = adapter
        self._settings = settings
        self._router = router or IntentRouter()
        self._runners: dict[str, asyncio.Task[None]] = {}

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        await self._adapter.start()
        count = await self._mark_stale_tasks_for_recovery()
        if count:
            logger.warning("marked %d in-flight task(s) as RECOVERY_REQUIRED", count)

    async def shutdown(self) -> None:
        for runner in list(self._runners.values()):
            if not runner.done():
                runner.cancel()
        pending = [r for r in self._runners.values() if not r.done()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._runners.clear()
        await self._adapter.stop()

    @property
    def adapter_name(self) -> str:
        return self._adapter.name

    async def _mark_stale_tasks_for_recovery(self) -> int:
        async with self._session_factory() as session:
            count = await TaskRepository(session).mark_in_flight_for_recovery()
            await session.commit()
            return count

    # ------------------------------------------------------------------ #
    # Task creation / control
    # ------------------------------------------------------------------ #
    async def start_coding_task(
        self,
        *,
        project_id: str,
        instruction: str,
        conversation_id: str | None = None,
        parent_task_id: str | None = None,
    ) -> Task:
        async with self._session_factory() as session:
            project = await ProjectRepository(session).get(project_id)
            if project is None:
                raise LookupError("project not found")
            tasks = TaskRepository(session)
            active = await tasks.find_active(project_id)
            if active is not None:
                raise TaskConflictError(
                    f"task {active.id} is already active for this project"
                )
            task = await tasks.create(
                project_id=project_id,
                instruction=instruction,
                task_type=TaskType.CODING.value,
                conversation_id=conversation_id,
                parent_task_id=parent_task_id,
            )
            await session.commit()

        await self._emit(
            task_id=task.id,
            project_id=project_id,
            type=EventType.TASK_CREATED.value,
            message=f"Coding task created: {instruction.strip()[:160]}",
            data={"task_type": TaskType.CODING.value},
        )
        self._spawn(task.id)
        return task

    def _spawn(self, task_id: str) -> None:
        runner = asyncio.create_task(self._run_task(task_id), name=f"task-{task_id}")
        self._runners[task_id] = runner

    async def cancel_task(self, task_id: str) -> Task | None:
        """Request cancellation. The task reaches CANCELLED only when the
        adapter confirms it, never merely because this call was made."""
        async with self._session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get(task_id)
            if task is None:
                return None
            if TaskStatus(task.status) in TERMINAL_STATUSES:
                return task
            await repo.update(task, status=TaskStatus.CANCEL_REQUESTED)
            project_id = task.project_id
            await session.commit()

        await self._adapter.cancel(task_id=task_id)
        await self._emit(
            task_id=task_id,
            project_id=project_id,
            type=EventType.PROGRESS_SUMMARY.value,
            message="Cancellation requested; waiting for the agent to confirm.",
            data={"status": TaskStatus.CANCEL_REQUESTED.value},
        )
        return task

    async def steer_task(self, task_id: str, instruction: str) -> bool:
        """Send a follow-up instruction to an active task."""
        async with self._session_factory() as session:
            task = await TaskRepository(session).get(task_id)
            if task is None or TaskStatus(task.status) in TERMINAL_STATUSES:
                return False
            project_id = task.project_id

        await self._adapter.steer(task_id=task_id, instruction=instruction)
        await self._emit(
            task_id=task_id,
            project_id=project_id,
            type=EventType.MESSAGE_RECEIVED.value,
            message=f"Follow-up instruction sent to the active task: {instruction.strip()[:160]}",
            data={"steered": True},
        )
        return True

    # ------------------------------------------------------------------ #
    # User message routing
    # ------------------------------------------------------------------ #
    async def handle_user_message(
        self,
        *,
        project_id: str,
        content: str,
        conversation_id: str | None = None,
    ) -> dict:
        """Route an inbound user message and return the dispatch result."""
        async with self._session_factory() as session:
            project = await ProjectRepository(session).get(project_id)
            if project is None:
                raise LookupError("project not found")
            conversations = ConversationRepository(session)
            if conversation_id:
                conversation = await conversations.get(conversation_id)
                if conversation is None or conversation.project_id != project_id:
                    raise LookupError("conversation not found for this project")
            else:
                conversation = await conversations.get_or_create_for_project(project_id)

            await conversations.add_message(
                conversation_id=conversation.id, role="user", content=content
            )
            active = await TaskRepository(session).find_active(project_id)
            active_task_id = active.id if active else None
            await session.commit()
            conversation_id = conversation.id

        await self._emit(
            task_id=active_task_id,
            project_id=project_id,
            type=EventType.MESSAGE_RECEIVED.value,
            message=f"User: {content.strip()[:160]}",
            data={"conversation_id": conversation_id},
        )

        intent = self._router.classify(content, has_active_task=active_task_id is not None)
        return await self._dispatch(
            intent=intent,
            project_id=project_id,
            content=content,
            conversation_id=conversation_id,
            active_task_id=active_task_id,
        )

    async def _dispatch(
        self,
        *,
        intent: Intent,
        project_id: str,
        content: str,
        conversation_id: str,
        active_task_id: str | None,
    ) -> dict:
        if intent is Intent.STOP_ACTIVE_TASK:
            if active_task_id:
                await self.cancel_task(active_task_id)
                reply, task_id = (
                    "Cancellation requested for the active task. I will confirm "
                    "once the agent stops.",
                    active_task_id,
                )
            else:
                reply, task_id = "There is no active task to stop.", None

        elif intent is Intent.STEER_ACTIVE_TASK and active_task_id:
            ok = await self.steer_task(active_task_id, content)
            reply = (
                "Sent that instruction to the active task."
                if ok
                else "That task is no longer running; nothing was steered."
            )
            task_id = active_task_id

        elif intent is Intent.START_CODING_TASK and active_task_id is None:
            try:
                task = await self.start_coding_task(
                    project_id=project_id,
                    instruction=content,
                    conversation_id=conversation_id,
                )
            except TaskConflictError:
                reply, task_id = (
                    "A coding task is already running. Send it as a follow-up "
                    "instruction instead.",
                    active_task_id,
                )
            else:
                reply, task_id = (
                    f"Started a coding task: {content.strip()[:160]}",
                    task.id,
                )

        elif intent is Intent.STEER_ACTIVE_TASK:
            # Steering requested but nothing is running: treat as a new task.
            task = await self.start_coding_task(
                project_id=project_id,
                instruction=content,
                conversation_id=conversation_id,
            )
            reply, task_id = f"Started a coding task: {content.strip()[:160]}", task.id

        elif intent is Intent.CHAT_OR_EXPLAIN:
            reply, task_id = await self._answer_question(
                project_id=project_id,
                content=content,
                conversation_id=conversation_id,
            )

        else:  # NEEDS_CLARIFICATION
            reply, task_id = (
                "I could not tell whether you want an answer or a code change. "
                "Could you rephrase?",
                None,
            )

        message = await self._add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=reply,
            task_id=task_id,
        )
        await self._emit(
            task_id=task_id,
            project_id=project_id,
            type=EventType.ASSISTANT_MESSAGE.value,
            message=reply[:240],
            data={"conversation_id": conversation_id},
        )
        return {"intent": intent.value, "message": message, "task_id": task_id}

    async def _answer_question(
        self, *, project_id: str, content: str, conversation_id: str
    ) -> tuple[str, str | None]:
        """Answer a project question from a bounded snapshot without
        interrupting any active coding task."""
        async with self._session_factory() as session:
            project = await ProjectRepository(session).get(project_id)
            if project is None:
                raise LookupError("project not found")
            root = resolve_project_root(self._settings, project)
            snapshot = await build_snapshot(session, project, root)
            answer = offline_answer(snapshot, content)
            task = await TaskRepository(session).create(
                project_id=project_id,
                instruction=content,
                task_type=TaskType.QUESTION.value,
                conversation_id=conversation_id,
                status=TaskStatus.COMPLETED,
            )
            await TaskRepository(session).update(
                task, result_summary=answer, progress_summary="Answered from snapshot."
            )
            await session.commit()
            task_id = task.id
        await self._emit(
            task_id=task_id,
            project_id=project_id,
            type=EventType.PROGRESS_SUMMARY.value,
            message="Answered the question from the current project snapshot.",
            data={"task_type": TaskType.QUESTION.value},
        )
        return answer, task_id

    # ------------------------------------------------------------------ #
    # Task execution
    # ------------------------------------------------------------------ #
    async def _run_task(self, task_id: str) -> None:
        project_id: str | None = None
        try:
            async with self._session_factory() as session:
                task = await TaskRepository(session).get(task_id)
                if task is None:
                    logger.warning("runner started for unknown task %s", task_id)
                    return
                project = await ProjectRepository(session).get(task.project_id)
                if project is None:
                    await self._set_status(
                        task_id, None, TaskStatus.FAILED, error="project not found"
                    )
                    return
                project_id = project.id
                instruction = task.instruction
                root = resolve_project_root(self._settings, project)
            root.mkdir(parents=True, exist_ok=True)

            await self._set_status(task_id, project_id, TaskStatus.RUNNING)
            result = await self._adapter.run(
                task_id=task_id,
                prompt=instruction,
                cwd=str(root),
                on_event=partial(self._on_agent_event, task_id, project_id),
            )

            if result.cancelled:
                await self._set_status(
                    task_id,
                    project_id,
                    TaskStatus.CANCELLED,
                    result_summary=result.summary,
                )
            elif result.ok:
                await self._set_status(
                    task_id,
                    project_id,
                    TaskStatus.COMPLETED,
                    result_summary=result.summary,
                    progress_summary="Completed.",
                )
            else:
                await self._set_status(
                    task_id,
                    project_id,
                    TaskStatus.FAILED,
                    result_summary=result.summary,
                    error=result.error or "agent reported failure",
                )
        except asyncio.CancelledError:
            if project_id:
                await self._set_status(
                    task_id,
                    project_id,
                    TaskStatus.CANCELLED,
                    result_summary="Task cancelled during shutdown.",
                )
            raise
        except Exception as exc:  # noqa: BLE001 - surface any adapter failure
            logger.exception("task %s failed", task_id)
            await self._set_status(
                task_id,
                project_id,
                TaskStatus.FAILED,
                error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            self._runners.pop(task_id, None)

    async def _on_agent_event(
        self, task_id: str, project_id: str, event: AgentEvent
    ) -> None:
        """Persist side effects of an adapter event, then broadcast it."""
        async with self._session_factory() as session:
            repo = TaskRepository(session)
            if event.type == EventType.FILE_CHANGED.value:
                path = event.data.get("path")
                if path:
                    await repo.add_file(
                        task_id=task_id,
                        path=str(path),
                        change_type=str(event.data.get("change_type", "modified")),
                    )
            elif event.type == EventType.PROGRESS_SUMMARY.value:
                task = await repo.get(task_id)
                if task is not None:
                    await repo.update(task, progress_summary=event.message)
            await session.commit()

        await self._emit(
            task_id=task_id,
            project_id=project_id,
            type=event.type,
            message=event.message,
            data=event.data,
        )

    # ------------------------------------------------------------------ #
    # Persistence & broadcast helpers
    # ------------------------------------------------------------------ #
    async def _emit(
        self,
        *,
        task_id: str | None,
        project_id: str | None,
        type: str,  # noqa: A002 - domain vocabulary field
        message: str,
        data: dict | None = None,
    ) -> None:
        async with self._session_factory() as session:
            event = await EventRepository(
                session, raw_log_max_chars=self._settings.raw_log_max_chars
            ).add(
                task_id=task_id,
                project_id=project_id,
                type=type,
                message=message,
                data=data or {},
            )
            await session.commit()
            payload = EventOut.model_validate(event).model_dump(mode="json")
        await self._bus.publish({"channel": "event", "payload": payload})

    async def _set_status(
        self,
        task_id: str,
        project_id: str | None,
        status: TaskStatus,
        *,
        progress_summary: str | None = None,
        result_summary: str | None = None,
        error: str | None = None,
    ) -> None:
        async with self._session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get(task_id)
            if task is None:
                return
            # Never overwrite a terminal state. This closes the race where a
            # shutdown cancellation arrives just after a task completed.
            if TaskStatus(task.status) in TERMINAL_STATUSES:
                return
            await repo.update(
                task,
                status=status,
                progress_summary=progress_summary,
                result_summary=result_summary,
                error=error,
            )
            await session.commit()
            payload = TaskOut.model_validate(task).model_dump(mode="json")

        await self._bus.publish({"channel": "task", "payload": payload})
        await self._emit(
            task_id=task_id,
            project_id=project_id,
            type=EventType.TASK_STATUS_CHANGED.value,
            message=f"Task status: {status.value}",
            data={"status": status.value},
        )

    async def _add_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        task_id: str | None = None,
    ) -> MessageOut:
        async with self._session_factory() as session:
            message = await ConversationRepository(session).add_message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                task_id=task_id,
            )
            await session.commit()
            payload = MessageOut.model_validate(message)
        await self._bus.publish(
            {"channel": "message", "payload": payload.model_dump(mode="json")}
        )
        return payload
