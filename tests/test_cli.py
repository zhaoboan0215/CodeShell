from __future__ import annotations

from importlib.metadata import version as package_version
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import codeshell
import codeshell.__main__ as cli
from codeshell.client import AuthenticationError
from codeshell.config import AppConfig, ProviderConfig
from codeshell.doctor import CheckStatus, DiagnosticResult, DoctorReport


def test_version_matches_installed_package_metadata() -> None:
    assert codeshell.__version__ == package_version("codeshell")
    assert codeshell.__version__.count(".") >= 1


def test_version_has_source_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_package(_name: str) -> str:
        raise codeshell.PackageNotFoundError

    monkeypatch.setattr(codeshell, "package_version", missing_package)
    assert codeshell._resolve_version() == "0.2.0"


def test_parser_keeps_existing_options() -> None:
    args = cli.build_parser().parse_args(
        ["--mode", "plan", "-p", "hello", "--output-format", "stream-json"]
    )
    assert args.mode == "plan"
    assert args.p == "hello"
    assert args.output_format == "stream-json"
    assert args.remote is False
    assert args.command is None


def test_help_lists_delivery_and_existing_options() -> None:
    help_text = cli.build_parser().format_help()
    for option in ("--version", "--mode", "-p", "--output-format", "--remote", "doctor"):
        assert option in help_text


def test_doctor_parser_supports_offline() -> None:
    args = cli.build_parser().parse_args(["doctor", "--offline"])
    assert args.command == "doctor"
    assert args.offline is True


def test_teammate_flags_still_bypass_standard_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = AsyncMock()
    monkeypatch.setattr(cli, "_run_teammate", worker)

    exit_code = cli.run_cli(["--teammate", "--team-name", "demo", "--agent-name", "worker"])

    assert exit_code == 0
    worker.assert_awaited_once_with("demo", "worker")


def test_run_cli_prints_doctor_report_and_returns_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = DoctorReport(
        (DiagnosticResult("config", CheckStatus.FAIL, "broken", critical=True),)
    )
    doctor = AsyncMock(return_value=report)
    monkeypatch.setattr(cli, "run_doctor", doctor)

    exit_code = cli.run_cli(["doctor", "--offline"])

    assert exit_code == 1
    assert "[FAIL] config: broken" in capsys.readouterr().out
    doctor.assert_awaited_once_with(online=False)


def test_config_error_is_actionable_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fail_config():
        raise cli.ConfigError("missing configuration")

    monkeypatch.setattr(cli, "load_config", fail_config)

    exit_code = cli.run_cli([])
    stderr = capsys.readouterr().err

    assert exit_code == 1
    assert "missing configuration" in stderr
    assert "codeshell doctor --offline" in stderr
    assert "Traceback" not in stderr


def test_prompt_authentication_error_is_actionable_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = AppConfig(
        providers=[ProviderConfig("demo", "openai", "https://example.test", "model")]
    )
    monkeypatch.setattr(cli, "load_config", lambda: config)
    monkeypatch.setattr(cli, "load_hooks", lambda _raw: [])

    async def fail_prompt(*_args, **_kwargs):
        raise AuthenticationError("API key not found")

    monkeypatch.setattr(cli, "_run_prompt", fail_prompt)

    exit_code = cli.run_cli(["-p", "hello"])
    stderr = capsys.readouterr().err

    assert exit_code == 1
    assert "API key not found" in stderr
    assert "codeshell doctor --offline" in stderr
    assert "Traceback" not in stderr


def test_banner_uses_shared_version() -> None:
    from codeshell.app import CodeShellApp

    banner = CodeShellApp._make_banner(model="demo", work_dir="/workspace")
    assert f"CodeShell v{codeshell.__version__}" in banner.plain


@pytest.mark.asyncio
async def test_status_uses_shared_version() -> None:
    from codeshell.commands.handlers.status import handle_status

    class UI:
        message = ""

        def add_system_message(self, text: str) -> None:
            self.message = text

        def get_token_count(self) -> tuple[int, int]:
            return 0, 0

    ui = UI()
    context = SimpleNamespace(
        agent=None,
        session=None,
        memory_manager=None,
        ui=ui,
    )

    await handle_status(context)

    assert f"版本: v{codeshell.__version__}" in ui.message
