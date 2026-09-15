from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from textual.widgets import OptionList, Static
import yaml

from codeshell.agent import Agent
from codeshell.app import CodeShellApp
from codeshell.client import LLMClient
from codeshell.commands.completion import CompletionPopup
from codeshell.config import ProviderConfig, load_config
from codeshell.conversation import ConversationManager
from codeshell.model_switching import (
    PreparedModelSwitch,
    get_available_models,
    prepare_model_switch,
)
from codeshell.skills.executor import SkillExecutor
from codeshell.tools.agent_tool import AgentTool
from codeshell.tools.base import StreamEvent


SENTINEL_KEY = "SENSITIVE_MODEL_SWITCH_KEY_123"


class FakeClient(LLMClient):
    def __init__(self, model: str) -> None:
        self.model = model
        self.requests: list[ConversationManager] = []

    async def stream(
        self,
        conversation: ConversationManager,
        system: str = "",
        tools: list[dict] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        self.requests.append(conversation)
        if False:
            yield


def _provider(
    *,
    model: str = "deepseek-flash",
    models: list[str] | None = None,
    protocol: str = "openai",
) -> ProviderConfig:
    return ProviderConfig(
        name="deepseek",
        protocol=protocol,
        base_url="https://example.test/v1",
        model=model,
        api_key=SENTINEL_KEY,
        thinking=True,
        context_window=64_000,
        max_output_tokens=4_096,
        models=models
        if models is not None
        else ["deepseek-flash", "deepseek-v4-pro"],
    )


@pytest.mark.parametrize("model", ["deepseek-flash", "deepseek-v4-pro"])
def test_prepare_model_switch_accepts_supported_models(model: str) -> None:
    source = _provider()
    calls: list[ProviderConfig] = []

    def factory(provider: ProviderConfig) -> LLMClient:
        calls.append(provider)
        return FakeClient(provider.model)

    prepared = prepare_model_switch(source, model, client_factory=factory)

    assert isinstance(prepared, PreparedModelSwitch)
    assert prepared.provider.model == model
    assert isinstance(prepared.client, FakeClient)
    assert prepared.client.model == model
    assert prepared.context_window == 64_000
    assert calls == [prepared.provider]


def test_prepare_model_switch_preserves_provider_and_source() -> None:
    source = _provider()
    source.set_fetched_context_window(123_456)

    prepared = prepare_model_switch(
        source,
        "deepseek-v4-pro",
        client_factory=lambda provider: FakeClient(provider.model),
    )

    assert source.model == "deepseek-flash"
    assert source._fetched_context_window == 123_456
    assert prepared.provider is not source
    assert prepared.provider.protocol == source.protocol
    assert prepared.provider.base_url == source.base_url
    assert prepared.provider.api_key == source.api_key
    assert prepared.provider.thinking == source.thinking
    assert prepared.provider.context_window == source.context_window
    assert prepared.provider.max_output_tokens == source.max_output_tokens
    assert prepared.provider._fetched_context_window == 0


@pytest.mark.parametrize(
    ("provider", "target"),
    [
        (_provider(models=["deepseek-flash"]), "deepseek-v4-pro"),
        (
            _provider(models=["deepseek-flash", "deepseek-v4-pro", "deepseek-r1"]),
            "deepseek-r1",
        ),
        (_provider(protocol="anthropic"), "deepseek-v4-pro"),
    ],
)
def test_prepare_model_switch_rejects_unavailable_models_before_factory(
    provider: ProviderConfig,
    target: str,
) -> None:
    calls = 0

    def factory(candidate: ProviderConfig) -> LLMClient:
        nonlocal calls
        calls += 1
        return FakeClient(candidate.model)

    with pytest.raises(ValueError, match="Available models"):
        prepare_model_switch(provider, target, client_factory=factory)

    assert calls == 0


def test_prepare_model_switch_propagates_factory_failure_without_mutation() -> None:
    source = _provider()

    def failing_factory(provider: ProviderConfig) -> LLMClient:
        raise RuntimeError("client setup failed")

    with pytest.raises(RuntimeError, match="client setup failed"):
        prepare_model_switch(
            source,
            "deepseek-v4-pro",
            client_factory=failing_factory,
        )

    assert source.model == "deepseek-flash"
    assert source.get_switchable_models() == (
        "deepseek-flash",
        "deepseek-v4-pro",
    )


def test_prepare_model_switch_repr_and_errors_do_not_expose_api_key() -> None:
    source = _provider()
    prepared = prepare_model_switch(
        source,
        "deepseek-v4-pro",
        client_factory=lambda provider: FakeClient(provider.model),
    )

    with pytest.raises(ValueError) as exc_info:
        prepare_model_switch(
            source,
            "not-a-model",
            client_factory=lambda provider: FakeClient(provider.model),
        )

    assert SENTINEL_KEY not in repr(prepared)
    assert SENTINEL_KEY not in str(exc_info.value)


def test_available_models_preserves_supported_order() -> None:
    provider = _provider(models=["deepseek-v4-pro", "deepseek-flash"])

    assert get_available_models(provider) == (
        "deepseek-flash",
        "deepseek-v4-pro",
    )


def test_available_models_rejects_non_deepseek_current_model() -> None:
    provider = ProviderConfig(
        name="openai",
        protocol="openai",
        base_url="https://example.test/v1",
        model="gpt-4.1",
        models=["gpt-4.1", "deepseek-flash", "deepseek-v4-pro"],
    )

    assert get_available_models(provider) == ()


def test_runtime_dependencies_update_model_refs_only() -> None:
    old_client = FakeClient("deepseek-flash")
    new_client = FakeClient("deepseek-v4-pro")
    registry = object()
    agent = Agent(
        client=old_client,
        registry=registry,  # type: ignore[arg-type]
        protocol="openai",
        context_window=64_000,
    )
    recovery_state = agent.recovery_state
    active_skills = agent.active_skills
    skill_executor = SkillExecutor(agent, old_client, "openai")
    old_provider = _provider()
    new_provider = old_provider.copy_for_model("deepseek-v4-pro")
    agent_tool = AgentTool(
        agent_loader=object(),  # type: ignore[arg-type]
        task_manager=object(),  # type: ignore[arg-type]
        trace_manager=object(),  # type: ignore[arg-type]
        parent_agent=agent,
        provider_config=old_provider,
    )

    agent.set_runtime_client(new_client, "openai-compat", 128_000)
    skill_executor.set_runtime_client(new_client, "openai-compat")
    agent_tool.set_provider_config(new_provider)

    assert agent.client is new_client
    assert agent.protocol == "openai-compat"
    assert agent.context_window == 128_000
    assert agent.registry is registry
    assert agent.recovery_state is recovery_state
    assert agent.active_skills is active_skills
    assert skill_executor.agent is agent
    assert skill_executor.client is new_client
    assert skill_executor.protocol == "openai-compat"
    assert agent_tool._parent_agent is agent
    assert agent_tool._provider_config is new_provider


def _app_without_full_initialization(
    provider: ProviderConfig,
) -> CodeShellApp:
    app = CodeShellApp([provider])

    def select_without_initialization(selected: ProviderConfig) -> None:
        app._selected_provider = selected

    app._select_provider = select_without_initialization  # type: ignore[method-assign]
    return app


@pytest.mark.asyncio
async def test_model_selector_marks_current_model_and_can_cancel() -> None:
    provider = _provider()
    app = _app_without_full_initialization(provider)

    async with app.run_test(size=(100, 40)) as pilot:
        panel = app.query_one("#model-select")
        assert panel.display is False

        app.show_model_selector(
            ("deepseek-flash", "deepseek-v4-pro"),
            "deepseek-flash",
        )
        await pilot.pause()

        options = list(app.query_one("#model-list", OptionList).options)
        assert panel.display is True
        assert [option.id for option in options] == [
            "deepseek-flash",
            "deepseek-v4-pro",
        ]
        assert "current" in str(options[0].prompt)
        assert "current" not in str(options[1].prompt)

        app.action_cancel()
        await pilot.pause()

        assert panel.display is False
        assert app._selected_provider is provider


@pytest.mark.asyncio
async def test_model_selector_selection_dispatches_switch() -> None:
    provider = _provider()
    app = _app_without_full_initialization(provider)
    switch = AsyncMock(return_value=True)
    app.switch_model = switch  # type: ignore[method-assign]

    async with app.run_test(size=(100, 40)) as pilot:
        app.show_model_selector(
            ("deepseek-flash", "deepseek-v4-pro"),
            "deepseek-flash",
        )
        option_list = app.query_one("#model-list", OptionList)
        option_list.highlighted = 1

        await pilot.press("enter")
        await pilot.pause()

        switch.assert_awaited_once_with("deepseek-v4-pro")
        assert app.query_one("#model-select").display is False


@pytest.mark.asyncio
async def test_model_selector_does_not_replace_provider_list() -> None:
    first = _provider()
    second = _provider(model="deepseek-v4-pro")
    second.name = "deepseek-secondary"
    app = CodeShellApp([first, second])

    async with app.run_test(size=(100, 40)) as pilot:
        app._selected_provider = first
        app.query_one("#input-area").display = True
        provider_list = app.query_one("#provider-list", OptionList)
        original_provider_ids = [option.id for option in provider_list.options]
        completion = app.query_one(CompletionPopup)
        completion.show(["/help", "/model"])
        assert completion.is_visible is True

        app.show_model_selector(
            ("deepseek-flash", "deepseek-v4-pro"),
            "deepseek-flash",
        )
        app.action_cancel()
        await pilot.pause()

        assert [option.id for option in provider_list.options] == original_provider_ids
        assert completion.is_visible is False


def _runtime_app(
    provider: ProviderConfig | None = None,
) -> tuple[
    CodeShellApp,
    FakeClient,
    Agent,
    SkillExecutor,
    AgentTool,
    list[str],
]:
    provider = provider or _provider()
    app = CodeShellApp([provider])
    old_client = FakeClient(provider.model)
    registry = app.registry
    agent = Agent(
        client=old_client,
        registry=registry,  # type: ignore[arg-type]
        protocol=provider.protocol,
        context_window=provider.get_context_window(),
    )
    skill_executor = SkillExecutor(agent, old_client, provider.protocol)
    agent_tool = AgentTool(
        agent_loader=object(),  # type: ignore[arg-type]
        task_manager=object(),  # type: ignore[arg-type]
        trace_manager=object(),  # type: ignore[arg-type]
        parent_agent=agent,
        provider_config=provider,
    )
    messages: list[str] = []
    app._selected_provider = provider
    app.client = old_client
    app.agent = agent
    app.skill_executor = skill_executor
    app._agent_tool = agent_tool
    app._show_system_message = messages.append  # type: ignore[method-assign]
    return app, old_client, agent, skill_executor, agent_tool, messages


def test_available_models_filters_protocol_and_preserves_fixed_order() -> None:
    app, *_ = _runtime_app(
        _provider(models=["deepseek-v4-pro", "deepseek-flash"])
    )
    assert app.get_available_models() == (
        "deepseek-flash",
        "deepseek-v4-pro",
    )

    app._selected_provider = _provider(protocol="anthropic")
    assert app.get_available_models() == ()


@pytest.mark.asyncio
async def test_busy_switch_and_selector_are_rejected_before_preparation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, old_client, *_rest, messages = _runtime_app()
    prepare = MagicMock()
    monkeypatch.setattr("codeshell.app.prepare_model_switch", prepare)
    app._streaming = True
    release = asyncio.Event()

    async def active_response() -> None:
        await release.wait()

    active_task = asyncio.create_task(active_response())
    app._agent_task = active_task

    try:
        switched = await app.switch_model("deepseek-v4-pro")
        app.show_model_selector(
            ("deepseek-flash", "deepseek-v4-pro"),
            "deepseek-flash",
        )

        assert switched is False
        assert app.client is old_client
        assert app._streaming is True
        assert app._agent_task is active_task
        assert active_task.done() is False
        assert prepare.call_count == 0
        assert len(messages) == 2
        assert all("等待" in message for message in messages)
    finally:
        release.set()
        await active_task


@pytest.mark.asyncio
async def test_same_model_is_rejected_without_preparation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, old_client, *_rest, messages = _runtime_app()
    prepare = MagicMock()
    monkeypatch.setattr("codeshell.app.prepare_model_switch", prepare)

    switched = await app.switch_model("deepseek-flash")

    assert switched is False
    assert app.client is old_client
    assert prepare.call_count == 0
    assert "已是当前模型" in messages[-1]


@pytest.mark.asyncio
async def test_invalid_model_is_rejected_without_runtime_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, old_client, agent, skill_executor, agent_tool, messages = _runtime_app()
    provider = app._selected_provider
    prepare = MagicMock()
    monkeypatch.setattr("codeshell.app.prepare_model_switch", prepare)

    switched = await app.switch_model("unsupported-model")

    assert switched is False
    assert app._selected_provider is provider
    assert app.client is old_client
    assert agent.client is old_client
    assert skill_executor.client is old_client
    assert agent_tool._provider_config is provider
    assert prepare.call_count == 0
    assert "deepseek-flash" in messages[-1]
    assert "deepseek-v4-pro" in messages[-1]


@pytest.mark.asyncio
async def test_non_deepseek_provider_is_rejected_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ProviderConfig(
        name="openai",
        protocol="openai",
        base_url="https://example.test/v1",
        model="gpt-4.1",
        models=["gpt-4.1", "deepseek-flash", "deepseek-v4-pro"],
    )
    app, old_client, *_rest, messages = _runtime_app(provider)
    prepare = MagicMock()
    monkeypatch.setattr("codeshell.app.prepare_model_switch", prepare)

    switched = await app.switch_model("deepseek-flash")

    assert switched is False
    assert app.client is old_client
    assert prepare.call_count == 0
    assert messages[-1] == "当前 Provider 不支持运行时模型切换。"


def _prepared(
    model: str,
    *,
    context_window: int = 64_000,
) -> PreparedModelSwitch:
    provider = _provider(model=model)
    provider.context_window = context_window
    client = FakeClient(model)
    return PreparedModelSwitch(
        provider=provider,
        client=client,
        context_window=provider.get_context_window(),
    )


@pytest.mark.asyncio
async def test_switch_success_updates_all_runtime_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, old_client, agent, skill_executor, agent_tool, messages = _runtime_app()
    old_registry = agent.registry
    old_recovery = agent.recovery_state
    old_conversation = app.conversation
    prepared = _prepared("deepseek-v4-pro", context_window=128_000)
    select_provider = MagicMock()
    init_mcp = AsyncMock()
    app._select_provider = select_provider  # type: ignore[method-assign]
    app._init_mcp = init_mcp  # type: ignore[method-assign]
    registered_tools = tuple(app.registry.list_tools())
    monkeypatch.setattr(
        "codeshell.app.prepare_model_switch",
        lambda provider, model: prepared,
    )

    switched = await app.switch_model("deepseek-v4-pro")

    assert switched is True
    assert app._selected_provider is prepared.provider
    assert app.client is prepared.client
    assert agent.client is prepared.client
    assert agent.protocol == prepared.provider.protocol
    assert agent.context_window == prepared.context_window
    assert skill_executor.client is prepared.client
    assert skill_executor.protocol == prepared.provider.protocol
    assert agent_tool._provider_config is prepared.provider
    assert agent.registry is old_registry
    assert agent.recovery_state is old_recovery
    assert app.conversation is old_conversation
    assert old_client is not prepared.client
    assert old_client.requests == []
    assert prepared.client.requests == []
    assert tuple(app.registry.list_tools()) == registered_tools
    select_provider.assert_not_called()
    init_mcp.assert_not_awaited()
    assert messages[-1] == "已切换模型: deepseek-v4-pro"

    await app._dispatch_command("/status")
    assert "128,000" in messages[-1]


@pytest.mark.asyncio
async def test_initialization_failure_keeps_old_runtime_and_hides_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, old_client, agent, skill_executor, agent_tool, messages = _runtime_app()
    old_provider = app._selected_provider

    def fail(provider: ProviderConfig, model: str) -> PreparedModelSwitch:
        raise RuntimeError(f"failed with {SENTINEL_KEY}")

    monkeypatch.setattr("codeshell.app.prepare_model_switch", fail)

    switched = await app.switch_model("deepseek-v4-pro")

    assert switched is False
    assert app._selected_provider is old_provider
    assert app.client is old_client
    assert agent.client is old_client
    assert skill_executor.client is old_client
    assert agent_tool._provider_config is old_provider
    assert SENTINEL_KEY not in messages[-1]
    async for _event in old_client.stream(app.conversation):
        pass
    assert old_client.requests == [app.conversation]


@pytest.mark.asyncio
async def test_rollback_restores_all_runtime_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, old_client, agent, skill_executor, agent_tool, messages = _runtime_app()
    old_provider = app._selected_provider
    old_agent_state = (agent.client, agent.protocol, agent.context_window)
    old_skill_state = (skill_executor.client, skill_executor.protocol)
    prepared = _prepared("deepseek-v4-pro")
    monkeypatch.setattr(
        "codeshell.app.prepare_model_switch",
        lambda provider, model: prepared,
    )
    original_set_provider = agent_tool.set_provider_config

    def fail_for_new_provider(provider: ProviderConfig) -> None:
        if provider is prepared.provider:
            raise RuntimeError("commit failed")
        original_set_provider(provider)

    monkeypatch.setattr(agent_tool, "set_provider_config", fail_for_new_provider)

    switched = await app.switch_model("deepseek-v4-pro")

    assert switched is False
    assert app._selected_provider is old_provider
    assert app.client is old_client
    assert (agent.client, agent.protocol, agent.context_window) == old_agent_state
    assert (skill_executor.client, skill_executor.protocol) == old_skill_state
    assert agent_tool._provider_config is old_provider
    assert messages[-1] == "模型切换失败，已继续使用 deepseek-flash。"


@pytest.mark.asyncio
async def test_direct_and_selector_end_to_end_paths_preserve_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _old_client, agent, _skill_executor, agent_tool, _messages = _runtime_app()
    app._select_provider = lambda provider: None  # type: ignore[method-assign]
    session = object()
    memory_manager = object()
    mcp_manager = object()
    team_manager = object()
    task_manager = app.task_manager
    conversation = app.conversation
    registry = app.registry
    permission_mode = agent.permission_mode
    app.session = session  # type: ignore[assignment]
    app.memory_manager = memory_manager  # type: ignore[assignment]
    app.mcp_manager = mcp_manager  # type: ignore[assignment]
    app.team_manager = team_manager

    prepared_by_model = {
        model: _prepared(model)
        for model in ("deepseek-flash", "deepseek-v4-pro")
    }
    monkeypatch.setattr(
        "codeshell.app.prepare_model_switch",
        lambda provider, model: prepared_by_model[model],
    )

    async with app.run_test(size=(100, 40)) as pilot:
        chat_input = app.query_one("#chat-input")
        chat_input.focus()
        chat_input.insert("/model deepseek-v4-pro")
        await pilot.press("enter")
        await pilot.pause()

        assert app.get_current_model() == "deepseek-v4-pro"
        assert "deepseek-v4-pro" in str(
            app.query_one("#model-label", Static).render()
        )
        v4_client = prepared_by_model["deepseek-v4-pro"].client
        assert agent.client is v4_client
        async for _event in agent.client.stream(conversation):
            pass
        assert isinstance(v4_client, FakeClient)
        assert v4_client.requests == [conversation]

        chat_input.focus()
        chat_input.insert("/model")
        await pilot.press("enter")
        await pilot.pause()
        options = list(app.query_one("#model-list", OptionList).options)
        assert "current" in str(options[1].prompt)

        model_list = app.query_one("#model-list", OptionList)
        model_list.highlighted = 0
        await pilot.press("enter")
        await pilot.pause()

        assert app.get_current_model() == "deepseek-flash"
        flash_client = prepared_by_model["deepseek-flash"].client
        assert agent.client is flash_client
        async for _event in agent.client.stream(conversation):
            pass
        assert isinstance(flash_client, FakeClient)
        assert flash_client.requests == [conversation]

    assert app.session is session
    assert app.conversation is conversation
    assert app.registry is registry
    assert app.memory_manager is memory_manager
    assert app.mcp_manager is mcp_manager
    assert app.team_manager is team_manager
    assert app.task_manager is task_manager
    assert agent.permission_mode is permission_mode
    assert agent_tool._provider_config.model == "deepseek-flash"


@pytest.mark.asyncio
async def test_runtime_switch_does_not_persist_to_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "providers": [
                    {
                        "name": "deepseek",
                        "protocol": "openai",
                        "base_url": "https://example.test/v1",
                        "model": "deepseek-flash",
                        "models": [
                            "deepseek-flash",
                            "deepseek-v4-pro",
                        ],
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    before = config_path.read_bytes()
    provider = load_config(config_path).providers[0]
    app, *_ = _runtime_app(provider)
    prepared_by_model = {
        model: _prepared(model)
        for model in ("deepseek-flash", "deepseek-v4-pro")
    }
    monkeypatch.setattr(
        "codeshell.app.prepare_model_switch",
        lambda current, model: prepared_by_model[model],
    )

    assert await app.switch_model("deepseek-v4-pro") is True
    assert await app.switch_model("deepseek-flash") is True

    assert config_path.read_bytes() == before
    reloaded = load_config(config_path).providers[0]
    assert reloaded.model == "deepseek-flash"
    assert reloaded.get_switchable_models() == (
        "deepseek-flash",
        "deepseek-v4-pro",
    )


@pytest.mark.asyncio
async def test_existing_background_task_survives_and_future_agent_uses_new_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, *_rest, agent_tool, _messages = _runtime_app()
    release = asyncio.Event()

    async def background_work() -> None:
        await release.wait()

    background_task = asyncio.create_task(background_work())
    app._subagent_task = background_task
    prepared = _prepared("deepseek-v4-pro")
    monkeypatch.setattr(
        "codeshell.app.prepare_model_switch",
        lambda provider, model: prepared,
    )

    try:
        assert await app.switch_model("deepseek-v4-pro") is True
        assert app._subagent_task is background_task
        assert background_task.done() is False
        assert agent_tool._provider_config is prepared.provider
    finally:
        release.set()
        await background_task


@pytest.mark.asyncio
async def test_memory_prefetch_uses_switched_provider_without_replacing_manager(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, *_ = _runtime_app()
    memory_manager = MagicMock()
    memory_manager.user_mem_dir = tmp_path / "user-memory"
    memory_manager.project_mem_dir = tmp_path / "project-memory"
    app.memory_manager = memory_manager
    prepared = _prepared("deepseek-v4-pro")
    monkeypatch.setattr(
        "codeshell.app.prepare_model_switch",
        lambda provider, model: prepared,
    )
    side_providers: list[ProviderConfig] = []

    def side_client_factory(provider: ProviderConfig) -> LLMClient:
        side_providers.append(provider)
        return FakeClient(provider.model)

    async def fake_find_relevant_memories(**kwargs: object) -> list:
        selector = kwargs["selector"]
        await selector("system", "query")  # type: ignore[operator]
        return []

    monkeypatch.setattr("codeshell.app.create_client", side_client_factory)
    monkeypatch.setattr(
        "codeshell.app.find_relevant_memories",
        fake_find_relevant_memories,
    )

    assert await app.switch_model("deepseek-v4-pro") is True
    result = await app._prefetch_relevant_memories("remember this")

    assert result.paths == []
    assert result.reminder == ""
    assert app.memory_manager is memory_manager
    assert side_providers == [prepared.provider]
