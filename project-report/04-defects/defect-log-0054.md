# Defect log — 2.5.1

| | |
|---|---|
| **Stage** | Remote access, mobile, Orchestrator and Pi Agent |
| **Date** | 2026-10-12 |
| **Defects** | D-47 … D-50 |

---

## D-47 — The Orchestrator was configured, enabled, and doing nothing

**Severity** Critical · **Status** Fixed · **Found by** user report, confirmed against the live API

**Symptom.** The Orchestrator never changed a routing decision.

**Root cause.** `complete_json` requested structured output via `response_format`.
The configured model advertises `supports_structured_output: true` but returns
**400 `Provider returned error`** for the parameter. Every `classify()` therefore
returned `None` and routing silently fell back to the deterministic rules router.

**Why it survived every test.** The fallback is *by design* — classification
"never fails" — so the system kept working while the feature was dead. Nothing
downstream could distinguish "the model agreed" from "the model never answered".
The generic error text hid the cause as well.

**Fix.** One retry without `response_format` on a 400, with the required keys
described in prose. Only 400 — auth and quota errors still surface.

---

## D-48 — Pi Agent Activity reported a model that did not exist

**Severity** High · **Status** Fixed · **Found by** reproduction with a clean runtime

**Symptom.** The Activity panel read `Pi is running unknown from Solo's own
runtime`, and the task then failed with `No API key found for the selected model`
— a message about a model the user never selected.

**Root cause.** Pi reports the literal string `"unknown"` when no model is
selected. The readiness guard checked only for a *missing* id, so `"unknown"`
passed as valid.

**Fix.** `unknown` / `none` / `null` are treated as no model, and the actionable
event is emitted *before* the run.

---

## D-49 — Answers are presented as completed tasks

**Severity** Medium · **Status** Identified, not fixed · **Found by** the user's database

**Symptom.** "I submit a task and it says Completed but nothing happens."

**Root cause.** `_answer_question` writes a `QUESTION` task and marks it
`COMPLETED` immediately. The user's database contains 9 such rows — `"hi"`,
`"are you ready for start project?"` — alongside 2 genuinely failed `CODING`
tasks. Question rows are visually indistinguishable from coding tasks, so a
correct answer reads as a task that did nothing.

**Not fixed deliberately.** Correcting it changes what a task *is* in the UI and
belongs with the Activity/milestone presentation work rather than in a patch
release. Reported so it is not mistaken for a working feature.

---

## D-50 — Voice on a phone was impossible, for a non-obvious reason

**Severity** High · **Status** Partially fixed · **Found by** design review

**Root cause.** Browsers expose the microphone only in a **secure context**. Solo
binds `0.0.0.0` and serves plain HTTP, so `http://<lan-ip>` is not one and
`getUserMedia` is refused. Nothing in Solo said so; the failure would have looked
like a broken button.

**Fix (part).** Solo can now terminate TLS: `SSL_CERTFILE`/`SSL_KEYFILE`,
`./solo.sh cert` for a correctly-scoped self-signed certificate, and
`./solo.sh access` to explain the situation per device. Verified: HTTPS serves 200,
plain HTTP is refused, the SAN includes the LAN IP.

**Outstanding.** The frontend has no secure-context guard, so the UI still cannot
explain the restriction to the user. Tracked as part of the mobile work.

---

## Corrected prior belief

`docs/` and earlier reports implied network access was local-only. **It is not** —
`app_host` has defaulted to `0.0.0.0`, and the LAN address returned 200. The real
gap was TLS (and therefore mobile voice), not reachability. Recorded because the
proposed fix would otherwise have been applied to a working component.

## Open

| ID | Issue | Status |
|---|---|---|
| D-08 | Docker build unverified — no daemon access | Open (environment) |
| D-49 | Question rows presented as completed tasks | Open (deliberate) |
| — | Mobile responsive layout not implemented | Open |
| — | No frontend secure-context guard for voice | Open |
