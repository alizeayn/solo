"""Repository layer: all database access lives behind these classes.

Business logic depends on repositories, never on SQLAlchemy sessions directly,
so the storage engine can be swapped without touching services.
"""

from .conversations import ConversationRepository
from .events import EventRepository
from .projects import ProjectRepository
from .sessions import AuthSessionRepository
from .settings import SettingsRepository
from .tasks import TaskRepository
from .users import UserRepository

__all__ = [
    "ConversationRepository",
    "EventRepository",
    "ProjectRepository",
    "AuthSessionRepository",
    "SettingsRepository",
    "TaskRepository",
    "UserRepository",
]
