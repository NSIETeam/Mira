"""Built-in provider factory adapters for providers awaiting package split."""

from __future__ import annotations

from mira.config.schema import Config, ModelPresetConfig, ProviderConfig
from mira.providers.base import LLMProvider
from mira.providers.registry import ProviderSpec


def create_azure_openai_provider(
    *,
    config: Config,
    provider_config: ProviderConfig | None,
    spec: ProviderSpec,
    model: str,
    preset: ModelPresetConfig,
) -> LLMProvider:
    del config, spec, preset
    from mira.providers.azure_openai_provider import AzureOpenAIProvider

    if not provider_config or not provider_config.api_base:
        raise ValueError("Azure OpenAI requires api_base in config.")
    return AzureOpenAIProvider(
        api_key=provider_config.api_key or "",
        api_base=provider_config.api_base,
        default_model=model,
    )


def create_openai_codex_provider(
    *,
    config: Config,
    provider_config: ProviderConfig | None,
    spec: ProviderSpec,
    model: str,
    preset: ModelPresetConfig,
) -> LLMProvider:
    del config, spec, preset
    from mira.providers.openai_codex_provider import OpenAICodexProvider

    return OpenAICodexProvider(
        default_model=model,
        proxy=getattr(provider_config, "proxy", None) if provider_config else None,
        extra_body=provider_config.extra_body if provider_config else None,
    )


def create_xai_grok_provider(
    *,
    config: Config,
    provider_config: ProviderConfig | None,
    spec: ProviderSpec,
    model: str,
    preset: ModelPresetConfig,
) -> LLMProvider:
    del config, spec, preset
    from mira.providers.xai_grok_provider import XAIGrokProvider

    return XAIGrokProvider(
        default_model=model,
        proxy=getattr(provider_config, "proxy", None) if provider_config else None,
        extra_body=provider_config.extra_body if provider_config else None,
    )


def create_github_copilot_provider(
    *,
    config: Config,
    provider_config: ProviderConfig | None,
    spec: ProviderSpec,
    model: str,
    preset: ModelPresetConfig,
) -> LLMProvider:
    del config, provider_config, spec, preset
    from mira.providers.github_copilot_provider import GitHubCopilotProvider

    return GitHubCopilotProvider(default_model=model)


def create_bedrock_provider(
    *,
    config: Config,
    provider_config: ProviderConfig | None,
    spec: ProviderSpec,
    model: str,
    preset: ModelPresetConfig,
) -> LLMProvider:
    del config, spec, preset
    from mira.providers.bedrock_provider import BedrockProvider

    return BedrockProvider(
        api_key=provider_config.api_key if provider_config else None,
        api_base=provider_config.api_base if provider_config else None,
        default_model=model,
        region=getattr(provider_config, "region", None) if provider_config else None,
        profile=getattr(provider_config, "profile", None) if provider_config else None,
        extra_body=provider_config.extra_body if provider_config else None,
    )
