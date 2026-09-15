from __future__ import annotations

from codeshell.commands.registry import Command, CommandContext, CommandType
from codeshell.model_switching import SUPPORTED_DEEPSEEK_MODELS


MODEL_USAGE = "/model [deepseek-flash|deepseek-v4-pro]"


async def handle_model(ctx: CommandContext) -> None:
    parts = ctx.args.split()
    if not parts:
        ctx.ui.show_model_selector(
            ctx.ui.get_available_models(),
            ctx.ui.get_current_model(),
        )
        return

    if len(parts) != 1:
        ctx.ui.add_system_message(f"用法: {MODEL_USAGE}")
        return

    await ctx.ui.switch_model(parts[0])


MODEL_COMMAND = Command(
    name="model",
    description=(
        "切换当前运行使用的 DeepSeek 模型；"
        f"可选: {', '.join(SUPPORTED_DEEPSEEK_MODELS)}"
    ),
    usage=MODEL_USAGE,
    type=CommandType.LOCAL_UI,
    handler=handle_model,
)
