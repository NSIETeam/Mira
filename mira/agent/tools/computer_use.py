"""Optional Computer Use mount point.

This tool is deliberately disabled by default. It defines the contract without
loading any desktop-control dependency into the lightweight kernel.
"""

from __future__ import annotations

from typing import Any

from mira.agent.tools.base import Tool, ToolResult, tool_parameters
from mira.agent.tools.context import current_request_context
from mira.agent.tools.schema import EnumSchema, StringSchema, tool_parameters_schema


@tool_parameters(
    tool_parameters_schema(
        action=EnumSchema(
            ["status", "request"],
            description="Check availability or request a trusted host-side Computer Use action.",
        ),
        instruction=StringSchema(
            "Operator-visible instruction for the trusted host adapter.",
            nullable=True,
        ),
        required=["action"],
    )
)
class ComputerUseTool(Tool):
    _scopes = {"core"}

    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        modules = getattr(getattr(ctx, "config", None), "modules", None)
        return bool(modules and modules.is_enabled("computer_use", default=False))

    @property
    def name(self) -> str:
        return "computer_use"

    @property
    def description(self) -> str:
        return (
            "Optional trusted desktop-control mount point. Disabled by default; "
            "only root/full-access local sessions should enable it."
        )

    async def execute(self, action: str, instruction: str | None = None) -> str:
        ctx = current_request_context()
        policy = getattr(ctx, "policy", None) if ctx is not None else None
        if getattr(policy, "role", "guest") != "root":
            return ToolResult.error("Error: computer_use requires root policy.")
        if action == "status":
            return "computer_use contract is mounted; no host adapter is attached in this build."
        return ToolResult.error(
            "Error: computer_use host adapter is not attached. "
            f"Requested instruction: {(instruction or '').strip()[:300]}"
        )
