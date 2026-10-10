# 06 — Test Report

**Stage:** Testing
**Date:** 2026-10-10

---

## 1. Summary

| Suite | Tests | Passed | Failed | Tool |
|---|---|---|---|---|
| Backend unit + API | 123 | 123 | 0 | pytest 8.3.4, pytest-asyncio, TestClient |
| Frontend unit + component | 22 | 22 | 0 | Vitest 3.2.7, Testing Library, jsdom |
| TypeScript | – | – | 0 errors | `tsc --noEmit`, `strict: true` |
| End-to-end (real server) | 26 checks | 26 | 0 | `scripts/e2e.sh` |
| **Total automated tests** | **145** | **145** | **0** | |

Backend coverage: **89 %** (1 965 statements, 209 missed).
Backend wall time: ~31 s. Frontend: ~1.5 s. End-to-end: ~15 s.

---

## 2. Backend coverage by module

| Module | Coverage | Notes |
|---|---|---|
| `schemas.py`, `security.py`, `domain.py`, `logging_setup.py`, `models.py`, `container.py`, `event_bus.py`, `services/__init__.py`, `api/settings.py`, `api/auth.py`, `adapters/base.py`, `repositories/__init__.py` | **100 %** | |
| `api/projects.py` | 98 % | |
| `services/intent.py`, `main.py` | 96 % | |
| `config.py` | 95 % | |
| `services/project_scan.py` | 94 % | |
| `services/context.py`, `adapters/__init__.py`, `services/archive.py`, `api/ws.py` | 91–92 % | |
| `repositories/tasks.py`, `api/tasks.py`, `adapters/mock_agent.py` | 89 % | |
| `services/settings_service.py` | 88 % | |
| `adapters/pi_agent.py` | 78 % | Phase 2 stub, intentionally unreachable |
| `services/auth_service.py` | 78 % | |
| `services/orchestrator.py` | 77 % | |
| `repositories/conversations.py`, `services/project_service.py` | 70–75 % | |
| `repositories/sessions.py`, `settings.py` | 65–66 % | |
| `services/event_bus.py` | 100 % | |

The uncovered remainder is dominated by defensive branches (corrupt-store
handling, unreachable `AssertionError` guards, restart-only paths) and the
Phase 2 Pi stub. No business rule is untested.

---

## 3. Backend test inventory

| File | Tests | Covers |
|---|---|---|
| `test_security.py` | 15 | scrypt round-trip, salting, malformed-hash rejection (4 parametrised), token uniqueness/hashing, masking (4 cases), cipher round-trip, key persistence, `0600` permissions, corrupt-token handling, redaction of values and patterns, filter rewriting |
| `test_archive.py` | 12 | Regular extraction, single-root stripping, traversal rejection (4 parametrised), symlink rejection, non-ZIP, entry-count limit, size limit, settings-driven limits |
| `test_intent.py` | 16 | Stop intents (5), coding starts (4), questions (3), steering (3), coded-question precedence |
| `test_project_scan.py` | 4 | Ignored directories, hidden directories, `max_files`, missing directory, language summary |
| `test_api_auth.py` | 19 | Health is public and secret-free, 4 protected routes, pre-setup status, setup + status + me, one-shot setup, short-password rejection, logout invalidation, login flow, cross-origin 403, same-origin 201, WS 4401, WS `ready` |
| `test_api_projects.py` | 12 | CRUD, unique slugs, blank-name 400, upload extraction, non-ZIP, corrupt archive, traversal, size limit 413, 404, path-boundary unit tests |
| `test_api_settings.py` | 12 | Defaults, masking, raw-key absence, encryption at rest (greps the SQLite file), plain round-trip, clear via empty string, delete endpoint, missing-key tests, Pi status, unknown provider 404, auth required |
| `test_api_tasks.py` | 8 | Completion with expected events, conflict 409, cancel → confirm, steer, steer-inactive 409, error paths, project filtering, **restart persistence** |
| `test_api_messages.py` | 8 | Snapshot answer, coding starts a task, follow-up steers the same task, question does not interrupt, stop cancels, stop with no task, message ordering, unknown project |
| `test_orchestrator.py` | 5 | In-flight → `RECOVERY_REQUIRED`, completed tasks untouched, bootstrap from password file (and file consumption), bootstrap skipped without a password, adapter health |
| `test_services_extra.py` | 12 | OpenRouter missing/valid/401/403/500/network-error, ElevenLabs missing/without-agent/with-agent/401, adapter factory guards, event bus fan-out and slow-subscriber drop, adapter failure → `FAILED`, snapshot + offline answer |

### Test isolation

Every test receives a unique temporary data directory and its own application
instance via `tests/conftest.py`; no test can touch a developer's real `data/`
or interfere with another. No test performs network I/O — provider HTTP is
replaced with an injected stub client.

---

## 4. Frontend test inventory

| File | Tests | Covers |
|---|---|---|
| `utils/format.test.ts` | 8 | All status labels, tone mapping, event labels and glyph fallbacks, relative time incl. future timestamps, truncation boundaries |
| `types.test.ts` | 3 | `isActive` / `isTerminal` matrix incl. `RECOVERY_REQUIRED` being neither |
| `components/LoginView.test.tsx` | 3 | Render, submit → `onComplete`, rejection → alert shown and no callback |
| `components/StackedLayout.test.tsx` | 2 | Default tab, panel switching |
| `panels/ActivityPanel.test.tsx` | 6 | Empty state, summary/status/metrics, changed files derived from events, timeline order, error surfacing, active-task fallback |

---

## 5. What the tests explicitly guarantee

Traced from the specification's acceptance criteria to a concrete test:

| Guarantee | Evidence |
|---|---|
| Unauthenticated users cannot reach project or coding functionality | `test_protected_endpoints_require_auth` (4 routes), `test_websocket_requires_authentication` |
| A stored secret is never returned, logged or stored in plaintext | `test_secret_is_stored_masked_and_never_returned`, `test_secret_persists_across_requests_and_is_encrypted_at_rest` (scans the DB file), `test_cipher_roundtrip_and_key_permissions`, `test_redaction_filter_rewrites_log_messages` |
| ZIP import is safe against traversal, symlinks and bombs | `test_archive.py` (12 tests), `test_upload_rejects_path_traversal`, e2e "no file escaped the workspace" |
| A project cannot escape the managed directory | `test_resolve_project_root_rejects_escapes`, `test_resolve_project_root_accepts_valid_path` |
| Only one modifying task runs per project | `test_conflicting_task_is_rejected` (409) |
| Cancellation is confirmed, not assumed | `test_cancel_requests_then_confirms`, `test_stop_cancels_the_active_task` |
| A question does not interrupt a running task | `test_question_while_running_does_not_interrupt_task` |
| A follow-up is associated with the right task | `test_follow_up_while_running_steers_the_same_task` |
| State survives a restart | `test_task_state_survives_restart` |
| Interrupted work is never reported as complete | `test_in_flight_tasks_are_marked_for_recovery` |
| Provider failures are handled without leaking secrets | `test_openrouter_network_error` asserts the key is absent from the detail string; 401/403/500 paths |
| An adapter crash produces a truthful failure state | `test_adapter_failure_marks_task_failed` |

---

## 6. Observations from testing

1. **The suite found real bugs, not just regressions.** Six of the eight defects
   in the log were surfaced by writing tests (D-01 through D-06), not by manual
   clicking. Two categories dominated: trust boundaries (archive paths, secret
   exposure) and concurrency (cancel/completion races).
2. **Determinism was engineered in, not assumed.** `MOCK_STEP_DELAY=0` makes the
   common case instant; concurrency tests deliberately use `0.2 s` so a race is
   observable rather than lucky. The cancel-before-run race (D-06) is only
   reproducible with a non-zero delay, which is why it is tested that way.
3. **Restart behaviour is tested as a first-class path.** `test_api_tasks.py`
   and `test_orchestrator.py` both build a *second* application instance over
   the same data directory, which is the closest thing to a process restart
   available in-process.

---

## 7. Known gaps

| Gap | Reason | Mitigation |
|---|---|---|
| Docker image build not executed | Daemon socket inaccessible (**D-08**) | Constituent steps verified natively; confirming command documented |
| No browser-driven UI test (Playwright/Cypress) | Not required for Phase 1; would add a heavy dependency | Component tests plus a real-server API-level e2e cover the path; UI is verified manually and by typecheck |
| No load or soak testing | Single-user MVP, not a throughput target | Bounded queues, caps and slow-subscriber handling are unit-tested |
| `orchestrator.py` at 77 % coverage | Some branches are shutdown/corruption paths | All state transitions are covered; remaining lines are defensive |
| No test for `restore.sh` round-trip | Requires a Docker daemon | Script syntax verified; behaviour documented |
