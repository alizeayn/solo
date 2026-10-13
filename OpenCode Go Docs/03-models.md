# Model catalogue

Observed from `GET https://opencode.ai/inference/go/v1/models` — **39 models**.
The list changes as models are added and retired; this is a snapshot, not a
contract. Solo discovers models at runtime rather than hardcoding them, precisely
because a hardcoded list would both hide new models and offer retired ones.

```
deepseek-v4-flash              deepseek-v4-flash-vision-exp   deepseek-flash
deepseek-v4.1-flash            deepseek-v4-pro                glm-5.1
glm-5.2                        glm-5.3                        glm-5.3-flash
grok-4.6                       grok-4.7                       gpt-5.6-luna
gpt-6-luna                     claude-haiku-5-5               kimi-k2.6
kimi-k2.7-code                 kimi-k3                        longcat-2.0
longcat-2.5-preview-free       step-5-preview-free            cat-jam-free
mimo-v2.5                      mimo-v2.5-pro                  mimo-v2.6-flash
mimo-v2.6-pro                  minimax-m2.5                   minimax-m2.7
minimax-m3                     muse-spark-1.2-contributor     muse-spark-1.3-contributor
omen-alpha                     space-bunny                    qwen3.6-plus
qwen3.7-max                    qwen3.7-plus                   qwen3.8-flash
qwen3.8-max                    hy3                            hy4-preview
```

## Choosing one for the Orchestrator

The Orchestrator makes many small, cheap calls: intent classification, milestone
wording, question answering. It does not need the strongest model — it needs a
fast, reliable one that returns valid JSON.

| Model | Why it suits the Orchestrator |
|---|---|
| `glm-5.3-flash` | Cheapest with the largest monthly allowance; ideal for classification |
| `mimo-v2.6-flash` | Very low cost, enormous request allowance |
| `kimi-k2.7-code` | Coding-tuned, generous allowance |
| `longcat-2.5-preview-free` | **Free** and unlimited for a limited time — best starting point |
| `step-5-preview-free` | Also free and unlimited for a limited time |

The strongest models (`grok-4.7`, `qwen3.8-max`, `kimi-k3`) carry the *smallest*
monthly allowances, which is the opposite of what the Orchestrator needs.

## Capability caution

Solo's `complete_json` requests structured output and, on a `400`, retries once
without `response_format`. That fallback exists because OpenRouter's catalogue
advertised `supports_structured_output: true` for a model that then rejected the
parameter. OpenCode Go's `/models` payload carries **no capability metadata at
all**, so the same defensive behaviour is the only safe assumption.
