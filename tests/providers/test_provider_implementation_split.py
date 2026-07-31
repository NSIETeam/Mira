from __future__ import annotations

from mira.providers.registry import (
    CORE_PROVIDER_BACKENDS,
    ProviderSpec,
    find_by_name,
    provider_implementation_summary,
    provider_implementation_violations,
)


def test_builtin_provider_registry_has_explicit_split_boundary() -> None:
    summary = provider_implementation_summary()

    assert summary["core_backends"] == list(CORE_PROVIDER_BACKENDS)
    assert summary["violations"] == []
    assert set(summary["openai_compat_migrations"]) >= {
        "azure_openai",
        "openai_codex",
        "xai_grok",
    }
    assert {"name": "bedrock", "package": "mira-provider-bedrock"} in summary[
        "split_packages"
    ]
    assert {"name": "github_copilot", "package": "mira-provider-copilot"} in summary[
        "split_packages"
    ]


def test_native_backends_must_not_remain_unmarked_core() -> None:
    violations = provider_implementation_violations((
        ProviderSpec(
            name="native_test",
            keywords=("native-test",),
            env_key="",
            backend="native_test",
        ),
    ))

    assert violations == ["native_test: backend 'native_test' is not allowed in core"]


def test_split_package_and_external_factory_specs_pass_split_audit() -> None:
    violations = provider_implementation_violations((
        ProviderSpec(
            name="split_test",
            keywords=("split-test",),
            env_key="",
            backend="split_test",
            implementation_status="split_package",
            split_package="mira-provider-split-test",
        ),
        ProviderSpec(
            name="factory_test",
            keywords=("factory-test",),
            env_key="",
            backend="factory_test",
            provider_factory="mira_provider_factory_test:create_provider",
        ),
    ))

    assert violations == []


def test_named_split_specs_expose_migration_metadata() -> None:
    assert find_by_name("azure_openai").migration_target == "openai_compat"
    assert find_by_name("openai_codex").migration_target == "openai_compat"
    assert find_by_name("xai_grok").migration_target == "openai_compat"
    assert find_by_name("bedrock").split_package == "mira-provider-bedrock"
    assert find_by_name("github_copilot").split_package == "mira-provider-copilot"
