# Summary — 2.5.1

| | |
|---|---|
| **Stage** | Remote access, mobile, Orchestrator and Pi Agent |
| **Version** | 2.5.1 |
| **Date** | 2026-10-12 |

---

## The Orchestrator was on, configured, and never consulted

Every routing decision in Solo was made by the fallback rules router. The brain
was reachable, the key valid, the model present — and `classify()` returned `None`
for **every single message**, because the configured model rejects
`response_format` with a bare `400 Provider returned error` while advertising
`supports_structured_output: true`.

The design that made this invisible is the same design that made it *safe*: the
docs say classification "never fails" because it degrades to deterministic rules.
So the app kept working, no error reached the user, and a headline feature was
dead for as long as it had existed. Nothing downstream could tell "the model
agreed" from "the model never answered".

The fix retries once without `response_format` — only on a 400, never an auth or
quota failure — and describes the required keys in prose.

**Two traps found while fixing it**, both worth remembering:

* Embedding the raw JSON Schema made the model return **the schema itself**.
  Weaker models echo documents. Lists of keys and allowed values work; documents
  do not.
* An *example object* would have silently biased the `intent` enum to whichever
  value was shown first. Enums are described, never demonstrated.

## Pi Agent now says what is wrong

Pi reports the literal string `"unknown"` for a missing model, so the readiness
check passed and the run started anyway, failing later with a message about an API
key the user never picked — while Activity said `Pi is running unknown from Solo's
own runtime`. `unknown` is now treated as no model, and the actionable event is
emitted before the run:

```
Pi has no model selected. Choose a provider and model in Settings → Pi Agent.
```

## What the user's own data showed

The database was the most useful artefact in the whole investigation. Nine
`QUESTION` tasks marked `COMPLETED` — including `"hi"` and `"are you ready for
start project?"` — sitting beside two genuinely failed `CODING` tasks (429 free
tier, 401 invalid key). That is the "shows Completed but nothing happens" report,
precisely: conversational messages recorded as completed tasks, next to real runs
that failed for provider reasons.

`D-49` is reported rather than papered over: **question answers still appear as
completed tasks.** Fixing it changes what a task means in the UI and belongs with
the Activity work, not a patch release.

## Network access: already working

`app_host` has always defaulted to `0.0.0.0` and the API is same-origin, so a
phone could already reach `http://<lan-ip>:8080` — **verified, 200**. The proposed
investigation would have "fixed" a working component.

The real gap was **TLS**, and not for encryption: browsers expose the microphone
only in a secure context, so over plain HTTP on a LAN address the voice session
could never start. Solo can now terminate TLS, `./solo.sh cert` produces a
certificate correctly scoped to the LAN IP, and `./solo.sh access` explains per
device whether voice will work and why. Verified: HTTPS 200, plain HTTP refused,
SAN contains the LAN IP.

## What is not done

Stated plainly, because the request asked for it and the environment did not
provide it:

| Not done | Why |
|---|---|
| **Mobile-responsive UI** | Not implemented. Only the pre-existing `StackedLayout` at ≤900 px exists. |
| **Cross-device testing** | No second device, no mobile browser, no headless-browser layer. |
| **Voice restrictions explained in the UI** | The secure-context guard is not written. |
| **`docs/remote-access.md`** | Referenced by `./solo.sh access`; not yet written. |
| **D-49** | Deliberately deferred — changes task semantics. |

## Verification

| Suite | Result |
|---|---|
| Backend | **463 passed** (+5) |
| Orchestrator, live account | **5/5** correct classifications with real reasoning |
| Pi Agent readiness | actionable event verified end-to-end |
| LAN access | 200 |
| HTTPS | 200; plain HTTP refused; SAN includes the LAN IP |

## Related

- [Scope 0051](../01-planning/network-mobile-and-agent-fixes-0051.md)
- [Implementation 0052](../02-implementation/network-mobile-and-agent-0052.md)
- [Testing 0053](../03-testing/agent-and-network-0053.md)
- [Defect log 0054](../04-defects/defect-log-0054.md)
- [Verification 0055](../05-verification/acceptance-criteria-0055.md)
