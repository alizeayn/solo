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
from ..domain import (
    EventType,
    Intent,
    PlannedTaskStatus,
    TERMINAL_STATUSES,
    TaskStatus,
    TaskType,
)
from ..models import Project, Task
from ..repositories import (
    ConversationRepository,
    EventRepository,
    ProjectRepository,
    TaskRepository,
)
from ..schemas import EventOut, MessageOut, TaskOut
from .checks import ChecksService
from .context import build_snapshot, offline_answer
from .event_bus import EventBus
from .intent import IntentRouter
from .milestones import MilestoneService
from .narration import NarrationService, Priority
from .orchestration_state import OrchestrationState, PlannedTask
from .orchestrator_brain import IntentDecision, OrchestratorBrain
from .project_paths import ProjectPathError, resolve_project_root
from .project_store import ProjectStoreService

logger = logging.getLogger(__name__)


class TaskConflictError(RuntimeError):
    """Raised when a second modifying task is requested for a busy project."""


def _short(text: str, limit: int = 80) -> str:
    """A one-line label for a queued step."""
    cleaned = " ".join((text or "").split())
    return cleaned if len(cleaned) <= limit else f"{cleaned[: limit - 1].rstrip()}…"


class OrchestratorService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        bus: EventBus,
        adapter: CodingAgentAdapter,
        settings: Settings,
        router: IntentRouter | None = None,
        store: ProjectStoreService | None = None,
        brain: OrchestratorBrain | None = None,
        checks: ChecksService | None = None,
        narration: NarrationService | None = None,
        milestones: MilestoneService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._bus = bus
        self._adapter = adapter
        self._settings = settings
        self._router = router or IntentRouter()
        self._store = store
        self._brain = brain
        self._checks = checks
        self._narration = narration
        self._milestones = milestones
        self._runners: dict[str, asyncio.Task[None]] = {}
        #: Post-settle work (summary, checks, queue advance) kept off the
        #: notification path but tracked so shutdown can await it.
        self._post_tasks: set[asyncio.Task[None]] = set()
        #: Recent activity per task, used to build a summary when it settles.
        self._activity: dict[str, list[str]] = {}
        self._files: dict[str, list[str]] = {}
        self._summarised: set[str] = set()

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

        post = [task for task in self._post_tasks if not task.done()]
        for task in post:
            task.cancel()
        if post:
            await asyncio.gather(*post, return_exceptions=True)
        self._post_tasks.clear()

        await self._adapter.stop()

    @property
    def adapter_name(self) -> str:
        return self._adapter.name

    def sessions(self) -> list[dict[str, Any]]:
        """Live coding-agent sessions, when the backend supports them."""
        getter = getattr(self._adapter, "sessions", None)
        if not callable(getter):
            return []
        try:
            return list(getter())
        except Exception:  # noqa: BLE001 - diagnostics must never raise
            logger.debug("could not read adapter sessions", exc_info=True)
            return []

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
        plan_id: str | None = None,
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

        # Every coding task is tracked in the orchestrator's working memory, so
        # the Plan panel is meaningful even when the LLM planner is disabled.
        if self._store is not None:
            state = await self._load_state(project)
            if plan_id and state.find(plan_id) is not None:
                state.set_status(plan_id, PlannedTaskStatus.RUNNING, task_id=task.id)
            else:
                entry = state.add(
                    PlannedTask(
                        title=_short(instruction),
                        instruction=instruction,
                        priority=10,
                        source="user",
                        status=PlannedTaskStatus.RUNNING.value,
                        task_id=task.id,
                    )
                )
                plan_id = entry.id
            state.set_active(task.id, plan_id=plan_id)
            await self._save_state(project, state)

        await self._emit(
            task_id=task.id,
            project_id=project_id,
            type=EventType.TASK_CREATED.value,
            message=f"Coding task created: {instruction.strip()[:160]}",
            data={"task_type": TaskType.CODING.value, "plan_id": plan_id},
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
    # ------------------------------------------------------------------ #
    # Orchestration state (see services/orchestration_state.py)
    # ------------------------------------------------------------------ #
    async def _load_state(self, project: Project) -> OrchestrationState:
        raw = self._store.read_orchestration(project) if self._store else None
        if isinstance(raw, dict):
            return OrchestrationState.from_dict(raw, project_id=project.id)
        return OrchestrationState(project_id=project.id)

    async def _save_state(self, project: Project, state: OrchestrationState) -> None:
        """Persist the working memory and broadcast it to the UI."""
        if self._store is not None:
            # File I/O must not stall the event loop; the store is a plain
            # synchronous writer by design (atomic temp-file replace).
            ok = await asyncio.to_thread(self._store.write_orchestration, project, state.to_dict())
            if not ok:
                logger.warning("could not persist orchestration state for %s", project.id)
        await self._bus.publish({"channel": "orchestration", "payload": state.summary()})

    async def orchestration_state(self, project_id: str) -> dict:
        """Public view of the orchestrator's working memory for a project."""
        async with self._session_factory() as session:
            project = await ProjectRepository(session).get(project_id)
        if project is None:
            raise LookupError("project not found")
        state = await self._load_state(project)
        return {"summary": state.summary(), "state": state.to_dict()}

    async def add_orchestration_note(self, project_id: str, text: str) -> dict:
        """Record a user instruction in the project's working memory."""
        project = await self._require_project(project_id)
        state = await self._load_state(project)
        note = state.add_note(text, task_id=state.active_task_id)
        await self._save_state(project, state)
        return note

    async def remove_planned_task(self, project_id: str, plan_id: str) -> bool:
        project = await self._require_project(project_id)
        state = await self._load_state(project)
        if not state.remove(plan_id):
            return False
        await self._save_state(project, state)
        return True

    async def set_planned_task_status(
        self, project_id: str, plan_id: str, status: str
    ) -> dict | None:
        project = await self._require_project(project_id)
        state = await self._load_state(project)
        item = state.set_status(plan_id, status)
        if item is None:
            return None
        await self._save_state(project, state)
        return item.to_dict()

    async def advance_queue(self, project_id: str) -> dict:
        """Start the next ready queued step now, on user request."""
        project = await self._require_project(project_id)
        state = await self._load_state(project)
        if await self._active_task_for(project_id) is not None:
            return {"started": False, "reason": "a task is already running"}
        nxt = state.next_pending()
        if nxt is None:
            return {"started": False, "reason": "the queue is empty"}
        await self._advance_queue(project, state)
        return {"started": True, "plan_id": nxt.id, "title": nxt.title}

    async def _require_project(self, project_id: str) -> Project:
        async with self._session_factory() as session:
            project = await ProjectRepository(session).get(project_id)
        if project is None:
            raise LookupError("project not found")
        return project

    async def plan_instruction(
        self, *, project_id: str, content: str
    ) -> dict:
        """Ask the orchestrator model to decompose an instruction into a plan."""
        async with self._session_factory() as session:
            project = await ProjectRepository(session).get(project_id)
            active = await TaskRepository(session).find_active(project_id)
        if project is None:
            raise LookupError("project not found")
        if self._brain is None:
            return {"planned": [], "reason": "orchestrator model is not available"}
        decision = await self._brain.classify(
            content,
            has_active_task=active is not None,
            active_instruction=active.instruction if active else None,
            active_summary=active.progress_summary if active else None,
        )
        if decision is None:
            return {"planned": [], "reason": "the orchestrator model did not respond"}
        planned = self._brain.plan_from(decision)
        if planned:
            state = await self._load_state(project)
            state.add_many(planned)
            await self._save_state(project, state)
        return {
            "intent": decision.intent.value,
            "reason": decision.reason,
            "planned": [item.to_dict() for item in planned],
        }

    async def _classify(
        self, content: str, *, project_id: str, active: Task | None
    ) -> tuple[Intent, IntentDecision | None]:
        """Classify a message with the orchestrator model, falling back to rules.

        The deterministic router is always the fallback, so classification never
        fails: a missing key, a provider outage or an invalid response degrades
        to the heuristics instead of blocking the user.
        """
        decision: IntentDecision | None = None
        if self._brain is not None and await self._brain.available():
            queued: list[str] = []
            if self._store is not None:
                async with self._session_factory() as session:
                    project = await ProjectRepository(session).get(project_id)
                if project is not None:
                    state = await self._load_state(project)
                    queued = [
                        item.title
                        for item in state.queue
                        if item.status == PlannedTaskStatus.PENDING.value
                    ]
            decision = await self._brain.classify(
                content,
                has_active_task=active is not None,
                active_instruction=active.instruction if active else None,
                active_summary=active.progress_summary if active else None,
                queued=queued,
            )
        if decision is not None:
            return decision.intent, decision
        return self._router.classify(content, has_active_task=active is not None), None

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

        intent, decision = await self._classify(
            content, project_id=project_id, active=active
        )
        return await self._dispatch(
            intent=intent,
            decision=decision,
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
        decision: IntentDecision | None = None,
    ) -> dict:
        project: Project | None = None
        if self._store is not None:
            async with self._session_factory() as session:
                project = await ProjectRepository(session).get(project_id)

        reply: str
        task_id: str | None = None

        if intent is Intent.STOP_ACTIVE_TASK:
            if active_task_id:
                await self.cancel_task(active_task_id)
                reply, task_id = (
                    "Cancellation requested for the active task. I will confirm "
                    "once the agent stops.",
                    active_task_id,
                )
            else:
                reply = "There is no active task to stop."

        elif intent is Intent.STEER_ACTIVE_TASK and active_task_id:
            if project is not None:
                # Remember the instruction. Phases 3-5 read these notes to decide
                # how a late instruction should change the running task.
                state = await self._load_state(project)
                state.add_note(content, task_id=active_task_id, applied="steered")
                await self._save_state(project, state)
            ok = await self.steer_task(active_task_id, content)
            reply = (
                "Sent that instruction to the active task."
                if ok
                else "That task is no longer running; nothing was steered."
            )
            task_id = active_task_id

        elif intent in {Intent.START_CODING_TASK, Intent.STEER_ACTIVE_TASK}:
            if active_task_id is not None:
                # Never start a second writer against one project. Record the
                # request instead, so nothing the user asked for is lost.
                if project is not None:
                    state = await self._load_state(project)
                    state.add_note(
                        content, task_id=active_task_id, kind="deferred_instruction"
                    )
                    await self._save_state(project, state)
                reply, task_id = (
                    "A coding task is already running. I recorded this as a "
                    "follow-up instruction.",
                    active_task_id,
                )
            else:
                reply, task_id = await self._start_from_plan(
                    project=project,
                    project_id=project_id,
                    content=content,
                    conversation_id=conversation_id,
                    decision=decision,
                )

        elif intent is Intent.CHAT_OR_EXPLAIN:
            reply, task_id = await self._answer_question(
                project_id=project_id,
                content=content,
                conversation_id=conversation_id,
            )

        else:  # NEEDS_CLARIFICATION
            reply = (
                "I could not tell whether you want an answer or a code change. "
                "Could you rephrase?"
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
        await self._sync_project_store(
            project_id, conversation_id=conversation_id
        )
        return {
            "intent": intent.value,
            "message": message,
            "task_id": task_id,
            "classified_by": "orchestrator-model" if decision is not None else "rules",
        }

    async def _start_from_plan(
        self,
        *,
        project: Project | None,
        project_id: str,
        content: str,
        conversation_id: str,
        decision: IntentDecision | None,
    ) -> tuple[str, str | None]:
        """Start the highest-priority planned step, or a single task from text.

        When the orchestrator model decomposed a compound request, the plan is
        recorded and its ready step runs first; the rest stay queued and are
        started in order as each settles.
        """
        state: OrchestrationState | None = None
        planned: list[PlannedTask] = []
        if project is not None and self._brain is not None and decision is not None:
            planned = self._brain.plan_from(decision)
            if planned:
                state = await self._load_state(project)
                state.add_many(planned)
                await self._save_state(project, state)
                # Evidence for the planning milestone: a real plan exists.
                await self._emit(
                    task_id=None,
                    project_id=project_id,
                    type=EventType.PROGRESS_SUMMARY.value,
                    message=f"Planned {len(planned)} step(s) for this request",
                    data={
                        "source": "orchestrator",
                        "steps": len(planned),
                        "reason": decision.reason,
                    },
                )

        first = state.next_pending() if state is not None else None
        instruction = first.instruction if first is not None else content

        try:
            task = await self.start_coding_task(
                project_id=project_id,
                instruction=instruction,
                conversation_id=conversation_id,
                plan_id=first.id if first is not None else None,
            )
        except TaskConflictError:
            return (
                "A coding task is already running. I recorded this as a "
                "follow-up instruction.",
                None,
            )

        if len(planned) > 1:
            reply = (
                f"Started '{first.title if first else instruction[:80]}'. "
                f"{len(planned) - 1} further step(s) are queued and will run in order."
            )
        else:
            reply = f"Started a coding task: {instruction.strip()[:160]}"
        return reply, task.id

    async def _active_task_for(self, project_id: str) -> Task | None:
        async with self._session_factory() as session:
            return await TaskRepository(session).find_active(project_id)

    async def _advance_queue(self, project: Project, state: OrchestrationState) -> None:
        """Start the next ready plan step after a successful completion."""
        if await self._active_task_for(project.id) is not None:
            return
        nxt = state.next_pending()
        if nxt is None:
            return
        await self._emit(
            task_id=None,
            project_id=project.id,
            type=EventType.PROGRESS_SUMMARY.value,
            message=f"Starting the next queued step: {nxt.title}",
            data={"plan_id": nxt.id, "source": "orchestrator"},
        )
        try:
            task = await self.start_coding_task(
                project_id=project.id, instruction=nxt.instruction, plan_id=nxt.id
            )
        except TaskConflictError:
            return
        await self._save_state(project, state)

    async def _after_task_settled(self, project_id: str | None, task_id: str) -> None:
        """Post-run orchestration: summarise, verify, and advance the plan."""
        if project_id is None or self._store is None:
            return
        async with self._session_factory() as session:
            project = await ProjectRepository(session).get(project_id)
            task = await TaskRepository(session).get(task_id)
        if project is None or task is None:
            return

        status = TaskStatus(task.status)
        await self._summarise_task(project, task)
        await self._run_checks(project, task)

        state = await self._load_state(project)
        if state.active_task_id == task_id:
            if state.active_plan_id:
                state.set_status(
                    state.active_plan_id,
                    (
                        PlannedTaskStatus.DONE
                        if status is TaskStatus.COMPLETED
                        else PlannedTaskStatus.FAILED
                    ),
                    task_id=task_id,
                    note=task.result_summary,
                )
            state.set_active(None)
            await self._save_state(project, state)

        if status is TaskStatus.COMPLETED:
            await self._advance_queue(project, state)

    async def _summarise_task(self, project: Project, task: Task) -> None:
        """Replace the raw agent text with a concise orchestrator summary."""
        if task.id in self._summarised:
            return
        self._summarised.add(task.id)
        if len(self._summarised) > 500:
            self._summarised.clear()
        if self._brain is None or not await self._brain.available():
            return

        activity = self._activity.pop(task.id, [])
        files = self._files.get(task.id, [])
        summary = await self._brain.summarise(
            instruction=task.instruction,
            status=task.status,
            activity=activity,
            files_changed=files,
            errors=[task.error] if task.error else [],
            deterministic_summary=task.result_summary,
        )
        if not summary:
            return

        async with self._session_factory() as session:
            repo = TaskRepository(session)
            fresh = await repo.get(task.id)
            if fresh is None:
                return
            await repo.update(fresh, result_summary=summary)
            await session.commit()
            payload = TaskOut.model_validate(fresh).model_dump(mode="json")
        await self._bus.publish({"channel": "task", "payload": payload})
        # The user-facing summary is the primary thing worth saying aloud.
        if self._narration is not None:
            await self._narration.announce(
                summary,
                kind="summary",
                priority=int(Priority.IMPORTANT),
                task_id=task.id,
                project_id=project.id,
            )

    async def _run_checks(self, project: Project, task: Task) -> None:
        """Run static checks over the files the agent changed."""
        if self._checks is None or not self._settings.checks_after_task:
            return
        if not self._checks.available():
            return
        try:
            root = resolve_project_root(self._settings, project)
        except ProjectPathError:  # pragma: no cover - tampered record
            return
        result = await self._checks.run_for_project(
            root, changed_files=self._files.get(task.id, [])
        )
        await self._emit(
            task_id=task.id,
            project_id=project.id,
            type=EventType.CHECK_RESULT.value,
            message=result.summary,
            data=result.to_dict(),
        )
        await self._sync_project_store(project.id, task_id=task.id)

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
            answer: str | None = None
            if self._brain is not None and await self._brain.available():
                answer = await self._brain.answer_question(
                    question=content, snapshot_text=snapshot.to_prompt_text()
                )
            if not answer:
                # Deterministic fallback: Solo answers from the snapshot alone.
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
        await self._sync_project_store(project_id, task_id=task_id, refresh_tree=True)
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
            await self._sync_project_store(project_id, task_id=task_id, refresh_tree=True)
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
        self._remember_activity(task_id, event)
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
    def _remember_activity(self, task_id: str, event: AgentEvent) -> None:
        """Keep a bounded trace of a run for the orchestrator's summary."""
        bucket = self._activity.setdefault(task_id, [])
        bucket.append(f"{event.type}: {event.message}")
        if len(bucket) > 60:
            del bucket[:-60]
        if event.type == EventType.FILE_CHANGED.value:
            path = event.data.get("path")
            if path:
                files = self._files.setdefault(task_id, [])
                entry = str(path)
                if entry not in files:
                    files.append(entry)

    async def _sync_project_store(
        self,
        project_id: str | None,
        *,
        task_id: str | None = None,
        conversation_id: str | None = None,
        refresh_tree: bool = False,
    ) -> None:
        """Mirror live state into the project's ``.solo`` store.

        Best-effort by design: a project directory that has become read-only
        must never break task execution, so every failure is logged and
        swallowed.
        """
        if self._store is None or project_id is None:
            return
        try:
            async with self._session_factory() as session:
                project = await ProjectRepository(session).get(project_id)
            if project is None:
                return
            if task_id is not None:
                await self._store.record_task(project, task_id)
            if conversation_id is not None:
                await self._store.record_session(project, conversation_id)
            if refresh_tree:
                await self._store.refresh(project)
        except Exception:  # noqa: BLE001 - the store never breaks a task
            logger.warning(
                "project store sync failed for project %s", project_id, exc_info=True
            )

    async def _narrate(
        self,
        event_type: str,
        message: str,
        *,
        task_id: str | None,
        project_id: str | None,
        data: dict | None = None,
    ) -> None:
        """Route only milestones to the voice channel.

        Tool calls are never narrated: the user asked for concise summaries of
        what the agent is doing, not a running commentary of every operation.
        """
        if self._narration is None:
            return
        if event_type == EventType.PROGRESS_SUMMARY.value:
            await self._narration.announce(
                message,
                kind="progress",
                priority=int(Priority.PROGRESS),
                task_id=task_id,
                project_id=project_id,
            )
        elif event_type == EventType.ERROR.value:
            await self._narration.announce(
                message,
                kind="error",
                priority=int(Priority.CRITICAL),
                task_id=task_id,
                project_id=project_id,
            )

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
        await self._narrate(
            type, message, task_id=task_id, project_id=project_id, data=data
        )
        await self._observe_milestone(
            task_id=task_id,
            project_id=project_id,
            event_type=type,
            message=message,
            data=data,
        )

    async def _observe_milestone(
        self,
        *,
        task_id: str | None,
        project_id: str | None,
        event_type: str,
        message: str,
        data: dict | None = None,
    ) -> None:
        """Feed one event to the milestone tracker and persist any change.

        The tracker decides whether the event justifies a phase transition; most
        events do not, which is the point — a milestone means something changed.
        """
        if self._milestones is None or task_id is None:
            return
        instruction: str | None = None
        async with self._session_factory() as session:
            task = await TaskRepository(session).get(task_id)
        if task is not None:
            instruction = task.instruction
        changed = await self._milestones.observe(
            task_id=task_id,
            project_id=project_id,
            event_type=event_type,
            message=message,
            data=data,
            instruction=instruction,
        )
        if changed is not None:
            await self._persist_milestones(project_id)

    async def _persist_milestones(self, project_id: str | None) -> None:
        """Write the milestone snapshot into the project store.

        Separate from the live broadcast on purpose: the broadcast serves the UI,
        this is the durable record a later voice session can read on reconnect.
        """
        if self._milestones is None or self._store is None or project_id is None:
            return
        async with self._session_factory() as session:
            project = await ProjectRepository(session).get(project_id)
        if project is None:
            return
        await asyncio.to_thread(
            self._store.write_milestones, project, self._milestones.snapshot()
        )

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
        # Read first, in its own session: the milestone chain is closed before
        # the row is written, and closing it touches the store and possibly the
        # Orchestrator model, neither of which belongs inside a database
        # transaction.
        async with self._session_factory() as session:
            task = await TaskRepository(session).get(task_id)
            if task is None:
                return
            # Never overwrite a terminal state. This closes the race where a
            # shutdown cancellation arrives just after a task completed.
            if TaskStatus(task.status) in TERMINAL_STATUSES:
                return
            task_result_summary = result_summary or task.result_summary
            task_error = error or task.error

        # Close the milestone chain *before* the row becomes terminal. The chain
        # is part of the outcome: a client that observes a finished task must
        # never then read a milestone still marked "in progress". Closing it
        # first also means the durable snapshot is already final by the time the
        # terminal status is visible anywhere.
        if status in TERMINAL_STATUSES and self._milestones is not None:
            await self._milestones.finish(
                task_id=task_id,
                project_id=project_id,
                status=status.value,
                summary=task_result_summary,
                error=task_error,
            )
            await self._persist_milestones(project_id)

        async with self._session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get(task_id)
            if task is None:
                return
            # Re-checked under the write session: a concurrent settlement may
            # have won the race while milestones were being closed.
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

        if status in TERMINAL_STATUSES:
            # Write the finished task into the project store *before* notifying
            # any client, so a UI that shows "completed" can always read the
            # record from disk.
            await self._sync_project_store(
                project_id, task_id=task_id, refresh_tree=True
            )

        await self._bus.publish({"channel": "task", "payload": payload})
        await self._emit(
            task_id=task_id,
            project_id=project_id,
            type=EventType.TASK_STATUS_CHANGED.value,
            message=f"Task status: {status.value}",
            data={"status": status.value},
        )

        if status in TERMINAL_STATUSES:
            # Summaries, static checks and queue advancement are enhancements:
            # they run after the user is told the task finished, never in front
            # of the notification. The milestone chain was already closed above,
            # before the row became terminal.

            # Say the outcome once, whatever the outcome is. The narration
            # service drops a duplicate, so a richer summary that arrives next
            # simply supersedes it.
            if self._narration is not None:
                outcome = {
                    TaskStatus.COMPLETED: "The task is complete.",
                    TaskStatus.CANCELLED: "The task was cancelled.",
                    TaskStatus.FAILED: "The task failed.",
                }.get(status)
                if outcome:
                    await self._narration.announce(
                        outcome,
                        kind="outcome",
                        priority=int(Priority.IMPORTANT),
                        task_id=task_id,
                        project_id=project_id,
                    )

            post = asyncio.create_task(
                self._after_task_settled(project_id, task_id),
                name=f"post-settle-{task_id[:8]}",
            )
            self._post_tasks.add(post)
            post.add_done_callback(self._post_tasks.discard)

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
