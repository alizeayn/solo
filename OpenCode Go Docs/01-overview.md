# Overview

OpenCode Go is a subscription giving access to a curated list of open coding
models, served by the OpenCode team. It is aimed at coding agents, and it is
optional — OpenCode itself works without it.

## Plans

| Plan | Price | Included usage |
|---|---|---|
| **Go** | $10/month | Lower-cost access to the models below |
| **Go Plus** | $40/month | Higher usage limits across the same models |

## How usage is measured

Unlike OpenRouter's per-token billing, Go is measured as a **monthly dollar
allowance per model**. Each model has its own limit, and each is subject to
tiered sub-limits:

* **5-hour** — 20% of the monthly limit
* **weekly** — 50%
* **monthly** — 100%

Crossing a sub-limit does not fail immediately; it means the model becomes
unavailable for that window. Two models (`LongCat 2.5 Preview Free`,
`Step 5 Preview Free`) are unlimited for a limited time, which makes them useful
for testing without consuming an allowance.

If the Console balance has credit and **Use balance** is enabled, Go falls back to
pay-as-you-go rather than blocking.

## Service terms a client must respect

The documentation is explicit that Go expects coding-agent traffic:

1. send typical coding-agent requests;
2. **identify yourself in the User-Agent** rather than looking like a generic
   HTTP library;
3. **send a stable `x-opencode-session`** so routing and prompt caching can be
   optimised.

Item 3 is enforced, not requested. See [02-endpoints-and-auth.md](02-endpoints-and-auth.md).

## Privacy

Retention is per model, and it is not uniform:

| Tier | Retention |
|---|---|
| Most models (GLM, Kimi, LongCat, MiMo, Qwen, MiniMax, Hy, Space Bunny) | **0 days** |
| Grok 4.7 / 4.6, GPT 6 Luna / 5.6 Luna, Claude Haiku 5.5 | **30 days** |
| Muse Spark 1.2 / 1.3 Contributor | prompts and completions may be used for training |

The Contributor tier is discounted in exchange for training rights and is limited
to Meta-permitted regions. Worth knowing before pointing an Orchestrator at it,
since the Orchestrator sees project context.
