from __future__ import annotations

import shutil
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from codeshell.config import (
    ConfigError,
    MCPServerConfig,
    ProviderConfig,
    load_config_with_discovery,
)


class CheckStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class DiagnosticResult:
    name: str
    status: CheckStatus
    detail: str
    remediation: str = ""
    critical: bool = False


@dataclass(frozen=True)
class DoctorReport:
    results: tuple[DiagnosticResult, ...]

    @property
    def exit_code(self) -> int:
        return int(any(r.status == CheckStatus.FAIL and r.critical for r in self.results))

    def render(self) -> str:
        lines = ["CodeShell Doctor", "──────────────"]
        for result in self.results:
            lines.append(f"[{result.status.value}] {result.name}: {result.detail}")
            if result.remediation:
                lines.append(f"       Fix: {result.remediation}")

        counts = {
            status: sum(r.status == status for r in self.results)
            for status in CheckStatus
        }
        warning_label = "warning" if counts[CheckStatus.WARN] == 1 else "warnings"
        lines.append("──────────────")
        lines.append(
            "Summary: "
            f"{counts[CheckStatus.PASS]} passed, "
            f"{counts[CheckStatus.WARN]} {warning_label}, "
            f"{counts[CheckStatus.FAIL]} failed"
        )
        return "\n".join(lines)


ProviderProbe = Callable[[ProviderConfig], Awaitable[DiagnosticResult]]
CommandLookup = Callable[[str], str | None]


def check_python(version_info: tuple[int, ...] | None = None) -> DiagnosticResult:
    version = tuple(sys.version_info[:3]) if version_info is None else version_info
    version_text = ".".join(str(part) for part in version[:3])
    if version[:2] >= (3, 11):
        return DiagnosticResult("Python", CheckStatus.PASS, f"{version_text} (requires >=3.11)")
    return DiagnosticResult(
        "Python",
        CheckStatus.FAIL,
        f"{version_text} is unsupported",
        "Install Python 3.11 or newer and recreate the environment.",
        critical=True,
    )


def check_project_files(cwd: Path) -> list[DiagnosticResult]:
    results: list[DiagnosticResult] = []
    for filename in ("pyproject.toml", "uv.lock"):
        path = cwd / filename
        if path.is_file():
            results.append(DiagnosticResult(filename, CheckStatus.PASS, "found"))
        else:
            results.append(
                DiagnosticResult(
                    filename,
                    CheckStatus.FAIL,
                    "missing from the current directory",
                    f"Run this command from the CodeShell repository root containing {filename}.",
                    critical=True,
                )
            )
    return results


def check_mcp_dependencies(
    servers: list[MCPServerConfig],
    command_lookup: CommandLookup = shutil.which,
) -> list[DiagnosticResult]:
    if not servers:
        return [DiagnosticResult("MCP", CheckStatus.PASS, "no MCP servers configured")]

    results: list[DiagnosticResult] = []
    for server in servers:
        if not server.is_stdio:
            results.append(
                DiagnosticResult(f"MCP {server.name}", CheckStatus.PASS, "HTTP transport configured")
            )
            continue

        command = server.command or ""
        commands = ("node", "npx") if command == "npx" else (command,)
        for executable in commands:
            found = command_lookup(executable)
            if found:
                results.append(
                    DiagnosticResult(
                        f"MCP {server.name} / {executable}",
                        CheckStatus.PASS,
                        f"found at {found}",
                    )
                )
            else:
                results.append(
                    DiagnosticResult(
                        f"MCP {server.name} / {executable}",
                        CheckStatus.WARN,
                        "command not found",
                        f"Install {executable} or remove the {server.name} MCP configuration.",
                    )
                )
    return results


def _safe_provider_failure(provider: ProviderConfig, error: BaseException) -> DiagnosticResult:
    error_name = type(error).__name__.lower()
    if "authentication" in error_name or "permission" in error_name:
        detail = "authentication failed"
        remediation = "Check the configured API key and its permissions."
    elif "connection" in error_name or "timeout" in error_name:
        detail = "network connection failed"
        remediation = "Check the base URL, network connection, proxy, and firewall."
    elif "notfound" in error_name or "not_found" in error_name:
        detail = f"model '{provider.model}' was not found"
        remediation = "Choose a model available from this provider."
    else:
        detail = f"provider returned {type(error).__name__}"
        remediation = "Check provider availability and run doctor again."
    return DiagnosticResult(
        f"Provider {provider.name}",
        CheckStatus.FAIL,
        detail,
        remediation,
        critical=True,
    )


async def probe_provider(provider: ProviderConfig) -> DiagnosticResult:
    """Use model metadata endpoints only; this never sends a chat prompt."""

    api_key = provider.resolve_api_key()
    try:
        if provider.protocol == "anthropic":
            kwargs = {"api_key": api_key}
            if provider.base_url:
                kwargs["base_url"] = provider.base_url
            async with AsyncAnthropic(**kwargs) as client:
                await client.models.retrieve(provider.model)
        else:
            kwargs = {"api_key": api_key}
            if provider.base_url:
                kwargs["base_url"] = provider.base_url
            async with AsyncOpenAI(**kwargs) as client:
                model_page = await client.models.list()
            # OpenAI-compatible SDKs return a page object whose records live in
            # ``data``.  Some test doubles and older implementations return an
            # iterable directly, so retain that shape as a compatibility path.
            models = getattr(model_page, "data", model_page)
            model_ids = {model.id for model in models}
            if provider.model not in model_ids:
                return DiagnosticResult(
                    f"Provider {provider.name}",
                    CheckStatus.FAIL,
                    f"model '{provider.model}' is not listed",
                    "Choose a model returned by the provider's model list endpoint.",
                    critical=True,
                )
    except Exception as error:
        return _safe_provider_failure(provider, error)

    return DiagnosticResult(
        f"Provider {provider.name}",
        CheckStatus.PASS,
        f"reachable; model '{provider.model}' is available",
    )


async def run_doctor(
    *,
    cwd: Path | None = None,
    home: Path | None = None,
    online: bool = True,
    provider_probe: ProviderProbe | None = None,
    command_lookup: CommandLookup = shutil.which,
) -> DoctorReport:
    project_dir = Path.cwd() if cwd is None else Path(cwd)
    user_home = Path.home() if home is None else Path(home)
    results: list[DiagnosticResult] = [check_python()]
    results.extend(check_project_files(project_dir))

    try:
        config, discovery = load_config_with_discovery(cwd=project_dir, home=user_home)
    except ConfigError as error:
        results.append(
            DiagnosticResult(
                "Configuration",
                CheckStatus.FAIL,
                str(error),
                "Fix the configuration and run doctor again.",
                critical=True,
            )
        )
        return DoctorReport(tuple(results))

    source_kind = "repository example" if discovery.using_example else "user/project config"
    source_list = ", ".join(str(path) for path in discovery.paths)
    results.append(
        DiagnosticResult("Configuration", CheckStatus.PASS, f"{source_kind}: {source_list}")
    )

    probe = probe_provider if provider_probe is None else provider_probe
    for provider in config.providers:
        if not provider.resolve_api_key():
            results.append(
                DiagnosticResult(
                    f"API key / {provider.name}",
                    CheckStatus.FAIL,
                    "not configured",
                    "Set ANTHROPIC_API_KEY for anthropic, or OPENAI_API_KEY for openai protocols.",
                    critical=True,
                )
            )
            continue

        results.append(
            DiagnosticResult(
                f"API key / {provider.name}",
                CheckStatus.PASS,
                "configured",
            )
        )
        if not online:
            results.append(
                DiagnosticResult(
                    f"Provider {provider.name}",
                    CheckStatus.WARN,
                    "network check skipped in offline mode",
                )
            )
            continue
        try:
            results.append(await probe(provider))
        except Exception as error:
            results.append(_safe_provider_failure(provider, error))

    results.extend(check_mcp_dependencies(config.mcp_servers, command_lookup))
    return DoctorReport(tuple(results))
