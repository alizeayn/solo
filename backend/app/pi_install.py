"""Install and verify Solo's isolated Pi Agent runtime.

Run as a module so the shell installer and the Settings UI use **one**
implementation:

```bash
cd <repo root>
PYTHONPATH=backend ./venv/bin/python -m app.pi_install            # install if missing
PYTHONPATH=backend ./venv/bin/python -m app.pi_install --force    # reinstall/upgrade
PYTHONPATH=backend ./venv/bin/python -m app.pi_install --json     # machine-readable result
PYTHONPATH=backend ./venv/bin/python -m app.pi_install --verify   # prove it can start
```

Exit codes: ``0`` success, ``1`` install or verification failure, ``2`` unusable
configuration.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from .config import Settings, get_settings
from .services.pi_runtime import PiRuntime


async def install_and_report(
    settings: Settings,
    *,
    force: bool,
    verify: bool,
    quiet: bool,
) -> tuple[int, dict[str, Any]]:
    runtime = PiRuntime(settings)
    layout = runtime.layout()

    if not quiet:
        print(f"  runtime dir : {layout.runtime_dir}")
        print(f"  agent dir   : {layout.agent_dir}")

    try:
        runtime.initialize()
    except OSError as exc:
        message = f"could not create Solo's Pi directories: {exc}"
        if not quiet:
            print(f"error: {message}", file=sys.stderr)
        return 2, {"ok": False, "error": message}

    result = await runtime.install(force=force)
    if not quiet:
        print(f"  install     : {'ok' if result.ok else 'FAILED'} — {result.message}")
        if result.detail and not result.ok:
            print(f"  detail      : {result.detail}")

    status = await runtime.status(verify=verify)
    if not quiet:
        print(f"  executable  : {status.executable or '(none)'}")
        print(f"  source      : {status.source}")
        print(f"  version     : {status.version or 'unknown'}")
        print(f"  node        : {status.node or 'not found'}")
        if verify:
            print(f"  verified    : {'yes' if status.verified else 'no'}")
        print(f"  status      : {status.detail}")

    payload: dict[str, Any] = {
        "ok": bool(result.ok and (status.verified if verify else status.installed)),
        "install": {
            "ok": result.ok,
            "message": result.message,
            "version": result.version,
            "duration_ms": result.duration_ms,
        },
        "runtime": status.to_dict(),
    }

    if not result.ok:
        return 1, payload
    if verify and not status.verified:
        return 1, payload
    return 0, payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.pi_install",
        description="Install and verify Solo's isolated Pi Agent runtime.",
    )
    parser.add_argument("--force", action="store_true", help="reinstall even if present")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="start the runtime and run a command to prove it works",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    settings = get_settings()
    code, payload = asyncio.run(
        install_and_report(
            settings, force=args.force, verify=args.verify, quiet=args.as_json
        )
    )
    if args.as_json:
        print(json.dumps(payload))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
