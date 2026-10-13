# Acceptance criteria — 2.6.1

| | |
|---|---|
| **Stage** | OpenCode Go as a second Orchestrator provider |
| **Date** | 2026-10-13 |

---

## 1. Review the existing architecture

| Requirement | Status |
|---|---|
| Orchestrator reviewed | ✅ `orchestrator_brain`, `api/orchestrator.py`, `orchestrator_providers` |
| OpenRouter integration reviewed | ✅ key/model/base URL reads found in five places across the API and brain |

## 2. Add OpenCode Go without breaking OpenRouter

| Requirement | Status |
|---|---|
| Second provider supported | ✅ provider descriptor + two settings pairs |
| OpenRouter not removed or broken | ✅ **470 pre-existing tests still pass**; default unchanged |
| One transport, not two | ✅ `extra_headers` added to the existing client |
| Switching is exact in both directions | ✅ asserted by test |

## 3. API key configuration and validation

| Requirement | Status |
|---|---|
| Enter a key | ✅ via Settings, per provider |
| Stored securely | ✅ encrypted at rest, asserted by test |
| Validated | ✅ `/orchestrator/test`, provider-aware; `GET /key` skipped for Go |
| Validated by a real request, not merely presence | ✅ unchanged rule |

## 4. Model retrieval and selection

| Requirement | Status |
|---|---|
| Retrieve models | ✅ `GET /orchestrator/models`, active provider |
| Display them | ✅ in Settings, per provider |
| Select one | ✅ written to that provider's own setting |
| Discovered, not hardcoded | ✅ live endpoint; the observed 39 are documented as a snapshot |

## 5. Official documentation reviewed and saved

| Requirement | Status |
|---|---|
| Reviewed | ✅ vendor Go guide, console guide, providers page |
| Saved in `OpenCode Go Docs` | ✅ 5 files |
| Organised | ✅ overview · verified protocol · catalogue · integration |
| Verified, not merely copied | ✅ the two divergences from the documentation are recorded |

## 6. Test the integration

| Requirement | Status |
|---|---|
| Models endpoint reachable | ✅ **live, 200, 39 models** |
| Session-header requirement confirmed | ✅ **live, 400 without it** |
| Request shape accepted | ✅ **live, 401 only on the credential** |
| Provider selection works end to end | ✅ through the real container |
| A real completion | ❌ **no OpenCode Go key available** |

## Test totals

| Suite | Result |
|---|---|
| Backend | **482 passed** (+12) |
| Frontend | **152 passed**, typecheck clean, build succeeded |

## Honest position

The integration is complete, tested at every layer Solo controls, and verified
against the live service as far as is possible without a credential. **No real
completion has been run, because no OpenCode Go key was available** — Pi's
credential store holds only OpenRouter.

That is a strong position but not a finished verification: entering a key and
running one task is what would close it.

## Related

- [Implementation 0088](../02-implementation/orchestrator-providers-0088.md)
- [Defect log 0090](../04-defects/defect-log-0090.md)
- [Summary 0092](../06-summary/summary-0092.md)
