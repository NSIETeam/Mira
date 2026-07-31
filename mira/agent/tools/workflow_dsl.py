"""Optional declarative workflow DSL tool."""

from __future__ import annotations

import json
from typing import Any

from mira.agent.maturity import parse_workflow_dsl
from mira.agent.tools.base import Tool, ToolResult, tool_parameters
from mira.agent.tools.schema import StringSchema, tool_parameters_schema


@tool_parameters(
    tool_parameters_schema(
        workflow=StringSchema(
            "Workflow JSON with a `steps` array. Each step has id, task, optional role, and optional depends_on.",
        ),
        required=["workflow"],
    )
)
class WorkflowDslTool(Tool):
    config_key = "workflow_dsl"
    _scopes = {"core"}
    _core_default = False

    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        modules = getattr(ctx, "modules", None)
        if modules is None:
            modules = getattr(getattr(ctx, "config", None), "modules", None)
        return bool(modules and modules.is_enabled("workflow_dsl", default=False))

    @property
    def name(self) -> str:
        return "workflow_dsl"

    @property
    def description(self) -> str:
        return (
            "Validate and expand a small declarative workflow into ordered subagent-ready steps. "
            "This is intentionally not a heavy visual workflow engine."
        )

    async def execute(self, workflow: str) -> str:
        try:
            steps = parse_workflow_dsl(workflow)
        except ValueError as exc:
            return ToolResult.error(f"Error: invalid workflow DSL: {exc}")
        return json.dumps(
            {
                "status": "ok",
                "steps": [step.to_dict() for step in steps],
                "execution": "manual_or_subagent_dispatch",
            },
            ensure_ascii=False,
            indent=2,
        )
