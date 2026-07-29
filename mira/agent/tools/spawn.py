"""Spawn tool for creating background subagents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mira.agent.tools.base import Tool, ToolResult, tool_parameters
from mira.agent.tools.context import current_request_context
from mira.agent.tools.schema import (
    ArraySchema,
    BooleanSchema,
    IntegerSchema,
    NumberSchema,
    ObjectSchema,
    StringSchema,
    tool_parameters_schema,
)
from mira.security.workspace_access import current_workspace_scope

if TYPE_CHECKING:
    from mira.agent.subagent import SubagentManager


@tool_parameters(
    tool_parameters_schema(
        task=StringSchema("The task for the subagent to complete"),
        tasks=ArraySchema(
            ObjectSchema(
                task=StringSchema("The task for the subagent to complete"),
                label=StringSchema("Optional short label for the task (for display)", nullable=True),
                weight=IntegerSchema(
                    description=(
                        "Optional scheduling weight for queued subagents. Higher values are "
                        "chosen sooner when execution slots free up."
                    ),
                    minimum=1,
                    maximum=8,
                ),
                required=["task"],
            ),
            description=(
                "Optional lightweight batch of subagent tasks. Use this to fan out a few "
                "independent subtasks in parallel. Keep tasks narrow and bounded."
            ),
            min_items=1,
            max_items=8,
            nullable=True,
        ),
        label=StringSchema("Optional short label for the task (for display)"),
        weight=IntegerSchema(
            description=(
                "Optional scheduling weight for queued subagents. Higher values are "
                "chosen sooner when execution slots free up."
            ),
            minimum=1,
            maximum=8,
        ),
        temperature=NumberSchema(
            description=(
                "Optional sampling temperature for the subagent "
                "(0.0 = deterministic, higher = more creative). "
                "Defaults to the provider's configured temperature."
            ),
            minimum=0.0,
            maximum=2.0,
        ),
        wait=BooleanSchema(
            description=(
                "Wait for the subagent and return its result directly. Use this for a "
                "blocking consultation that must inform the current turn. Defaults to "
                "false for background execution."
            ),
            default=False,
        ),
        required=[],
    )
)
class SpawnTool(Tool):
    """Tool to spawn a subagent for background task execution."""

    def __init__(self, manager: "SubagentManager"):
        self._manager = manager

    @classmethod
    def create(cls, ctx: Any) -> Tool:
        return cls(manager=ctx.subagent_manager)

    @property
    def name(self) -> str:
        return "spawn"

    @property
    def description(self) -> str:
        return (
            "Spawn a subagent to handle a task in the background. "
            "Use this for complex or time-consuming tasks that can run independently. "
            "You can also pass a small `tasks` array to fan out several independent "
            "lightweight subtasks in one call. "
            "Set wait=true for a consultation whose result must inform the current turn. "
            "The subagent will complete the task and report back when done. "
            "For deliverables or existing projects, inspect the workspace first "
            "and use a dedicated subdirectory when helpful."
        )

    async def execute(
        self,
        task: str | None = None,
        tasks: list[dict[str, Any]] | None = None,
        label: str | None = None,
        weight: int = 1,
        temperature: float | None = None,
        wait: bool = False,
        **kwargs: Any,
    ) -> str:
        """Spawn a subagent to execute the given task."""
        request_ctx = current_request_context()
        if request_ctx is None or request_ctx.runtime is None:
            return ToolResult.error("Error: spawn requires an active model runtime")
        requested_tasks: list[tuple[str, str | None, int]] = []
        if task:
            requested_tasks.append((task, label, max(1, weight)))
        for item in tasks or ():
            if not isinstance(item, dict):
                continue
            item_task = str(item.get("task") or "").strip()
            if not item_task:
                continue
            item_label = item.get("label")
            item_weight = item.get("weight")
            parsed_weight = int(item_weight) if isinstance(item_weight, int) and not isinstance(item_weight, bool) else 1
            requested_tasks.append((item_task, str(item_label) if item_label is not None else None, max(1, parsed_weight)))
        if not requested_tasks:
            return ToolResult.error("Error: spawn requires `task` or at least one entry in `tasks`.")

        running = self._manager.get_running_count()
        limit = self._manager.max_concurrent_subagents
        origin_channel = request_ctx.channel
        origin_chat_id = request_ctx.chat_id
        session_key = request_ctx.session_key or f"{origin_channel}:{origin_chat_id}"
        method = self._manager.run_inline if wait else self._manager.spawn
        if wait or len(requested_tasks) == 1:
            chosen_task, chosen_label, chosen_weight = requested_tasks[0]
            return await method(
                task=chosen_task,
                runtime=request_ctx.runtime,
                label=chosen_label,
                weight=chosen_weight,
                origin_channel=origin_channel,
                origin_chat_id=origin_chat_id,
                session_key=session_key,
                origin_message_id=request_ctx.message_id,
                temperature=temperature,
                workspace_scope=current_workspace_scope(),
            )

        results: list[str] = []
        for item_task, item_label, item_weight in requested_tasks:
            results.append(await self._manager.spawn(
                task=item_task,
                runtime=request_ctx.runtime,
                label=item_label,
                weight=item_weight,
                origin_channel=origin_channel,
                origin_chat_id=origin_chat_id,
                session_key=session_key,
                origin_message_id=request_ctx.message_id,
                temperature=temperature,
                workspace_scope=current_workspace_scope(),
            ))
        queued = sum("queued" in line.lower() for line in results)
        started = len(results) - queued
        summary = [f"Started {started} subagent(s); queued {queued} subagent(s) with lightweight parallelism."]
        summary.extend(f"- {line}" for line in results)
        if running >= limit:
            summary.append(
                f"- Host/session concurrency is currently saturated at {running}/{limit}; new tasks entered the shared queue."
            )
        return "\n".join(summary)
