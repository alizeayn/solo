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

from .version import read_version


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
    app_version: str = Field(default_factory=read_version)
    log_level: str = "INFO"

    # Coding-agent backend: "auto" (Pi when installed, otherwise the
    # simulator), "pi" (require Pi), or "mock".
    agent_backend: str = "auto"
    # Seconds between simulated steps in the mock coding agent. Tests set 0.
    mock_step_delay: float = 0.35

    # --- Pi Agent ---
    # Solo installs and owns its own Pi Agent. The executable is never resolved
    # through PATH, so the host's Pi installation can never be used by accident.
    pi_executable: str | None = None
    #: npm prefix for Solo's own Pi installation. Defaults to <data>/pi-runtime.
    pi_runtime_dir: str | None = None
    #: Pi's configuration directory. Defaults to <data>/pi/agent, which keeps
    #: credentials and the model catalog separate from ~/.pi/agent.
    pi_agent_dir: str | None = None
    #: Trust project-local Pi resources (.pi/settings.json, extensions, skills).
    #: False maps to --no-approve: predictable and safe for a non-interactive run.
    pi_approve_project: bool = False
    # Disable extensions/skills/templates/MCP so the harness is reproducible and
    # produces no unanswerable extension UI requests.
    pi_minimal_harness: bool = True
    # Wall-clock limit for one coding task.
    pi_run_timeout_seconds: int = 1800

    # --- Orchestrator (OpenRouter) ---
    # Reasoning/intent model used for classification, prioritisation and
    # summaries. It is only ever invoked when a key and model are configured.
    orchestrator_enabled: bool = True
    orchestrator_timeout_seconds: float = 45.0
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # --- Voice (ElevenLabs) ---
    # Text to speech for narration and speech to text for input. The
    # Agents Platform is deliberately not used: it would own the
    # conversation loop and answer from its own context instead of from
    # the real task state.
    elevenlabs_base_url: str = "https://api.elevenlabs.io"
    elevenlabs_timeout_seconds: float = 30.0

    # --- Static checks (Pyright) ---
    checks_enabled: bool = True
    pyright_executable: str = "pyright"
    pyright_timeout_seconds: int = 180
    # Run checks automatically after a coding task settles.
    checks_after_task: bool = True

    # --- Storage ---
    # Root directory for the SQLite DB, encrypted secrets and workspaces.
    app_data_dir: Path = Path("./data")
    # Optional directory containing the built frontend (served by the backend).
    frontend_dist: Path | None = None

    # --- Sessions / auth ---
    session_ttl_hours: int = 168  # 7 days
    # Mark the session cookie ``Secure``.
    #   unset (default) -> auto: Secure only when the request is HTTPS, so the
    #                      app works over plain http://localhost without
    #                      silently breaking sign-in.
    #   true            -> always Secure (use behind a TLS proxy).
    #   false           -> never Secure.
    session_cookie_secure: bool | None = None
    # Optional bootstrap password consumed once on first start. When set and no
    # user exists yet, an admin account is created from it. Used by install.sh.
    admin_password: str | None = None

    # --- Network exposure ---
    # Bind address lives above as ``app_host``: "0.0.0.0" (default) serves the
    # local network, "127.0.0.1" restricts Solo to this machine.
    #
    # Comma-separated Host header allow-list. Empty (default) accepts any Host,
    # which is what a LAN deployment needs: the address a phone will use is not
    # known in advance. Set it when Solo is reachable from an untrusted network
    # so a forged Host header cannot poison cookie domains or generated links.
    allowed_hosts: str = ""
    # TLS. Both must be set for Solo to serve HTTPS itself. This is not only
    # about encryption: browsers expose the microphone only in a *secure
    # context*, so voice input cannot work over plain http on a LAN address.
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None

    @property
    def allowed_hosts_list(self) -> list[str]:
        """Host allow-list as a list. Empty means "accept any Host"."""
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    @property
    def https_enabled(self) -> bool:
        """True when Solo terminates TLS itself (both cert and key are set)."""
        return bool(self.ssl_certfile and self.ssl_keyfile)

    # --- Projects ---
    # Name of the per-project metadata directory created inside a project root.
    metadata_dir_name: str = ".solo"
    # Colon-separated extra roots that "Open Project" may read from. Always
    # additive to the built-in defaults (home directory + managed workspaces).
    project_roots: str = ""
    # When True (default), any readable directory may be opened except the
    # always-blocked system paths and the Solo data directory. Set to False to
    # restrict opening to ``project_roots`` plus the built-in defaults.
    allow_any_project_path: bool = True
    # Bounds for the generated project state tree.
    max_tree_depth: int = 10
    max_tree_entries: int = 5000
    # When True, a ``.gitignore`` is written inside the metadata directory so a
    # project's Solo state does not pollute the user's repository by default.
    metadata_write_gitignore: bool = True

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
    def configured_project_roots(self) -> list[Path]:
        """Extra roots the operator has explicitly allowed, from PROJECT_ROOTS."""
        roots: list[Path] = []
        for raw in self.project_roots.split(":"):
            cleaned = raw.strip()
            if not cleaned:
                continue
            try:
                roots.append(Path(cleaned).expanduser().resolve())
            except OSError:  # pragma: no cover - unresolvable path
                continue
        return roots

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
