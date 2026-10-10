# 02 — Phase Plan

**Stage:** Planning
**Date:** 2026-10-10

---

## 1. Approach

Follow the specification's own phasing, and **build vertically**: get one thin
slice working end to end before widening it. Within Phase 1 the order was chosen
so that each step is verifiable before the next depends on it.

```
1. Repo + tooling baseline
2. Domain vocabulary  ─────────────► the contract everything else speaks
3. Persistence + security ────────► models, repositories, hashing, cipher
4. Adapter contract + simulator ──► lets the whole path exist before Pi
5. Orchestrator ──────────────────► task lifecycle, routing, broadcast
6. HTTP + WebSocket API ──────────► the externally visible surface
7. Backend test suite ────────────► 123 tests before any UI is built
8. Frontend shell + panels ───────► auth, settings, Dockview, live feed
9. Frontend tests + typecheck
10. Deployment + docs
11. End-to-end verification on a real server
12. Project report
```

Rationale for the ordering: the backend contract was frozen and tested before
the UI consumed it, so frontend work could not be blocked by, or accidentally
define, backend behaviour.

---

## 2. Technology decisions

| Decision | Choice | Rationale |
|---|---|---|
| Password hashing | `hashlib.scrypt` (stdlib) | No external bcrypt build, no `passlib` version-detection warnings, memory-hard, constant-time compare. |
| Session storage | Opaque random token; SHA-256 digest stored | Revocable server-side; a database leak yields no usable cookie. |
| Secret encryption | Fernet, key in a separate `0600` file | A stolen database alone cannot decrypt stored keys. |
| ORM / async | SQLAlchemy 2.0 async + `aiosqlite` | Typed, mature, one dialect swap away from PostgreSQL. |
| DB access | Repository classes only | Business logic never touches a session; migration is an engine change. |
| Task/event ids | `uuid4().hex` strings | Opaque, URL-safe, never encode a filesystem path. |
| Frontend routing | None (three-state view) | Three mutually exclusive views and an overlay are state, not routes; avoids a dependency. |
| Tiling UI | `dockview-react` 8.4.1 + `themeAbyss` | Spec-mandated; theme variables retuned to match the app palette. |
| Frontend tests | Vitest + Testing Library + jsdom | Same toolchain as Vite; no second build system. |
| State management | React context provider | No Redux-class dependency for a single-user MVP. |

### Versions actually verified

Backend: FastAPI 0.115.6, uvicorn 0.34.0, SQLAlchemy 2.0.36, aiosqlite 0.20.0,
pydantic 2.10.4, pydantic-settings 2.7.0, python-multipart 0.0.20,
cryptography 44.0.0, httpx 0.28.1.

Frontend: React 19.3.0, Vite 8.3.4, TypeScript 5.7, dockview/dockview-react
8.4.1, Vitest 3.2.7.

All runtime versions are pinned in `backend/requirements.txt`; the frontend
lockfile is committed and `npm ci` was verified against it.

---

## 3. Work breakdown and outcomes

| # | Work item | Outcome |
|---|---|---|
| P1-01 | Repo scaffold, `.gitignore`, `LICENSE`, `.env.example` | ✅ |
| P1-02 | Domain vocabulary (statuses, events, intents, settings keys) | ✅ |
| P1-03 | Config (env-driven, paths, limits) | ✅ |
| P1-04 | Security primitives (scrypt, tokens, Fernet cipher, masking) | ✅ |
| P1-05 | Logging with redaction filter | ✅ |
| P1-06 | ORM models + async engine + session factory | ✅ |
| P1-07 | Repositories (7) | ✅ |
| P1-08 | Services: auth, settings, archive, project scan, projects, context, intent, event bus | ✅ |
| P1-09 | Adapter contract + mock coding agent + Pi runtime probe | ✅ |
| P1-10 | Orchestrator (lifecycle, routing, single-writer, broadcast) | ✅ |
| P1-11 | API routers (health, auth, settings, projects, tasks, messages, ws) | ✅ |
| P1-12 | App factory: lifespan, middleware, SPA serving | ✅ |
| P1-13 | Backend test suite | ✅ 123 tests, 89 % coverage |
| P1-14 | Frontend scaffold (Vite, TS strict, design system) | ✅ |
| P1-15 | Auth + first-run views | ✅ |
| P1-16 | Settings UI with live connection tests | ✅ |
| P1-17 | Project dialog (create / upload) | ✅ |
| P1-18 | Dockview layout with persistence and fallback | ✅ |
| P1-19 | Three panels + stacked narrow-screen layout | ✅ |
| P1-20 | WebSocket client with backoff, workspace provider | ✅ |
| P1-21 | Frontend test suite + typecheck + production build | ✅ 22 tests, 0 TS errors |
| P1-22 | Dockerfile, Compose, `install.sh`, backup/restore, `dev.sh` | ✅ (image build unverified — D-08) |
| P1-23 | Documentation (README + 4 docs) | ✅ |
| P1-24 | End-to-end smoke script | ✅ 26 checks passed |
| P1-25 | Project report | ✅ this document set |

---

## 4. Explicit non-goals for Phase 1

Recorded so that their absence is a decision, not an oversight:

- No real code modification. The mock agent runs a fixed, believable event
  sequence so the pipeline can be validated safely.
- No LLM calls. Intent routing is deterministic and unit-tested. Provider
  *credentials* are stored and tested, but no model inference is performed.
- No audio. Voice and TTS are represented in the UI as disabled with an
  explicit phase label.
- No schema migration framework. Create-all is additive-only for the MVP; the
  policy is documented in `docs/development.md`.
