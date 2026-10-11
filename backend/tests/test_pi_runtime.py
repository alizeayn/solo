"""Isolation tests for Solo's own Pi Agent runtime.

The acceptance criterion these tests exist for:

    Solo must run its own isolated Pi Agent instance and must never silently
    fall back to the global desktop installation.

They assert four independent guarantees:

1. the executable is never resolved through ``PATH``;
2. Solo's Pi configuration directory is never ``~/.pi/agent``;
3. every Pi subprocess receives Solo's own ``PI_CODING_AGENT_DIR``;
4. installing, initialising or reconfiguring Solo's runtime never writes to the
   host's Pi configuration.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from app.adapters.pi_agent import probe_pi_runtime
from app.adapters.pi_session import PiLaunchConfig, build_pi_argv
from app.config import Settings
from app.services.pi_runtime import (
    AGENT_SETTINGS,
    PI_PACKAGE,
    PiRuntime,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
FAKE_NPM = """#!/bin/sh
# A stand-in for npm that creates the layout the installer expects.
PREFIX=""
FAIL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="$2"; shift 2 ;;
    --fail)   FAIL=1; shift ;;
    *) shift ;;
  esac
done
if [ -z "$PREFIX" ]; then echo "no --prefix given" >&2; exit 1; fi
if [ "$FAIL" = "1" ]; then echo "fake npm: simulated network failure" >&2; exit 1; fi
DIR="$PREFIX/node_modules/@earendil-works/pi-coding-agent/dist/bundle"
mkdir -p "$DIR"
printf '// fake cli\\n' > "$DIR/cli.js"
echo "fake npm: installed %s"
exit 0
"""


@pytest.fixture
def fake_npm(tmp_path, monkeypatch) -> Path:
    """Put a fake npm (and node) on PATH for installer tests."""
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    npm = bindir / "npm"
    npm.write_text(FAKE_NPM)
    npm.chmod(npm.stat().st_mode | stat.S_IXUSR)
    node = bindir / "node"
    node.write_text("#!/bin/sh\necho v99.0.0-fake\n")
    node.chmod(node.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    return bindir


def make_managed_runtime(settings: Settings, fake_pi: str) -> PiRuntime:
    """Build a Solo-managed runtime whose 'node' execs the protocol fake.

    This exercises the real managed code path — an absolute interpreter plus an
    absolute script — without installing the actual Pi package.
    """
    runtime = PiRuntime(settings)
    layout = runtime.layout()
    layout.cli_js.parent.mkdir(parents=True, exist_ok=True)
    layout.cli_js.write_text("// stands in for the Pi CLI bundle\n")
    layout.runtime_dir.mkdir(parents=True, exist_ok=True)
    shim = layout.runtime_dir / "fake-node"
    shim.write_text(f'#!/bin/sh\nshift\nexec "{fake_pi}" "$@"\n')
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    layout.manifest.write_text(
        json.dumps({"package": PI_PACKAGE, "node": str(shim), "version": "1.1.0-fake"})
    )
    return runtime


# --------------------------------------------------------------------------- #
# 1. The executable is never resolved through PATH
# --------------------------------------------------------------------------- #
def test_path_is_never_used_even_when_pi_is_available(settings_factory, tmp_path, monkeypatch):
    """A global `pi` on PATH must not be picked up, silently or otherwise."""
    bindir = tmp_path / "global-bin"
    bindir.mkdir()
    global_pi = bindir / "pi"
    global_pi.write_text("#!/bin/sh\necho GLOBAL-PI-USED\n")
    global_pi.chmod(global_pi.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")

    settings = settings_factory(pi_executable=None)
    runtime = PiRuntime(settings)

    assert runtime.resolve_argv() is None, "Solo must not fall back to a PATH lookup"
    assert runtime.source() == "none"
    assert not runtime.is_installed()

    status = asyncio_run(runtime.status())
    assert status.installed is False
    assert status.source == "none"
    assert "not installed" in status.detail


def test_a_bare_command_name_is_refused(settings_factory):
    """PI_EXECUTABLE=pi is ambiguous, so Solo refuses it rather than resolving it."""
    runtime = PiRuntime(settings_factory(pi_executable="pi"))
    assert runtime.external_executable() is None
    assert runtime.resolve_argv() is None

    status = asyncio_run(runtime.status())
    assert status.source == "none"
    assert "refuses to resolve" in status.detail


def test_an_explicit_absolute_override_is_honoured_but_labelled(settings_factory, tmp_path):
    """An operator's explicit path is allowed, and never reported as isolated."""
    executable = tmp_path / "my-pi"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

    runtime = PiRuntime(settings_factory(pi_executable=str(executable)))
    assert runtime.resolve_argv() == [str(executable)]
    assert runtime.source() == "external"

    status = asyncio_run(runtime.status())
    assert status.source == "external"
    assert "not used" in status.detail or "isolated" in status.detail


def test_managed_runtime_resolves_to_an_absolute_interpreter_and_script(
    settings_factory, fake_pi
):
    runtime = make_managed_runtime(settings_factory(pi_executable=None), fake_pi)
    argv = runtime.resolve_argv()

    assert argv is not None
    assert len(argv) == 2, "the managed runtime is [node, cli.js]"
    assert Path(argv[0]).is_absolute()
    assert Path(argv[1]).is_absolute()
    assert argv[1].endswith("cli.js")
    assert runtime.source() == "managed"
    assert runtime.is_installed() is True

    # …and the argv actually starts Pi.
    full = build_pi_argv(argv, PiLaunchConfig(provider="fake", model="fake-model"))
    assert full[:2] == argv
    assert "--mode" in full and "rpc" in full


# --------------------------------------------------------------------------- #
# 2. Solo's configuration directory is its own
# --------------------------------------------------------------------------- #
def test_agent_dir_lives_inside_solos_data_directory(settings_factory):
    settings = settings_factory(pi_agent_dir=None)
    runtime = PiRuntime(settings)
    agent = runtime.agent_dir()

    assert agent == (settings.app_data_dir / "pi" / "agent").resolve()
    assert str(agent).startswith(str(settings.app_data_dir.resolve()))
    assert not str(agent).startswith(str((Path.home() / ".pi").resolve()))
    assert runtime.layout().runtime_dir == (settings.app_data_dir / "pi-runtime").resolve()


def test_the_host_pi_directory_is_never_touched(settings_factory, monkeypatch, tmp_path, fake_npm):
    """A decoy ~/.pi/agent must remain untouched by any Solo operation.

    Uses the offline `fake_npm` fixture: a unit test must not reach the network,
    and performing a real `npm install` here made the suite slow, flaky and
    dependent on connectivity.
    """
    decoy_home = tmp_path / "home"
    decoy_agent = decoy_home / ".pi" / "agent"
    decoy_agent.mkdir(parents=True)
    sentinel = decoy_agent / "auth.json"
    sentinel.write_text('{"openrouter": {"type": "api_key", "key": "HOST-KEY"}}')

    monkeypatch.setenv("HOME", str(decoy_home))
    settings = settings_factory(pi_agent_dir=None, pi_runtime_dir=None)
    runtime = PiRuntime(settings)

    runtime.initialize()
    asyncio_run(runtime.status())
    installed = asyncio_run(runtime.install())
    assert installed.ok is True, installed.detail

    assert sentinel.read_text() == '{"openrouter": {"type": "api_key", "key": "HOST-KEY"}}'
    assert sorted(p.name for p in decoy_agent.iterdir()) == ["auth.json"]


# --------------------------------------------------------------------------- #
# 3. Every Pi subprocess gets Solo's own environment
# --------------------------------------------------------------------------- #
def test_env_always_points_at_solos_agent_directory(settings_factory):
    settings = settings_factory(pi_agent_dir=None)
    runtime = PiRuntime(settings)
    env = runtime.env()

    assert env["PI_CODING_AGENT_DIR"] == str(runtime.agent_dir())
    assert "PI_SKIP_VERSION_CHECK" in env
    assert "HOME" not in env, "Solo must not override the process HOME"


def test_explicit_agent_dir_is_still_isolated_from_the_host(settings_factory, tmp_path):
    custom = tmp_path / "isolated-agent"
    runtime = PiRuntime(settings_factory(pi_agent_dir=str(custom)))
    assert runtime.agent_dir() == custom.resolve()
    assert runtime.env()["PI_CODING_AGENT_DIR"] == str(custom.resolve())


# --------------------------------------------------------------------------- #
# 4. Initialisation
# --------------------------------------------------------------------------- #
def test_initialize_creates_isolated_credentials_and_settings(settings_factory):
    settings = settings_factory(pi_agent_dir=None, pi_runtime_dir=None)
    runtime = PiRuntime(settings)
    runtime.initialize()
    layout = runtime.layout()

    assert layout.agent_dir.is_dir()
    assert layout.runtime_dir.is_dir()
    assert layout.auth_file.is_file(), "Pi expects auth.json to exist"
    assert json.loads(layout.auth_file.read_text()) == {}

    written = json.loads(layout.settings_file.read_text())
    assert written["defaultProjectTrust"] == "never", (
        "the isolated runtime must not trust project-local extensions"
    )
    assert written == AGENT_SETTINGS

    if os.name == "posix":
        assert oct(layout.agent_dir.stat().st_mode)[-3:] == "700"
        assert oct(layout.auth_file.stat().st_mode)[-3:] == "600"


def test_initialize_preserves_an_edited_settings_file(settings_factory):
    runtime = PiRuntime(settings_factory(pi_agent_dir=None, pi_runtime_dir=None))
    runtime.initialize()
    layout = runtime.layout()
    layout.settings_file.write_text('{"defaultProjectTrust": "always"}')

    runtime.initialize()
    assert json.loads(layout.settings_file.read_text()) == {"defaultProjectTrust": "always"}


# --------------------------------------------------------------------------- #
# Installer
# --------------------------------------------------------------------------- #
async def test_install_uses_the_managed_prefix(settings_factory, fake_npm):
    settings = settings_factory(pi_executable=None, pi_runtime_dir=None)
    runtime = PiRuntime(settings)

    result = await runtime.install()
    assert result.ok is True, result.detail
    assert runtime.managed_cli() is not None
    assert runtime.source() == "managed"

    layout = runtime.layout()
    assert str(layout.cli_js).startswith(str(settings.app_data_dir.resolve()))

    manifest = runtime.read_manifest()
    assert manifest["package"] == PI_PACKAGE
    assert manifest["node"]


async def test_install_is_idempotent(settings_factory, fake_npm):
    runtime = PiRuntime(settings_factory(pi_executable=None, pi_runtime_dir=None))
    first = await runtime.install()
    assert first.ok is True

    second = await runtime.install()
    assert second.ok is True
    assert "already installed" in second.message


async def test_install_reports_a_missing_node_clearly(settings_factory, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    runtime = PiRuntime(settings_factory(pi_executable=None, pi_runtime_dir=None))
    result = await runtime.install()

    assert result.ok is False
    assert "Node.js was not found" in result.message
    assert "nodejs.org" in (result.detail or "")


async def test_install_reports_an_npm_failure_and_records_it(
    settings_factory, tmp_path, monkeypatch
):
    bindir = tmp_path / "failing-bin"
    bindir.mkdir()
    npm = bindir / "npm"
    npm.write_text("#!/bin/sh\necho 'npm ERR! simulated network failure' >&2\nexit 1\n")
    npm.chmod(npm.stat().st_mode | stat.S_IXUSR)
    node = bindir / "node"
    node.write_text("#!/bin/sh\necho v99.0.0-fake\n")
    node.chmod(node.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")

    runtime = PiRuntime(settings_factory(pi_executable=None, pi_runtime_dir=None))
    result = await runtime.install()

    assert result.ok is False
    assert "could not be installed" in result.message
    assert "simulated network failure" in (result.detail or "")
    assert runtime.read_manifest().get("last_error")
    # A failed install must not leave a half-usable runtime behind.
    assert runtime.resolve_argv() is None


async def test_install_reports_when_an_external_executable_is_configured(
    settings_factory, tmp_path
):
    executable = tmp_path / "my-pi"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

    runtime = PiRuntime(settings_factory(pi_executable=str(executable)))
    result = await runtime.install()
    assert result.ok is True
    assert "did not install its own copy" in result.message


# --------------------------------------------------------------------------- #
# Status and verification
# --------------------------------------------------------------------------- #
async def test_status_reports_the_isolated_runtime(settings_factory, fake_pi):
    runtime = make_managed_runtime(settings_factory(pi_executable=None), fake_pi)
    status = await runtime.status()

    assert status.installed is True
    assert status.source == "managed"
    assert status.version == "1.1.0-fake"
    assert status.agent_dir == str(runtime.agent_dir())
    assert status.runtime_dir == str(runtime.runtime_dir())
    payload = status.to_dict()
    assert payload["isolated"] is True
    assert payload["available"] is True


async def test_verified_is_only_true_when_the_runtime_really_starts(
    settings_factory, fake_pi
):
    runtime = make_managed_runtime(settings_factory(pi_executable=None), fake_pi)

    ok, detail = await runtime.rpc_probe(command={"type": "get_state"})
    assert ok is True, detail

    verified = await runtime.status(verify=True)
    assert verified.verified is True

    # Now break the runtime and confirm Solo admits it rather than assuming.
    runtime.layout().cli_js.unlink()
    broken = await runtime.status(verify=True)
    assert broken.installed is False
    assert broken.verified is False


async def test_probe_reports_an_uninstalled_runtime(settings_factory):
    runtime = PiRuntime(settings_factory(pi_executable=None, pi_runtime_dir=None))
    ok, detail = await runtime.rpc_probe(command={"type": "get_state"})
    assert ok is False
    assert "not installed" in detail


async def test_probe_pi_runtime_reports_the_source(settings_factory, fake_pi):
    settings = settings_factory(pi_executable=None)
    make_managed_runtime(settings, fake_pi)
    info = await probe_pi_runtime(settings)
    assert info.available is True
    assert info.source == "managed"
    assert info.agent_dir == str(PiRuntime(settings).agent_dir())


async def test_backend_auto_uses_pi_only_when_solo_own_runtime_exists(
    settings_factory, tmp_path, monkeypatch
):
    """`auto` must not be influenced by a global `pi` on PATH."""
    from app.adapters import resolve_backend

    bindir = tmp_path / "global-bin"
    bindir.mkdir()
    global_pi = bindir / "pi"
    global_pi.write_text("#!/bin/sh\nexit 0\n")
    global_pi.chmod(global_pi.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")

    settings = settings_factory(agent_backend="auto", pi_executable=None, pi_runtime_dir=None)
    assert resolve_backend(settings) == "mock", "a global pi must not select the Pi backend"

    settings_with_runtime = Path(settings.app_data_dir) / "pi-runtime"
    cli = settings_with_runtime / "node_modules" / PI_PACKAGE / "dist" / "bundle" / "cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("// fake")
    (settings_with_runtime / "runtime.json").write_text(json.dumps({"node": str(global_pi)}))
    assert resolve_backend(settings) == "pi"


def asyncio_run(coro):
    """Small helper so synchronous tests can drive the async runtime API."""
    import asyncio

    return asyncio.run(coro)
