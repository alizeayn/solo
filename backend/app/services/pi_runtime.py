"""Solo's own, isolated Pi Agent runtime.

**Solo never uses the Pi Agent installed on the host.** It installs, owns and
invokes its own copy, with its own configuration directory, so:

* the desktop Pi installation is never read, written or executed;
* Solo keeps working when ``pi`` is not on ``PATH`` at all (a background
  process, a different shell, a container, systemd);
* credentials, model selection and project-trust decisions are Solo's alone.

Two directories, both inside Solo's data directory:

```
<data>/pi-runtime/          npm prefix — the installed package
│   node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js
│   node_modules/.bin/pi
│   runtime.json            install manifest (versions, node path, timestamps)
└──
<data>/pi/agent/            PI_CODING_AGENT_DIR — Solo's Pi configuration
    auth.json               credentials written through Solo's Settings UI
    settings.json           isolated defaults (project trust, no telemetry)
    models-store.json       Pi's own fetched catalog
```

Why the executable is not taken from ``PATH``: on the development machine ``pi``
lived under an nvm directory that is only on ``PATH`` while nvm is active, so a
background-started Solo could not find it — and a bare ``PATH`` lookup could
equally have picked up the user's own installation silently. :meth:`resolve_argv`
therefore returns an **absolute** interpreter and script path, or nothing.

Invoking ``node <cli.js>`` directly rather than the ``.bin/pi`` shim also removes
a hidden dependency: the shim's shebang is ``#!/usr/bin/env node``, which needs
``node`` on ``PATH``. Passing the resolved Node binary explicitly means the only
external requirement is a Node installation, discovered once and recorded in the
manifest.

A note on the model catalog: a fresh, *unauthenticated* agent directory reports
no models, which is why an earlier version of Solo reused the host's Pi
configuration. With a credential stored, the package's bundled provider catalog
is used and models appear (verified: 401 OpenRouter models from a clean agent
directory). Isolation therefore costs nothing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Settings

logger = logging.getLogger(__name__)

#: The npm package Solo depends on.
PI_PACKAGE = "@earendil-works/pi-coding-agent"
#: Pinned so installs are reproducible and an update can detect a change.
#: Bump deliberately after checking the RPC protocol still matches
#: (see "Pi Agent Docs/20-solo-integration.md").
PI_PACKAGE_VERSION = "1.1.0"
#: Where the CLI entry point lives inside the installed package.
CLI_RELATIVE = Path("node_modules") / PI_PACKAGE / "dist" / "bundle" / "cli.js"
#: Default install/verify timeouts.
INSTALL_TIMEOUT = 600.0
VERIFY_TIMEOUT = 90.0

#: Isolated defaults written into Solo's own agent directory.
#: `defaultProjectTrust` may only be set in the agent directory, so this is the
#: right place for it — and `never` means a project cannot load executable
#: extensions without an explicit opt-in.
AGENT_SETTINGS: dict[str, Any] = {
    "defaultProjectTrust": "never",
    "quietStartup": "header",
}


@dataclass(frozen=True)
class PiRuntimeLayout:
    """Every path Solo owns for the Pi runtime."""

    runtime_dir: Path
    agent_dir: Path

    @property
    def cli_js(self) -> Path:
        return self.runtime_dir / CLI_RELATIVE

    @property
    def shim(self) -> Path:
        return self.runtime_dir / "node_modules" / ".bin" / "pi"

    @property
    def package_dir(self) -> Path:
        return self.runtime_dir / "node_modules" / PI_PACKAGE

    @property
    def manifest(self) -> Path:
        return self.runtime_dir / "runtime.json"

    @property
    def auth_file(self) -> Path:
        return self.agent_dir / "auth.json"

    @property
    def settings_file(self) -> Path:
        return self.agent_dir / "settings.json"


@dataclass
class InstallResult:
    ok: bool
    message: str
    detail: str | None = None
    version: str | None = None
    duration_ms: int = 0
    output: str | None = None


@dataclass
class RuntimeStatus:
    """A truthful description of Solo's own Pi runtime."""

    installed: bool
    #: True only when the runtime was actually started and answered a command.
    verified: bool
    #: ``managed`` (Solo's own copy), ``external`` (an explicit override), ``none``.
    source: str
    #: Display path for the executable actually invoked.
    executable: str | None
    #: Full argv prefix used to spawn Pi.
    argv: list[str] = field(default_factory=list)
    version: str | None = None
    node: str | None = None
    node_available: bool = False
    runtime_dir: str = ""
    agent_dir: str = ""
    detail: str = ""
    last_error: str | None = None
    installed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            # `available` mirrors `installed` for the health endpoint and older
            # clients; `installed` is the precise term for Solo's own runtime.
            "available": self.installed,
            "installed": self.installed,
            "verified": self.verified,
            "source": self.source,
            "executable": self.executable,
            "version": self.version,
            "node": self.node,
            "node_available": self.node_available,
            "runtime_dir": self.runtime_dir,
            "agent_dir": self.agent_dir,
            "detail": self.detail,
            "last_error": self.last_error,
            "installed_at": self.installed_at,
            "isolated": self.source == "managed",
        }


class PiRuntimeError(RuntimeError):
    """Raised for runtime install/initialise failures."""


class PiRuntime:
    """Locate, install and verify Solo's isolated Pi Agent."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def layout(self) -> PiRuntimeLayout:
        return PiRuntimeLayout(
            runtime_dir=self.runtime_dir(),
            agent_dir=self.agent_dir(),
        )

    def runtime_dir(self) -> Path:
        override = (self._settings.pi_runtime_dir or "").strip()
        base = Path(override).expanduser() if override else self._settings.app_data_dir / "pi-runtime"
        return base.resolve() if base.is_absolute() else (Path.cwd() / base).resolve()

    def agent_dir(self) -> Path:
        """Solo's own Pi configuration directory — never ``~/.pi/agent``."""
        override = (self._settings.pi_agent_dir or "").strip()
        if override:
            base = Path(override).expanduser()
        else:
            base = self._settings.app_data_dir / "pi" / "agent"
        return base.resolve() if base.is_absolute() else (Path.cwd() / base).resolve()

    # ------------------------------------------------------------------ #
    # Manifest
    # ------------------------------------------------------------------ #
    def read_manifest(self) -> dict[str, Any]:
        try:
            data = json.loads(self.layout().manifest.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write_manifest(self, **updates: Any) -> None:
        layout = self.layout()
        payload = self.read_manifest()
        payload.update(updates)
        payload.setdefault("package", PI_PACKAGE)
        payload["agent_dir"] = str(layout.agent_dir)
        layout.runtime_dir.mkdir(parents=True, exist_ok=True)
        temporary = layout.manifest.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, layout.manifest)

    # ------------------------------------------------------------------ #
    # Executable resolution
    # ------------------------------------------------------------------ #
    def node_path(self, *, persist: bool = True) -> str | None:
        """Resolve Node, preferring the path recorded at install time."""
        recorded = (self.read_manifest().get("node") or "").strip()
        if recorded and Path(recorded).is_file() and os.access(recorded, os.X_OK):
            return recorded
        found = shutil.which("node")
        if found and persist and self.layout().runtime_dir.is_dir():
            try:
                self._write_manifest(node=found)
            except OSError:  # pragma: no cover - read-only runtime dir
                logger.debug("could not record the node path", exc_info=True)
        return found

    def managed_cli(self) -> Path | None:
        """The CLI entry point of Solo's own installation, if present."""
        cli = self.layout().cli_js
        return cli if cli.is_file() else None

    def external_executable(self) -> Path | None:
        """An explicitly configured executable, if it is a real absolute path.

        A bare command name is deliberately **rejected**: that is exactly the
        silent PATH fallback this module exists to prevent.
        """
        raw = (self._settings.pi_executable or "").strip()
        if not raw:
            return None
        candidate = Path(raw).expanduser()
        if os.sep not in raw and (os.altsep is None or os.altsep not in raw):
            return None
        return candidate if candidate.is_file() else None

    def resolve_argv(self) -> list[str] | None:
        """The full argv prefix for spawning Pi, or ``None`` if unusable.

        Returns an absolute interpreter + script for Solo's own installation, or
        an explicitly configured executable. It never performs a bare ``PATH``
        lookup for ``pi``.
        """
        external = self.external_executable()
        if external is not None:
            if external.suffix == ".js":
                node = self.node_path()
                return [node, str(external)] if node else None
            return [str(external)]

        cli = self.managed_cli()
        if cli is None:
            return None
        node = self.node_path()
        if node is None:
            return None
        return [node, str(cli)]

    def source(self) -> str:
        if self.external_executable() is not None:
            return "external"
        return "managed" if self.managed_cli() is not None else "none"

    def is_installed(self) -> bool:
        return self.resolve_argv() is not None

    def env(self) -> dict[str, str]:
        """Environment for every Pi subprocess Solo starts.

        ``PI_CODING_AGENT_DIR`` is always Solo's own directory. Nothing is
        inherited from the host Pi installation.
        """
        return {
            "PI_CODING_AGENT_DIR": str(self.agent_dir()),
            "PI_SKIP_VERSION_CHECK": "1",
        }

    #: Flags Solo always passes. RPC mode is required for a long-lived session,
    #: and the rest make the harness reproducible and safe without a terminal.
    HARNESS_FLAGS: tuple[str, ...] = (
        "--mode",
        "rpc",
        "--no-session",
        "--no-approve",
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
        "--no-mcp",
        "--no-context-files",
    )

    def rpc_argv(self, extra: list[str] | None = None) -> list[str] | None:
        """Full argv for a one-shot RPC probe of Solo's own runtime."""
        prefix = self.resolve_argv()
        if prefix is None:
            return None
        return [*prefix, *self.HARNESS_FLAGS, *(extra or [])]

    # ------------------------------------------------------------------ #
    # Initialisation
    # ------------------------------------------------------------------ #
    def initialize(self) -> None:
        """Create Solo's runtime and agent directories with restrictive modes."""
        layout = self.layout()
        for directory in (layout.runtime_dir, layout.agent_dir):
            directory.mkdir(parents=True, exist_ok=True)
            try:
                directory.chmod(0o700)
            except OSError:  # pragma: no cover - non-POSIX
                pass

        # Isolated defaults. Written once; a user edit is preserved.
        if not layout.settings_file.exists():
            layout.settings_file.write_text(
                json.dumps(AGENT_SETTINGS, indent=2) + "\n", encoding="utf-8"
            )
            try:
                layout.settings_file.chmod(0o600)
            except OSError:  # pragma: no cover
                pass
        if not layout.auth_file.exists():
            # Pi expects the file to exist; an empty object means "no credentials".
            layout.auth_file.write_text("{}\n", encoding="utf-8")
            try:
                layout.auth_file.chmod(0o600)
            except OSError:  # pragma: no cover
                pass

    # ------------------------------------------------------------------ #
    # Install
    # ------------------------------------------------------------------ #
    async def install(self, *, force: bool = False, timeout: float = INSTALL_TIMEOUT) -> InstallResult:
        """Install or upgrade Solo's own Pi Agent copy.

        Idempotent: an existing installation is reused unless ``force`` is set.
        Node is resolved first so a failure is reported before npm runs.
        """
        started = time.monotonic()
        layout = self.layout()

        if self.external_executable() is not None:
            return InstallResult(
                ok=True,
                message=(
                    "Using an explicitly configured Pi executable; Solo did not "
                    "install its own copy."
                ),
                detail=str(self.external_executable()),
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        node = self.node_path(persist=False)
        if node is None:
            return InstallResult(
                ok=False,
                message="Node.js was not found, so Pi Agent cannot be installed.",
                detail=(
                    "Install Node.js 20 or newer (https://nodejs.org) and run "
                    "'./solo.sh install' again."
                ),
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        npm = shutil.which("npm")
        if npm is None:
            return InstallResult(
                ok=False,
                message="npm was not found, so Pi Agent cannot be installed.",
                detail="Install npm alongside Node.js, then run './solo.sh install' again.",
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        if not force and self.managed_cli() is not None:
            version = await self._read_version()
            return InstallResult(
                ok=True,
                message=f"Pi Agent {version or ''} is already installed in Solo's runtime.".strip(),
                detail=str(layout.runtime_dir),
                version=version,
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        try:
            self.initialize()
        except OSError as exc:
            return InstallResult(
                ok=False,
                message=f"Could not create Solo's runtime directory: {exc.strerror or exc}",
                detail=str(layout.runtime_dir),
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        args = [
            npm,
            "install",
            "--prefix",
            str(layout.runtime_dir),
            "--no-audit",
            "--no-fund",
            "--loglevel",
            "error",
        ]
        if force:
            args.append("--force")
        args.append(f"{PI_PACKAGE}@{PI_PACKAGE_VERSION}")

        logger.info("installing %s into %s", PI_PACKAGE, layout.runtime_dir)
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(layout.runtime_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
            return_code = process.returncode or 0
        except asyncio.TimeoutError:
            process.kill()
            return InstallResult(
                ok=False,
                message=f"Installing Pi Agent timed out after {int(timeout)}s.",
                detail="Check your network connection and try again.",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except OSError as exc:
            return InstallResult(
                ok=False,
                message=f"Could not run npm: {exc.strerror or exc}",
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        output = (stdout or b"").decode("utf-8", "replace").strip()[-2000:]
        duration = int((time.monotonic() - started) * 1000)

        if return_code != 0 or self.managed_cli() is None:
            detail = output or f"npm exited with code {return_code}."
            self._record_failure(detail)
            return InstallResult(
                ok=False,
                message="Pi Agent could not be installed into Solo's runtime.",
                detail=detail,
                duration_ms=duration,
                output=output or None,
            )

        version = await self._read_version()
        self._write_manifest(
            version=version,
            node=node,
            installed_at=_now(),
            last_error=None,
        )
        logger.info("installed Pi Agent %s into %s", version, layout.runtime_dir)
        return InstallResult(
            ok=True,
            message=f"Pi Agent {version or ''} installed into Solo's runtime.".strip(),
            detail=str(layout.runtime_dir),
            version=version,
            duration_ms=duration,
            output=output or None,
        )

    def _record_failure(self, detail: str) -> None:
        try:
            self._write_manifest(last_error=detail[:1000], last_error_at=_now())
        except OSError:  # pragma: no cover
            logger.debug("could not record the install failure", exc_info=True)

    async def _read_version(self, *, timeout: float = 60.0) -> str | None:
        argv = self.resolve_argv()
        if argv is None:
            return None
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **self.env()},
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except (asyncio.TimeoutError, OSError):
            return None
        if process.returncode != 0:
            return None
        return stdout.decode("utf-8", "replace").strip() or None

    # ------------------------------------------------------------------ #
    # Status and verification
    # ------------------------------------------------------------------ #
    async def status(self, *, verify: bool = False) -> RuntimeStatus:
        """Describe the runtime, optionally proving it can actually start."""
        layout = self.layout()
        argv = self.resolve_argv()
        source = self.source()
        manifest = self.read_manifest()
        node = self.node_path(persist=True)

        status = RuntimeStatus(
            installed=argv is not None,
            verified=False,
            source=source,
            executable=argv[-1] if argv else None,
            argv=list(argv or []),
            version=manifest.get("version"),
            node=node,
            node_available=node is not None,
            runtime_dir=str(layout.runtime_dir),
            agent_dir=str(layout.agent_dir),
            detail="",
            last_error=manifest.get("last_error"),
            installed_at=manifest.get("installed_at"),
        )

        if argv is None:
            status.detail = self._missing_detail(source)
            return status

        # Read and cache the version once, so a truthful "installed version" is
        # available to the UI without spawning Pi on every status call.
        if not status.version:
            version = await self._read_version()
            if version:
                status.version = version
                try:
                    self._write_manifest(version=version, node=node)
                except OSError:  # pragma: no cover - read-only runtime dir
                    logger.debug("could not cache the Pi version", exc_info=True)

        if source == "external":
            status.detail = (
                "Using an explicitly configured Pi executable. Solo's own isolated "
                f"runtime was not used. Unset PI_EXECUTABLE to use Solo's copy."
            )
        else:
            status.detail = f"Solo's isolated Pi Agent is installed at {layout.runtime_dir}."

        if verify:
            started = time.monotonic()
            ok, detail = await self.rpc_probe(
                command={"type": "get_state"}, timeout=VERIFY_TIMEOUT
            )
            status.verified = ok
            if ok:
                status.version = status.version or await self._read_version()
                status.detail += f" Verified in {int((time.monotonic() - started) * 1000)} ms."
                status.last_error = None
            else:
                status.detail = f"Pi did not start: {detail}"
                status.last_error = detail
        return status

    async def rpc_probe(
        self,
        *,
        command: dict[str, Any],
        timeout: float = VERIFY_TIMEOUT,
        cwd: str | None = None,
    ) -> tuple[bool, str]:
        """Start Solo's Pi runtime in RPC mode and run one command.

        Used to prove the isolated runtime can actually start, rather than
        merely that a file exists on disk.
        """
        argv = self.resolve_argv()
        if argv is None:
            return False, self._missing_detail(self.source())

        # Imported lazily: `adapters` imports this module through its package
        # initialiser, so a module-level import here would be circular.
        from ..adapters.pi_rpc import PiRpcClient, PiRpcError, PiUnavailableError

        # RPC mode is mandatory: without --mode rpc the process starts the
        # interactive interface and never answers a command.
        probe_argv = [*argv, *self.HARNESS_FLAGS]
        workdir = Path(cwd) if cwd else self.runtime_dir()
        workdir.mkdir(parents=True, exist_ok=True)
        client = PiRpcClient(
            probe_argv,
            cwd=str(workdir),
            env=self.env(),
            label="pi-runtime-probe",
        )
        try:
            await client.start()
            await client.call(command, timeout=timeout)
        except PiUnavailableError as exc:
            return False, str(exc)
        except PiRpcError as exc:
            return False, str(exc)
        except Exception as exc:  # noqa: BLE001 - never raise from a probe
            logger.warning("Pi runtime probe failed", exc_info=True)
            return False, f"{type(exc).__name__}: {exc}"
        finally:
            await client.close(grace=5.0)
        return True, "Solo's Pi Agent started and answered a command."

    def _missing_detail(self, source: str) -> str:
        layout = self.layout()
        if (self._settings.pi_executable or "").strip() and self.external_executable() is None:
            return (
                "PI_EXECUTABLE is set to a command name, which Solo refuses to resolve "
                "through PATH so that it can never silently use the host's Pi Agent. "
                "Set it to an absolute path, or leave it empty to use Solo's own runtime."
            )
        if not layout.runtime_dir.is_dir():
            return (
                "Solo's isolated Pi Agent is not installed yet. Run './solo.sh install' "
                "or install it from Settings."
            )
        if self.managed_cli() is None:
            return (
                f"Solo's Pi runtime at {layout.runtime_dir} is incomplete (no CLI found). "
                "Reinstall it from Settings or with './solo.sh install'."
            )
        if self.node_path(persist=False) is None:
            return (
                "Node.js was not found, so Solo's Pi Agent cannot start. "
                "Install Node.js 20 or newer and restart Solo."
            )
        return "Solo's isolated Pi Agent runtime is unavailable."


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def node_version(node: str | None) -> str | None:
    """Best-effort Node version string, for diagnostics."""
    if not node:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - fixed argument list
            [node, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return (result.stdout or "").strip() or None
