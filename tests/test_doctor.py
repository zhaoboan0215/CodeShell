from __future__ import annotations

from pathlib import Path

import pytest

from codeshell.config import MCPServerConfig
from codeshell.doctor import (
    CheckStatus,
    DiagnosticResult,
    DoctorReport,
    _safe_provider_failure,
    check_mcp_dependencies,
    check_project_files,
    check_python,
    probe_provider,
    run_doctor,
)


def _write_project(
    root: Path,
    *,
    api_key: str = "TEST_DOCTOR_KEY_987",
    model: str = "gpt-test",
    mcp: str = "",
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (root / "config.yaml").write_text(
        "providers:\n"
        "  - name: test-provider\n"
        "    protocol: openai\n"
        "    base_url: https://example.test\n"
        f"    model: {model}\n"
        f"    api_key: {api_key!r}\n"
        f"{mcp}",
        encoding="utf-8",
    )


def test_report_renders_statuses_and_summary() -> None:
    report = DoctorReport(
        (
            DiagnosticResult("one", CheckStatus.PASS, "ok"),
            DiagnosticResult("two", CheckStatus.WARN, "optional", "install it"),
            DiagnosticResult("three", CheckStatus.FAIL, "broken", critical=False),
        )
    )

    rendered = report.render()

    assert "[PASS] one: ok" in rendered
    assert "[WARN] two: optional" in rendered
    assert "Fix: install it" in rendered
    assert "1 passed, 1 warning, 1 failed" in rendered
    assert report.exit_code == 0


def test_report_returns_one_for_critical_failure() -> None:
    report = DoctorReport(
        (DiagnosticResult("critical", CheckStatus.FAIL, "broken", critical=True),)
    )
    assert report.exit_code == 1


def test_python_check_accepts_supported_and_rejects_old_version() -> None:
    assert check_python((3, 11, 0)).status == CheckStatus.PASS
    old = check_python((3, 10, 14))
    assert old.status == CheckStatus.FAIL
    assert old.critical is True
    assert "3.11" in old.remediation


def test_project_file_checks_name_each_missing_file(tmp_path: Path) -> None:
    results = check_project_files(tmp_path)
    assert [result.name for result in results] == ["pyproject.toml", "uv.lock"]
    assert all(result.status == CheckStatus.FAIL for result in results)

    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    assert all(result.status == CheckStatus.PASS for result in check_project_files(tmp_path))


def test_mcp_checks_node_and_npx_for_npx_server() -> None:
    server = MCPServerConfig(name="context7", command="npx")
    found = {"node": "/bin/node", "npx": "/bin/npx"}

    results = check_mcp_dependencies([server], found.get)

    assert [result.name for result in results] == [
        "MCP context7 / node",
        "MCP context7 / npx",
    ]
    assert all(result.status == CheckStatus.PASS for result in results)


def test_mcp_missing_command_warns_without_being_critical() -> None:
    server = MCPServerConfig(name="custom", command="missing-tool")
    result = check_mcp_dependencies([server], lambda _command: None)[0]
    assert result.status == CheckStatus.WARN
    assert result.critical is False
    assert "missing-tool" in result.remediation


def test_http_and_unconfigured_mcp_do_not_require_node() -> None:
    called: list[str] = []

    no_mcp = check_mcp_dependencies([], lambda command: called.append(command))
    http_mcp = check_mcp_dependencies(
        [MCPServerConfig(name="remote", url="https://example.test/mcp")],
        lambda command: called.append(command),
    )

    assert no_mcp[0].status == CheckStatus.PASS
    assert http_mcp[0].status == CheckStatus.PASS
    assert called == []


@pytest.mark.asyncio
async def test_doctor_offline_is_secret_free_and_never_calls_probe(tmp_path: Path) -> None:
    project = tmp_path / "project"
    secret = "TEST_DOCTOR_KEY_987"
    _write_project(project, api_key=secret)

    async def forbidden_probe(_provider):
        raise AssertionError("offline mode must not call the provider")

    report = await run_doctor(
        cwd=project,
        home=tmp_path / "home",
        online=False,
        provider_probe=forbidden_probe,
    )
    rendered = report.render()

    assert report.exit_code == 0
    assert "configured" in rendered
    assert "network check skipped" in rendered
    assert secret not in rendered


@pytest.mark.asyncio
async def test_doctor_online_uses_injected_probe(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project)
    seen: list[str] = []

    async def passing_probe(provider):
        seen.append(provider.model)
        return DiagnosticResult("Provider test-provider", CheckStatus.PASS, "reachable")

    report = await run_doctor(
        cwd=project,
        home=tmp_path / "home",
        provider_probe=passing_probe,
    )

    assert seen == ["gpt-test"]
    assert report.exit_code == 0
    assert "reachable" in report.render()


@pytest.mark.asyncio
async def test_doctor_maps_probe_exception_without_leaking_message(tmp_path: Path) -> None:
    project = tmp_path / "project"
    secret = "TEST_DOCTOR_KEY_987"
    _write_project(project, api_key=secret)

    class APIConnectionError(Exception):
        pass

    async def failing_probe(_provider):
        raise APIConnectionError(f"request failed with {secret}")

    report = await run_doctor(
        cwd=project,
        home=tmp_path / "home",
        provider_probe=failing_probe,
    )

    assert report.exit_code == 1
    assert "network connection failed" in report.render()
    assert secret not in report.render()


@pytest.mark.asyncio
async def test_missing_key_is_critical_and_skips_probe(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project, api_key="")

    async def forbidden_probe(_provider):
        raise AssertionError("missing keys must skip provider probing")

    report = await run_doctor(
        cwd=project,
        home=tmp_path / "home",
        online=True,
        provider_probe=forbidden_probe,
    )

    assert report.exit_code == 1
    assert "not configured" in report.render()


@pytest.mark.asyncio
async def test_invalid_config_stops_dependent_checks(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("", encoding="utf-8")
    (project / "uv.lock").write_text("", encoding="utf-8")
    (project / "config.yaml").write_text("providers: [", encoding="utf-8")

    report = await run_doctor(cwd=project, home=tmp_path / "home", online=False)

    assert report.exit_code == 1
    assert "Configuration" in report.render()
    assert "API key" not in report.render()
    assert "Traceback" not in report.render()


@pytest.mark.asyncio
async def test_doctor_is_read_only_across_repeated_runs(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project)
    before = {path: path.read_bytes() for path in project.iterdir()}

    await run_doctor(cwd=project, home=tmp_path / "home", online=False)
    await run_doctor(cwd=project, home=tmp_path / "home", online=False)

    after = {path: path.read_bytes() for path in project.iterdir()}
    assert after == before


@pytest.mark.parametrize(
    ("error_type", "expected"),
    [
        ("AuthenticationError", "authentication failed"),
        ("APIConnectionError", "network connection failed"),
        ("NotFoundError", "was not found"),
        ("APIStatusError", "provider returned"),
    ],
)
def test_provider_errors_are_classified_without_messages(error_type: str, expected: str) -> None:
    from codeshell.config import ProviderConfig

    provider = ProviderConfig("demo", "openai", "https://example.test", "model-x", "secret")
    error_class = type(error_type, (Exception,), {})
    result = _safe_provider_failure(provider, error_class("secret payload"))

    assert result.status == CheckStatus.FAIL
    assert result.critical is True
    assert expected in result.detail
    assert "secret payload" not in result.detail


@pytest.mark.asyncio
async def test_openai_compatible_probe_reads_models_from_page_data(monkeypatch) -> None:
    from codeshell.config import ProviderConfig

    class Model:
        def __init__(self, model_id: str) -> None:
            self.id = model_id

    class ModelPage:
        def __init__(self) -> None:
            self.data = [Model("deepseek-flash"), Model("deepseek-v4-pro")]

    class ModelsResource:
        async def list(self) -> ModelPage:
            return ModelPage()

    class FakeAsyncOpenAI:
        def __init__(self, **_kwargs) -> None:
            self.models = ModelsResource()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("codeshell.doctor.AsyncOpenAI", FakeAsyncOpenAI)
    provider = ProviderConfig(
        "deepseek-official",
        "openai",
        "https://api.deepseek.com",
        "deepseek-flash",
        "secret",
    )

    result = await probe_provider(provider)

    assert result.status == CheckStatus.PASS
    assert "deepseek-flash" in result.detail


@pytest.mark.asyncio
async def test_openai_compatible_probe_rejects_unlisted_model(monkeypatch) -> None:
    from codeshell.config import ProviderConfig

    class ModelPage:
        data = [type("Model", (), {"id": "available-model"})()]

    class ModelsResource:
        async def list(self) -> ModelPage:
            return ModelPage()

    class FakeAsyncOpenAI:
        def __init__(self, **_kwargs) -> None:
            self.models = ModelsResource()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("codeshell.doctor.AsyncOpenAI", FakeAsyncOpenAI)
    provider = ProviderConfig(
        "compatible",
        "openai-compat",
        "https://example.test/v1",
        "missing-model",
        "secret",
    )

    result = await probe_provider(provider)

    assert result.status == CheckStatus.FAIL
    assert result.critical is True
    assert "missing-model" in result.detail
