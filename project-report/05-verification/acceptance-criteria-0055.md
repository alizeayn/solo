# Acceptance criteria — 2.5.1

| | |
|---|---|
| **Stage** | Network access, mobile, Orchestrator and Pi Agent |
| **Date** | 2026-10-12 |

---

## 1. Reported defect: task says Completed but nothing happens

| Requirement | Status |
|---|---|
| Cause identified | ✅ three distinct causes: D-47, D-48, D-49 |
| Orchestrator functioning | ✅ **fixed and verified** — 5/5 classifications correct with real reasoning |
| Pi Agent functioning | ✅ readiness now reported truthfully; runs correctly when a model is configured |
| Pi Agent Activity informative | ✅ emits an actionable `error` event instead of "running unknown" |
| Regression tests | ✅ 5 new; **463 backend tests pass** |
| "Completed but nothing happened" eliminated | ⚠️ **partly** — D-49 remains open by choice |

## 2. Network accessibility

| Requirement | Status |
|---|---|
| Reachable from other devices | ✅ verified — `0.0.0.0:8080`, LAN IP returns 200 |
| Startup supports it | ✅ default bind already correct; `APP_HOST` documented |
| Address discoverable | ✅ `./solo.sh access` and the start banner |
| Distinguish local from remote | ✅ `./solo.sh access` states bind, LAN URL and voice readiness |

## 3. Security

| Requirement | Status |
|---|---|
| Not exposed indiscriminately | ✅ authentication unchanged; explicit guidance to use a TLS proxy or tunnel |
| Secrets protected | ✅ API keys stay in encrypted server-side storage; no key in any config file or commit |
| Host-header protection available | ✅ `SOLO_ALLOWED_HOSTS` (opt-in) |
| TLS | ✅ supported and verified; self-signed helper for the LAN |
| Remote access documented | ⚠️ referenced from `./solo.sh access`; `docs/remote-access.md` **not yet written** |

## 4. Voice on mobile

| Requirement | Status |
|---|---|
| Secure context available for the microphone | ✅ TLS support added and verified |
| Tap to start, no holding | ✅ already the session model from 2.5.0 |
| Session stays active | ✅ session model |
| UI explains microphone restrictions | ❌ **not implemented** — no secure-context guard |

## 5. Mobile-responsive UI

| Requirement | Status |
|---|---|
| Workspace usable on narrow screens | ❌ **not implemented** — only the pre-existing `StackedLayout` at ≤900 px |
| Tile layout, navigation, spacing, typography, tap targets | ❌ not addressed |
| Voice session usable on a touchscreen | ⚠️ session model is tap-based; layout not adapted |
| Tested at representative mobile sizes | ❌ not done |
| Cross-device test | ❌ no second device available |

## 6. Honest position

This release fixes the **functional** fault that was reported — the Orchestrator
and Pi Agent — and closes the TLS gap that blocked voice on a phone. It does
**not** deliver the mobile-responsive UI or cross-device testing, which remain
open. Claiming otherwise would be false.

## Related

- [Implementation 0052](../02-implementation/network-mobile-and-agent-0052.md)
- [Defect log 0054](../04-defects/defect-log-0054.md)
- [Summary 0056](../06-summary/summary-0056.md)
