"""Static checks (Pyright) for the project the agent just changed.

Solo's harness uses Pi to *make* changes and Pyright to *verify* them. A check
never blocks a task: it runs after the agent settles, is bounded by file count
and wall clock, and reports a truthful outcome — including "skipped" when the
project has no Python or Pyright is not installed.

Pyright is invoked through its documented CLI with ``--outputjson`` so results
are structured rather than scraped from human-readable text.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Settings
from ..domain import CheckOutcome

logger = logging.getLogger(__name__)

#: Files handed to Pyright in one run when no explicit targets are given.
MAX_TARGET_FILES = 300
#: Diagnostics retained per run.
MAX_DIAGNOSTICS = 100
#: Directories never scanned for Python sources.
SKIP_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "venv",
        ".venv",
        "__pycache__",
        "dist",
        "build",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "site-packages",
        ".solo",
    }
)


@dataclass
class Diagnostic:
    file: str
    line: int
    column: int
    severity: str
    message: str
    rule: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "severity": self.severity,
            "message": self.message,
            "rule": self.rule,
        }


@dataclass
class CheckResult:
    tool: str
    outcome: str
    summary: str
    error_count: int = 0
    warning_count: int = 0
    files_checked: int = 0
    duration_ms: int = 0
    command: str | None = None
    output: str | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.outcome == CheckOutcome.PASSED.value

    def to_dict(self, *, include_diagnostics: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tool": self.tool,
            "outcome": self.outcome,
            "summary": self.summary,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "files_checked": self.files_checked,
            "duration_ms": self.duration_ms,
            "command": self.command,
            "output": self.output,
            "passed": self.passed,
        }
        if include_diagnostics:
            payload["diagnostics"] = [item.to_dict() for item in self.diagnostics]
        return payload


def find_python_files(root: Path, *, limit: int = MAX_TARGET_FILES) -> list[str]:
    """Bounded scan for Python sources, relative to *root*."""
    found: list[str] = []
    if not root.is_dir():
        return found
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            name for name in dirnames if name not in SKIP_DIRS and not name.startswith(".")
        )
        for name in sorted(filenames):
            if name.endswith((".py", ".pyi")):
                relative = os.path.relpath(os.path.join(dirpath, name), root)
                found.append(relative)
                if len(found) >= limit:
                    return found
    return found


class ChecksService:
    """Runs static analysis over a project directory."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # ------------------------------------------------------------------ #
    # Availability
    # ------------------------------------------------------------------ #
    def executable(self) -> str | None:
        return shutil.which(self._settings.pyright_executable)

    def available(self) -> bool:
        return bool(self._settings.checks_enabled) and self.executable() is not None

    def status(self) -> dict[str, Any]:
        path = self.executable()
        return {
            "enabled": self._settings.checks_enabled,
            "available": path is not None,
            "tool": "pyright",
            "executable": path,
            "detail": (
                f"Pyright found at {path}"
                if path
                else (
                    "Pyright is not installed. Install it with "
                    "'./venv/bin/pip install pyright' to enable static checks."
                )
            ),
        }

    # ------------------------------------------------------------------ #
    # Running
    # ------------------------------------------------------------------ #
    async def run_for_project(
        self,
        root: Path,
        *,
        changed_files: list[str] | None = None,
    ) -> CheckResult:
        """Run Pyright over *root*, preferring the files the agent changed."""
        started = time.monotonic()
        if not self._settings.checks_enabled:
            return self._skipped("Static checks are disabled in Settings.", started)
        executable = self.executable()
        if executable is None:
            return self._skipped(
                "Pyright is not installed, so static checks were skipped.", started
            )
        if not root.is_dir():
            return self._error("The project directory is not available.", started)

        targets = self._targets(root, changed_files)
        if targets is None:
            return self._skipped(
                "No Python files found in this project, so Pyright had nothing to check.",
                started,
            )

        command = [executable, "--outputjson", *targets]
        timeout = float(self._settings.pyright_timeout_seconds)
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
            return_code: int | None = process.returncode
        except asyncio.TimeoutError:
            with_suppress_kill(process)
            return self._error(
                f"Pyright did not finish within {int(timeout)}s and was stopped.", started
            )
        except OSError as exc:
            return self._error(f"Could not start Pyright: {exc.strerror or exc}", started)

        duration_ms = int((time.monotonic() - started) * 1000)
        text = stdout.decode("utf-8", "replace")
        stderr_text = stderr.decode("utf-8", "replace").strip()

        payload: dict[str, Any] | None = None
        try:
            parsed = json.loads(text)
            payload = parsed if isinstance(parsed, dict) else None
        except ValueError:
            payload = None

        if payload is None:
            return CheckResult(
                tool="pyright",
                outcome=CheckOutcome.ERROR.value,
                summary=(
                    "Pyright did not return parseable JSON"
                    + (f": {stderr_text[:200]}" if stderr_text else ".")
                ),
                duration_ms=duration_ms,
                command=" ".join(command),
                output=(stderr_text or text)[-1000:] or None,
                files_checked=len(targets),
            )

        diagnostics = self._parse_diagnostics(payload, root)
        errors = sum(1 for item in diagnostics if item.severity == "error")
        warnings = sum(1 for item in diagnostics if item.severity == "warning")

        if errors:
            outcome = CheckOutcome.FAILED.value
            plural = "error" if errors == 1 else "errors"
            summary = f"Pyright found {errors} {plural}"
            if warnings:
                summary += f" and {warnings} warning(s)"
            summary += f" in {len(targets)} file(s)."
        else:
            outcome = CheckOutcome.PASSED.value
            summary = f"Pyright found no type errors in {len(targets)} file(s)."
            if warnings:
                summary += f" ({warnings} warning(s).)"

        if return_code not in (0, 1) and not diagnostics:
            outcome = CheckOutcome.ERROR.value
            summary = f"Pyright exited with code {return_code}."

        return CheckResult(
            tool="pyright",
            outcome=outcome,
            summary=summary,
            error_count=errors,
            warning_count=warnings,
            files_checked=len(targets),
            duration_ms=duration_ms,
            command=" ".join(command),
            output=stderr_text or None,
            diagnostics=diagnostics,
        )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _targets(self, root: Path, changed_files: list[str] | None) -> list[str] | None:
        """Which files to check: the changed ones, else the project's sources."""
        if changed_files:
            candidates: list[str] = []
            for item in changed_files:
                if not item.endswith((".py", ".pyi")):
                    continue
                candidate = (root / item).resolve()
                try:
                    candidate.relative_to(root.resolve())
                except ValueError:
                    continue
                if candidate.is_file():
                    candidates.append(item)
            if candidates:
                return candidates[:MAX_TARGET_FILES]

        found = find_python_files(root, limit=MAX_TARGET_FILES)
        return found or None

    @staticmethod
    def _parse_diagnostics(payload: dict[str, Any], root: Path) -> list[Diagnostic]:
        raw = payload.get("generalDiagnostics")
        if not isinstance(raw, list):
            return []
        diagnostics: list[Diagnostic] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            position = (item.get("range") or {}).get("start") or {}
            file_path = str(item.get("file") or "")
            try:
                relative = str(Path(file_path).resolve().relative_to(root.resolve()))
            except (ValueError, OSError):
                relative = file_path
            diagnostics.append(
                Diagnostic(
                    file=relative,
                    line=int(position.get("line") or 0) + 1,
                    column=int(position.get("character") or 0) + 1,
                    severity=str(item.get("severity") or "error"),
                    message=str(item.get("message") or "").strip()[:500],
                    rule=item.get("rule"),
                )
            )
            if len(diagnostics) >= MAX_DIAGNOSTICS:
                break
        return diagnostics

    def _skipped(self, message: str, started: float) -> CheckResult:
        return CheckResult(
            tool="pyright",
            outcome=CheckOutcome.SKIPPED.value,
            summary=message,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    def _error(self, message: str, started: float) -> CheckResult:
        return CheckResult(
            tool="pyright",
            outcome=CheckOutcome.ERROR.value,
            summary=message,
            duration_ms=int((time.monotonic() - started) * 1000),
        )


def with_suppress_kill(process: asyncio.subprocess.Process | None) -> None:
    """Best-effort kill for a timed-out subprocess."""
    if process is None:  # pragma: no cover - defensive
        return
    try:
        process.kill()
    except (ProcessLookupError, OSError):  # pragma: no cover
        pass
