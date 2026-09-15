from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from codeshell.config import (
    ConfigDiscovery,
    ConfigError,
    ProviderConfig,
    discover_config,
    load_config,
    load_config_with_discovery,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_config(path: Path, *, name: str = "test") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "providers:\n"
        f"  - name: {name}\n"
        "    protocol: openai\n"
        "    base_url: https://example.test\n"
        "    model: gpt-4.1\n",
        encoding="utf-8",
    )
    return path


def _write_provider_entry(path: Path, entry: dict) -> Path:
    path.write_text(
        yaml.safe_dump({"providers": [entry]}, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _provider_entry(**overrides: object) -> dict:
    entry = {
        "name": "deepseek",
        "protocol": "openai",
        "base_url": "https://example.test",
        "model": "deepseek-flash",
    }
    entry.update(overrides)
    return entry


def test_example_config_is_valid_and_contains_no_key() -> None:
    example = REPO_ROOT / "config.yaml"
    raw = yaml.safe_load(example.read_text(encoding="utf-8"))

    config = load_config(example)

    assert config.providers[0].name == "deepseek-official"
    assert raw["providers"][0].get("api_key", "") == ""
    assert "sk-" not in example.read_text(encoding="utf-8").lower()
    assert [server.name for server in config.mcp_servers] == [
        server["name"] for server in raw.get("mcp_servers", [])
    ]


def test_discover_config_preserves_layer_order(tmp_path: Path) -> None:
    home = tmp_path / "user"
    project = tmp_path / "project"
    global_config = _write_config(home / ".codeshell" / "config.yaml", name="global")
    project_config = _write_config(project / ".codeshell" / "config.yaml", name="project")
    local_config = _write_config(project / ".codeshell" / "config.local.yaml", name="local")

    discovery = discover_config(cwd=project, home=home)

    assert discovery == ConfigDiscovery(
        paths=(global_config, project_config, local_config),
        using_example=False,
    )


def test_example_is_used_only_when_user_configs_are_absent(tmp_path: Path) -> None:
    home = tmp_path / "user"
    project = tmp_path / "project"
    example = _write_config(project / "config.yaml", name="example")

    config, discovery = load_config_with_discovery(cwd=project, home=home)

    assert config.providers[0].name == "example"
    assert discovery == ConfigDiscovery(paths=(example,), using_example=True)

    project_config = _write_config(project / ".codeshell" / "config.yaml", name="project")
    config, discovery = load_config_with_discovery(cwd=project, home=home)
    assert config.providers[0].name == "project"
    assert discovery == ConfigDiscovery(paths=(project_config,), using_example=False)


def test_example_fallback_is_read_only(tmp_path: Path) -> None:
    home = tmp_path / "user"
    project = tmp_path / "project"
    example = _write_config(project / "config.yaml", name="example")
    before = example.read_bytes()

    load_config_with_discovery(cwd=project, home=home)
    load_config_with_discovery(cwd=project, home=home)

    assert example.read_bytes() == before
    assert not (project / ".codeshell").exists()


def test_explicit_missing_path_never_uses_example(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_config(project / "config.yaml", name="example")
    missing = project / "missing.yaml"

    with pytest.raises(ConfigError, match="Config file not found") as exc_info:
        load_config_with_discovery(path=missing, cwd=project, home=tmp_path / "user")

    message = str(exc_info.value)
    assert "name, protocol, base_url, model" in message
    assert "codeshell doctor --offline" in message


def test_missing_config_error_is_actionable_and_secret_free(tmp_path: Path) -> None:
    project = tmp_path / "project"
    home = tmp_path / "user"
    secret = "SENSITIVE_TEST_KEY_123"

    with pytest.raises(ConfigError) as exc_info:
        load_config_with_discovery(cwd=project, home=home)

    message = str(exc_info.value)
    assert str(project / ".codeshell" / "config.yaml") in message
    assert str(home / ".codeshell" / "config.yaml") in message
    assert "config.yaml" in message
    assert "name, protocol, base_url, model" in message
    assert "codeshell doctor --offline" in message
    assert secret not in message


def test_invalid_yaml_and_missing_fields_include_source_path(tmp_path: Path) -> None:
    invalid_yaml = tmp_path / "invalid.yaml"
    invalid_yaml.write_text("providers: [", encoding="utf-8")
    with pytest.raises(ConfigError, match=str(invalid_yaml)):
        load_config(invalid_yaml)

    missing_fields = tmp_path / "missing-fields.yaml"
    missing_fields.write_text("providers:\n  - name: broken\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=str(missing_fields)):
        load_config(missing_fields)


def test_provider_models_fall_back_to_default_for_legacy_config(tmp_path: Path) -> None:
    path = _write_provider_entry(tmp_path / "legacy.yaml", _provider_entry())

    provider = load_config(path).providers[0]

    assert provider.models == ["deepseek-flash"]
    assert provider.get_switchable_models() == ("deepseek-flash",)


def test_provider_models_load_in_configured_order(tmp_path: Path) -> None:
    models = ["deepseek-flash", "deepseek-v4-pro"]
    path = _write_provider_entry(
        tmp_path / "models.yaml",
        _provider_entry(models=models),
    )

    provider = load_config(path).providers[0]

    assert provider.models == models
    assert provider.get_switchable_models() == tuple(models)


def test_empty_provider_models_fall_back_to_default(tmp_path: Path) -> None:
    path = _write_provider_entry(
        tmp_path / "empty-models.yaml",
        _provider_entry(models=[]),
    )

    provider = load_config(path).providers[0]

    assert provider.models == ["deepseek-flash"]


@pytest.mark.parametrize(
    "models",
    [
        "deepseek-flash",
        ["deepseek-flash", 123],
        ["deepseek-flash", ""],
        ["deepseek-flash", "deepseek-flash"],
    ],
)
def test_invalid_provider_models_are_rejected(
    tmp_path: Path,
    models: object,
) -> None:
    path = _write_provider_entry(
        tmp_path / "invalid-models.yaml",
        _provider_entry(models=models),
    )

    with pytest.raises(ConfigError, match="models"):
        load_config(path)


def test_provider_models_must_include_default_model(tmp_path: Path) -> None:
    path = _write_provider_entry(
        tmp_path / "missing-default.yaml",
        _provider_entry(models=["deepseek-v4-pro"]),
    )

    with pytest.raises(ConfigError, match="must be included in models"):
        load_config(path)


def test_provider_copy_for_model_preserves_config_and_resets_runtime_cache() -> None:
    provider = ProviderConfig(
        name="deepseek",
        protocol="openai",
        base_url="https://example.test",
        model="deepseek-flash",
        api_key="SENSITIVE_TEST_KEY",
        thinking=True,
        context_window=64_000,
        max_output_tokens=4_096,
        models=["deepseek-flash", "deepseek-v4-pro"],
    )
    provider.set_fetched_context_window(123_456)

    copied = provider.copy_for_model("deepseek-v4-pro")

    assert provider.model == "deepseek-flash"
    assert provider._fetched_context_window == 123_456
    assert copied.model == "deepseek-v4-pro"
    assert copied._fetched_context_window == 0
    assert copied.models == provider.models
    assert copied.models is not provider.models
    assert copied.protocol == provider.protocol
    assert copied.base_url == provider.base_url
    assert copied.api_key == provider.api_key
    assert copied.thinking == provider.thinking
    assert copied.context_window == provider.context_window
    assert copied.max_output_tokens == provider.max_output_tokens
