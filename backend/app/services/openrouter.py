"""OpenRouter client.

Used by Solo's **Orchestrator** for intent classification, task prioritisation,
progress summarisation and project questions. It is deliberately a thin adapter:
no orchestration policy lives here, only transport, validation and error
translation.

Reference: <https://openrouter.ai/docs/api-reference/chat/send-chat-completion-request>
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT = 60.0
#: Hard cap so a runaway model cannot flood the orchestrator.
MAX_COMPLETION_TOKENS = 2048


class OpenRouterError(RuntimeError):
    """Any failure talking to OpenRouter, with a user-facing message."""

    def __init__(self, message: str, *, status: int | None = None, detail: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail


@dataclass
class OpenRouterModel:
    id: str
    name: str
    context_length: int | None = None
    pricing: dict[str, Any] = field(default_factory=dict)
    supports_structured_output: bool = False
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "context_length": self.context_length,
            "pricing": self.pricing,
            "supports_structured_output": self.supports_structured_output,
            "description": self.description,
        }


def _model_from_payload(raw: dict[str, Any]) -> OpenRouterModel:
    supported = raw.get("supported_parameters") or []
    pricing = raw.get("pricing") or {}
    return OpenRouterModel(
        id=str(raw.get("id") or ""),
        name=str(raw.get("name") or raw.get("id") or ""),
        context_length=raw.get("context_length") or raw.get("top_provider", {}).get("context_length"),
        pricing={k: v for k, v in pricing.items() if isinstance(v, (str, int, float))},
        supports_structured_output="structured_outputs" in supported
        or "response_format" in supported,
        description=(raw.get("description") or None),
    )


class OpenRouterClient:
    """Small async client for the OpenRouter REST API."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        referer: str = "http://localhost",
        title: str = "Solo",
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # OpenRouter uses these for attribution on the dashboard.
            "HTTP-Referer": referer,
            "X-Title": title,
        }

    # ------------------------------------------------------------------ #
    # Discovery / validation
    # ------------------------------------------------------------------ #
    async def verify_key(self) -> dict[str, Any]:
        """Check that the key is valid and return its account metadata."""
        payload = await self._request("GET", "/key")
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, dict) else {}

    async def list_models(self) -> list[OpenRouterModel]:
        """Every model OpenRouter exposes for this key."""
        payload = await self._request("GET", "/models")
        raw = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(raw, list):
            raise OpenRouterError("OpenRouter returned an unexpected model list")
        models = [_model_from_payload(item) for item in raw if isinstance(item, dict)]
        models = [model for model in models if model.id]
        models.sort(key=lambda m: m.id)
        return models

    # ------------------------------------------------------------------ #
    # Completion
    # ------------------------------------------------------------------ #
    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = MAX_COMPLETION_TOKENS,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Return the assistant text for a chat completion."""
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            body["response_format"] = response_format

        payload = await self._request("POST", "/chat/completions", json=body)
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices:
            raise OpenRouterError("OpenRouter returned no choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        if not isinstance(content, str) or not content.strip():
            raise OpenRouterError("OpenRouter returned an empty response")
        return content.strip()

    async def complete_json(
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        schema_name: str = "response",
        temperature: float = 0.0,
        max_tokens: int = MAX_COMPLETION_TOKENS,
    ) -> dict[str, Any]:
        """Completion constrained to JSON, validated by the caller's schema."""
        response_format: dict[str, Any] | None = None
        if schema is not None:
            response_format = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            }
        else:
            response_format = {"type": "json_object"}

        text = await self.complete(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )
        return _parse_json_object(text)

    # ------------------------------------------------------------------ #
    # Transport
    # ------------------------------------------------------------------ #
    async def _request(
        self, method: str, path: str, *, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(
                    method, url, headers=self._headers, json=json
                )
        except httpx.TimeoutException as exc:
            raise OpenRouterError(
                "OpenRouter did not respond in time.", detail="timeout"
            ) from exc
        except httpx.HTTPError as exc:
            raise OpenRouterError(
                "Could not reach OpenRouter.", detail=type(exc).__name__
            ) from exc

        elapsed = round((time.monotonic() - started) * 1000)
        if response.status_code >= 400:
            raise OpenRouterError(
                _error_message(response),
                status=response.status_code,
                detail=f"HTTP {response.status_code} in {elapsed}ms",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise OpenRouterError("OpenRouter returned a non-JSON response") from exc
        if not isinstance(payload, dict):
            raise OpenRouterError("OpenRouter returned an unexpected response shape")
        return payload


def _error_message(response: httpx.Response) -> str:
    """Turn an OpenRouter error body into something a user can act on."""
    fallback = f"OpenRouter returned HTTP {response.status_code}."
    try:
        payload = response.json()
    except ValueError:
        return fallback
    if not isinstance(payload, dict):
        return fallback
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()[:400]
    if isinstance(error, str) and error.strip():
        return error.strip()[:400]
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()[:400]
    return fallback


def _parse_json_object(text: str) -> dict[str, Any]:
    """Parse JSON from a model response, tolerating code fences."""
    candidate = text.strip()
    if candidate.startswith("```"):
        # Strip a ```json ... ``` fence.
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    try:
        parsed = json.loads(candidate)
    except ValueError as exc:
        raise OpenRouterError(
            "The orchestrator model did not return valid JSON.",
            detail=candidate[:200],
        ) from exc
    if not isinstance(parsed, dict):
        raise OpenRouterError("The orchestrator model did not return a JSON object.")
    return parsed
