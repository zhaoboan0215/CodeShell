from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from codeshell.client import LLMClient, create_client
from codeshell.config import ProviderConfig


SUPPORTED_DEEPSEEK_MODELS = (
    "deepseek-flash",
    "deepseek-v4-pro",
)
SUPPORTED_DEEPSEEK_PROTOCOLS = {"openai", "openai-compat"}

ClientFactory = Callable[[ProviderConfig], LLMClient]


@dataclass(frozen=True)
class PreparedModelSwitch:
    provider: ProviderConfig = field(repr=False)
    client: LLMClient = field(repr=False)
    context_window: int


def get_available_models(provider: ProviderConfig) -> tuple[str, ...]:
    if provider.protocol not in SUPPORTED_DEEPSEEK_PROTOCOLS:
        return ()
    if provider.model not in SUPPORTED_DEEPSEEK_MODELS:
        return ()
    configured = set(provider.get_switchable_models())
    return tuple(
        model for model in SUPPORTED_DEEPSEEK_MODELS if model in configured
    )


def prepare_model_switch(
    provider: ProviderConfig,
    model: str,
    *,
    client_factory: ClientFactory = create_client,
) -> PreparedModelSwitch:
    available = get_available_models(provider)
    if model not in available:
        supported = ", ".join(SUPPORTED_DEEPSEEK_MODELS)
        raise ValueError(
            f"Unsupported model '{model}'. Available models: {supported}"
        )

    candidate = provider.copy_for_model(model)
    client = client_factory(candidate)
    return PreparedModelSwitch(
        provider=candidate,
        client=client,
        context_window=candidate.get_context_window(),
    )
