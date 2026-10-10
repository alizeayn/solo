"""Application configuration.

All configuration is environment-driven (12-factor) and validated by
pydantic-settings. Secrets are intentionally *not* part of this module: API
keys and the admin password live in the encrypted secrets store managed by
``app.security.SecretCipher`` and the settings repository.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- General ---
    app_env: str = Field(default="development", description="development|production")
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    # Coding-agent backend: "mock" (Phase 1) or "pi" (Phase 2).
    agent_backend: str = "mock"
    # Seconds between simulated steps in the mock coding agent. Tests set 0.
    mock_step_delay: float = 0.35

    # --- Storage ---
    # Root directory for the SQLite DB, encrypted secrets and workspaces.
    app_data_dir: Path = Path("./data")
    # Optional directory containing the built frontend (served by the backend).
    frontend_dist: Path | None = None

    # --- Sessions / auth ---
    session_ttl_hours: int = 168  # 7 days
    # Optional bootstrap password consumed once on first start. When set and no
    # user exists yet, an admin account is created from it. Used by install.sh.
    admin_password: str | None = None

    # --- Uploads ---
    max_upload_mb: int = 200
    max_zip_entries: int = 20000
    max_uncompressed_mb: int = 2048

    # --- Retention ---
    # Cap on retained raw diagnostic log characters per task.
    raw_log_max_chars: int = 200_000

    # ---------- Derived paths ----------

    @property
    def db_path(self) -> Path:
        return self.app_data_dir / "app.db"

    @property
    def workspaces_dir(self) -> Path:
        return self.app_data_dir / "workspaces"

    @property
    def key_path(self) -> Path:
        return self.app_data_dir / "master.key"

    @property
    def secrets_path(self) -> Path:
        return self.app_data_dir / "secrets.enc"

    @property
    def uploads_dir(self) -> Path:
        return self.app_data_dir / "uploads"

    @property
    def bootstrap_password_file(self) -> Path:
        return self.app_data_dir / "initial-admin-password"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_uncompressed_bytes(self) -> int:
        return self.max_uncompressed_mb * 1024 * 1024

    def ensure_directories(self) -> None:
        """Create the data directory tree with restrictive permissions."""
        for path in (
            self.app_data_dir,
            self.workspaces_dir,
            self.uploads_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
            try:
                path.chmod(0o700)
            except OSError:  # pragma: no cover - non-POSIX / restricted FS
                pass


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear the cached settings (used by tests)."""
    get_settings.cache_clear()
