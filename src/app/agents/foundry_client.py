"""Azure AI Foundry client/service abstraction (azure-ai-projects ~= 2.2.0).

Chosen pattern: **Hybrid, Foundry-first for inference.** Azure AI Foundry is the
system of record for the model deployment and (optionally) a persisted agent. This
module wraps the SDK behind a tiny, stable interface (`generate`) and degrades
gracefully to a deterministic local composer when Foundry is not configured — so
the prototype always runs.

Key v2 patterns used (guarded by soft imports so the prototype runs without the
SDK installed or credentials present):
  - Entra ID auth via ``DefaultAzureCredential`` + ``get_bearer_token_provider``.
  - ``AzureOpenAI(azure_endpoint=<account endpoint>, ...)`` for chat completions
    against the account's model deployment. (The azure-ai-projects 2.2.0 project
    client's ``get_openai_client`` does not accept ``api_version`` and its
    ``/openai/v1`` route does not serve every deployment, so we bind directly to
    the account endpoint instead.)

TODO(prod): if you adopt persisted Foundry **agents** (server-side tools, threads),
add an `agents` path here using the project's agents API and select via
settings.azure_ai_agent_id. Verify exact symbols against the installed SDK version.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger("app.agents.foundry")


class FoundryClient:
    """Thin wrapper over the Azure AI Foundry project client."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._openai_client: object | None = None
        self._available = False
        if self._settings.foundry_ready:
            self._available = self._try_init()

    @property
    def available(self) -> bool:
        """True when Foundry is configured and the SDK initialized successfully."""
        return self._available

    def _try_init(self) -> bool:
        try:
            from azure.identity import (
                DefaultAzureCredential,
                get_bearer_token_provider,
            )
            from openai import AzureOpenAI
        except ImportError:
            logger.warning(
                "foundry_sdk_unavailable",
                extra={"hint": "uv add azure-ai-projects azure-identity openai"},
            )
            return False

        try:
            # Preferred path: route through the APIM AI-gateway (token limits,
            # token metrics, semantic cache, managed-identity backend auth). The
            # gateway exposes the standard /openai route and accepts the APIM
            # subscription key via the api-key header, so the stock client works
            # unchanged. Falls back to a direct Entra-auth call to Foundry.
            if self._settings.model_gateway_ready:
                self._openai_client = AzureOpenAI(
                    azure_endpoint=self._settings.azure_openai_gateway_endpoint.rstrip(
                        "/"
                    ),
                    api_key=self._settings.azure_openai_gateway_key,
                    api_version=self._settings.azure_openai_api_version,
                )
                logger.info(
                    "foundry_initialized",
                    extra={
                        "deployment": self._settings.azure_ai_model_deployment,
                        "transport": "apim_gateway",
                    },
                )
                return True

            # azure-ai-projects 2.2.0's project.get_openai_client() does not accept
            # api_version and its /openai/v1 route does not serve all deployments, so
            # we bind an AzureOpenAI client to the account endpoint with Entra auth.
            token_provider = get_bearer_token_provider(
                DefaultAzureCredential(),
                "https://cognitiveservices.azure.com/.default",
            )
            self._openai_client = AzureOpenAI(
                azure_endpoint=self._settings.account_endpoint,
                azure_ad_token_provider=token_provider,
                api_version=self._settings.azure_openai_api_version,
            )
            logger.info(
                "foundry_initialized",
                extra={
                    "deployment": self._settings.azure_ai_model_deployment,
                    "transport": "direct",
                },
            )
            return True
        except Exception as exc:  # noqa: BLE001 - prototype must not crash on auth issues
            logger.warning("foundry_init_failed", extra={"detail": str(exc)})
            return False

    async def generate(self, system_prompt: str, user_prompt: str) -> str | None:
        """Generate a completion via Foundry, or None if unavailable/failed."""
        if not self._available or self._openai_client is None:
            return None
        try:
            # The OpenAI-compatible client is synchronous; call inline. For high
            # throughput, wrap in a threadpool or use the async client variant.
            client = self._openai_client
            completion = client.chat.completions.create(  # type: ignore[attr-defined]
                model=self._settings.azure_ai_model_deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=600,
            )
            content = completion.choices[0].message.content
            return str(content) if content is not None else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("foundry_generate_failed", extra={"detail": str(exc)})
            return None


@lru_cache(maxsize=1)
def get_foundry_client() -> FoundryClient:
    """Return a cached Foundry client."""
    return FoundryClient()
