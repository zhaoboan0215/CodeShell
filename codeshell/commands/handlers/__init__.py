
from __future__ import annotations

from codeshell.commands.handlers.clear import CLEAR_COMMAND
from codeshell.commands.handlers.compact import COMPACT_COMMAND
from codeshell.commands.handlers.help import HELP_COMMAND
from codeshell.commands.handlers.mcp import MCP_COMMAND
from codeshell.commands.handlers.memory import MEMORY_COMMAND
from codeshell.commands.handlers.model import MODEL_COMMAND
from codeshell.commands.handlers.plan import PLAN_COMMAND
from codeshell.commands.handlers.sandbox import SANDBOX_COMMAND
from codeshell.commands.handlers.session import SESSION_COMMAND
from codeshell.commands.handlers.skill import SKILL_COMMAND
from codeshell.commands.handlers.rewind import REWIND_COMMAND
from codeshell.commands.handlers.status import STATUS_COMMAND
from codeshell.commands.registry import CommandRegistry


ALL_COMMANDS = [
    HELP_COMMAND,
    COMPACT_COMMAND,
    CLEAR_COMMAND,
    PLAN_COMMAND,
    SESSION_COMMAND,
    MCP_COMMAND,
    MEMORY_COMMAND,
    MODEL_COMMAND,
    SANDBOX_COMMAND,
    REWIND_COMMAND,
    STATUS_COMMAND,
    SKILL_COMMAND,
]


def register_all_commands(registry: CommandRegistry) -> None:
    for cmd in ALL_COMMANDS:
        registry.register_sync(cmd)

