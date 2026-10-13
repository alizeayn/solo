"""The model providers the Orchestrator can reason with.

Solo's Orchestrator asks a model to classify intent, plan steps, summarise
progress and phrase milestones. Which company serves that model is an
implementation detail, so the provider is a setting rather than a code path —
and the second provider is added without the first one changing behaviour.

Both providers speak the OpenAI chat-completions dialect, which is why one
transport (`app.services.openrouter.OpenRouterClient`) serves both. What differs
is the base URL, which settings hold the key and the model, and any headers the
provider requires.

## Why the headers are not optional

OpenCode Go rejects a request that carries no session id:

```json
400 {"type":"error","error":{"type":"MissingSessionID",
     "message":"Request is missing x-opencode-session and cannot be routed
                efficiently."}}
```

This is not advisory politeness — omitting it fails every call, and the message
is clear only if you read it. Sending it is part of using the provider at all.

References:
* OpenCode Go — <https://opencode.ai/docs/go/>
* OpenRouter — <https://openrouter.ai/docs/api-reference/overview>
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

OPENROUTER = "openrouter"
OPENCODE_GO = "opencode_go"

#: Default base URLs. Both are OpenAI-compatible: `POST /chat/completions` and
#: `GET /models` under the same prefix.
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
#: The Go inference prefix. Note that the marketing site also serves
#: `opencode.ai/zen/go/v1`; both answered identically when checked, and the
#: official documentation names this one, so this is the one Solo uses.
OPENCODE_GO_BASE_URL = "https://opencode.ai/inference/go/v1"


def opencode_go_headers(session_id: str) -> dict[str, str]:
    """Headers OpenCode Go requires on every inference request.

    `x-opencode-session` is mandatory (see the module docstring). The user agent
    is requested rather than enforced: the documentation asks clients to identify
    themselves instead of looking like a generic HTTP library, because Go shapes
    routing and caching around coding-agent traffic.
    """
    return {
        "x-opencode-session": session_id,
        "User-Agent": "solo/2.6.1 (coding-agent)",
    }


@dataclass(frozen=True)
class ProviderSpec:
    """Everything that differs between providers."""

    id: str
    label: str
    default_base_url: str
    #: Settings key holding the API key for this provider.
    key_setting: str
    #: Settings key holding the chosen model id for this provider.
    model_setting: str
    #: Settings attribute that can override the base URL (proxies, self-hosting).
    base_url_setting: str | None = None
    #: Extra headers to send, given a session id.
    header_builder: Callable[[str], dict[str, str]] | None = None
    #: Where a user can learn more; shown in the UI.
    documentation: str = ""
    #: Where to obtain a key.
    key_url: str = ""
    notes: str = ""


PROVIDERS: dict[str, ProviderSpec] = {
    OPENROUTER: ProviderSpec(
        id=OPENROUTER,
        label="OpenRouter",
        default_base_url=OPENROUTER_BASE_URL,
        base_url_setting="openrouter_base_url",
        key_setting="openrouter_api_key",
        model_setting="openrouter_model",
        documentation="https://openrouter.ai/docs/api-reference/overview",
        key_url="https://openrouter.ai/keys",
        notes=(
            "One key reaches many vendors. Free tiers are rate limited per day; "
            "the catalogue advertises capabilities a model may not honour."
        ),
    ),
    OPENCODE_GO: ProviderSpec(
        id=OPENCODE_GO,
        label="OpenCode Go",
        default_base_url=OPENCODE_GO_BASE_URL,
        base_url_setting="opencode_go_base_url",
        key_setting="opencode_go_api_key",
        model_setting="opencode_go_model",
        header_builder=opencode_go_headers,
        documentation="https://opencode.ai/docs/go/",
        key_url="https://opencode.ai/console",
        notes=(
            "A subscription with a curated list of open coding models, billed "
            "against a monthly allowance rather than per token. Every request "
            "must carry x-opencode-session."
        ),
    ),
}

DEFAULT_PROVIDER = OPENROUTER


def get_provider(provider_id: str | None) -> ProviderSpec:
    """Resolve a provider id, falling back to the default rather than raising.

    A saved setting can name a provider that a later release removed. Treating
    that as a hard error would leave the Orchestrator unusable with no way to
    reach the UI that fixes it.
    """
    return PROVIDERS.get((provider_id or "").strip().lower(), PROVIDERS[DEFAULT_PROVIDER])


def provider_catalog() -> list[dict[str, Any]]:
    """The providers, described for the settings UI."""
    return [
        {
            "id": spec.id,
            "label": spec.label,
            "key_setting": spec.key_setting,
            "model_setting": spec.model_setting,
            "base_url": spec.default_base_url,
            "documentation": spec.documentation,
            "key_url": spec.key_url,
            "notes": spec.notes,
            "requires_session_header": spec.header_builder is not None,
        }
        for spec in PROVIDERS.values()
    ]


def build_headers(spec: ProviderSpec, session_id: str) -> dict[str, str]:
    """Provider headers, tolerant of a spec that needs none."""
    if spec.header_builder is None:
        return {}
    return spec.header_builder(session_id)
