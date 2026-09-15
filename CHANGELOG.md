# Changelog

All notable changes to CodeShell are documented in this file.

## Unreleased

### Added

- Repository-safe `config.example.yaml` with a no-secret DeepSeek default.
- `codeshell doctor` and `codeshell doctor --offline` environment diagnostics.
- Read-only checks for Python, repository files, configuration, API Key presence, Provider model availability, and MCP command dependencies.
- Complete README with quick start, architecture, configuration, security, testing, and troubleshooting guidance.
- A real, redacted Textual TUI screenshot.
- Python 3.11–3.13 delivery smoke workflow and a transparent full-regression job.
- Per-improvement documentation archive containing the approved specification, plan, tasks, checklist, and final change report.

### Changed

- Configuration discovery now reports its source and falls back to the repository example only when no user or project configuration exists.
- CLI routing is testable and handles startup configuration and authentication errors without an internal traceback.
- CLI, TUI Banner, and `/status` now share package version `0.2.0`.
- The documented one-command startup uses a locked, non-editable installation to avoid editable `.pth` import failures on affected macOS/Python 3.13 environments.

### Fixed

- Installed CLI startup no longer depends on the current working directory being added through an editable `.pth` file.
- Missing or invalid configuration errors now include configuration locations, required fields, and a Doctor command.
- Provider diagnostics correctly read model records from OpenAI-compatible SDK page responses.

### Known issues

- The pre-existing `pre_tool_use` Hook integration test for rejecting `rm -rf /` remains failing. Its implementation was explicitly excluded from this improvement and is not filtered from the full regression job.
