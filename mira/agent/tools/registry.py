"""Tool registry for dynamic tool management."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from mira.agent.tools.base import Tool, ToolResult
from mira.agent.tools.context import ContextAware, current_request_context
from mira.security.policy import EffectivePrincipalPolicy
from mira.tool_contracts import tool_contract_family

if TYPE_CHECKING:
    from mira.runtime_context import RuntimeContextProvider


def is_tool_error_result(name: str, result: Any) -> bool:
    return isinstance(result, ToolResult) and result.is_error


class ToolRegistry:
    """
    Registry for agent tools.

    Allows dynamic registration and execution of tools.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._cached_definitions: list[dict[str, Any]] | None = None

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
        self._cached_definitions = None

    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        self._tools.pop(name, None)
        self._cached_definitions = None

    def filtered_copy(self, *, exclude: set[str]) -> ToolRegistry:
        """Return a registry view excluding selected tools."""
        registry = ToolRegistry()
        for name, tool in self._tools.items():
            if name not in exclude:
                registry.register(tool)
        return registry

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_runtime_context_providers(self) -> list[RuntimeContextProvider]:
        """Return tool-owned providers in stable tool-name order."""
        providers: list[RuntimeContextProvider] = []
        for name in sorted(self._tools):
            provider = self._tools[name].runtime_context_provider()
            if provider is not None:
                providers.append(provider)
        return providers

    @staticmethod
    def _lookup_key(name: str) -> str:
        """Normalize names for suggestions only; never for execution."""
        return "".join(ch.lower() for ch in name if ch.isalnum())

    def _suggest_name(self, name: str) -> str | None:
        key = self._lookup_key(str(name or ""))
        if not key:
            return None
        matches = [
            registered
            for registered in self._tools
            if self._lookup_key(registered) == key
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    @staticmethod
    def _schema_name(schema: dict[str, Any]) -> str:
        """Extract a normalized tool name from either OpenAI or flat schemas."""
        fn = schema.get("function")
        if isinstance(fn, dict):
            name = fn.get("name")
            if isinstance(name, str):
                return name
        name = schema.get("name")
        return name if isinstance(name, str) else ""

    @classmethod
    def _schema_family(cls, schema: dict[str, Any]) -> str:
        """Classify tool schemas into stable operator-facing families."""
        return tool_contract_family(cls._schema_name(schema).replace("_", "-"))

    def get_definitions(self) -> list[dict[str, Any]]:
        """Get tool definitions with stable ordering for cache-friendly prompts.

        Built-in tools are sorted first as a stable prefix, then MCP tools are
        sorted and appended.  The result is cached until the next
        register/unregister call.
        """
        if self._cached_definitions is not None:
            return self._cached_definitions

        definitions = [tool.to_schema() for tool in self._tools.values()]
        builtins: list[dict[str, Any]] = []
        mcp_tools: list[dict[str, Any]] = []
        for schema in definitions:
            name = self._schema_name(schema)
            schema["x_mira_family"] = self._schema_family(schema)
            if name.startswith("mcp_"):
                mcp_tools.append(schema)
            else:
                builtins.append(schema)

        builtins.sort(key=lambda schema: (self._schema_family(schema), self._schema_name(schema)))
        mcp_tools.sort(key=lambda schema: (self._schema_family(schema), self._schema_name(schema)))
        self._cached_definitions = builtins + mcp_tools
        return self._cached_definitions

    def prepare_call(
        self,
        name: str,
        params: Any,
    ) -> tuple[Tool | None, Any, str | None]:
        """Resolve, cast, and validate one tool call."""
        ctx = current_request_context()
        policy = getattr(ctx, "policy", None) if ctx is not None else None
        if isinstance(policy, EffectivePrincipalPolicy) and not policy.allows_tool(name):
            return None, params, ToolResult.error(
                f"Error: Tool '{name}' is denied by policy for "
                f"user '{policy.user_id}' group '{policy.group_id}'."
            )
        tool = self._tools.get(name)
        if not tool:
            suggestion = self._suggest_name(str(name))
            hint = f" Did you mean '{suggestion}'? Tool names must match exactly." if suggestion else ""
            return None, params, (
                ToolResult.error(
                    f"Error: Tool '{name}' not found.{hint} Available: {', '.join(self.tool_names)}"
                )
            )

        # Compatibility for external tools that still implement the legacy
        # setter protocol. Built-ins read the authoritative ContextVar
        # directly and never copy routing state.
        if isinstance(tool, ContextAware) and ctx is not None:
            tool.set_context(ctx)

        params = self._coerce_params(tool, params)
        if not isinstance(params, dict):
            return tool, params, (
                ToolResult.error(
                    f"Error: Tool '{name}' parameters must be a JSON object, got "
                    f"{type(params).__name__}. Use named parameters like "
                    'tool_name(param1="value1", param2="value2") matching the tool schema.'
                )
            )

        cast_params = tool.cast_params(params)
        errors = tool.validate_params(cast_params)
        if errors:
            return tool, cast_params, (
                ToolResult.error(f"Error: Invalid parameters for tool '{name}': " + "; ".join(errors))
            )
        return tool, cast_params, None

    @classmethod
    def _coerce_argument_value(cls, value: Any) -> Any:
        if value is None:
            return {}
        if not isinstance(value, str):
            return value

        stripped = value.strip()
        if not stripped:
            return {}

        if not stripped.startswith(("{", "[")):
            return value

        try:
            parsed = json.loads(stripped)
        except Exception:
            return value

        return parsed

    @classmethod
    def _coerce_params(cls, tool: Tool, params: Any) -> Any:
        params = cls._coerce_argument_value(params)
        return cls._unwrap_arguments_payload(tool, params)

    @classmethod
    def _unwrap_arguments_payload(cls, tool: Tool, params: Any) -> Any:
        if not isinstance(params, dict) or set(params) != {"arguments"}:
            return params
        properties = (tool.parameters or {}).get("properties", {})
        if isinstance(properties, dict) and "arguments" in properties:
            return params
        return cls._coerce_argument_value(params.get("arguments"))

    async def execute(self, name: str, params: Any) -> Any:
        """Execute a tool by name with given parameters."""
        hint = "\n\n[Analyze the error above and try a different approach.]"
        tool, params, error = self.prepare_call(name, params)
        if error:
            return ToolResult.error(str(error) + hint)

        try:
            assert tool is not None  # guarded by prepare_call()
            result = await tool.execute(**params)
            if is_tool_error_result(name, result):
                return ToolResult.error(self._format_tool_failure(tool, str(result)) + hint)
            return result
        except Exception as e:
            return ToolResult.error(
                self._format_tool_failure(tool, f"Error executing {name}: {e!s}") + hint
            )

    @staticmethod
    def _format_tool_failure(tool: Tool, message: str) -> str:
        reliability = getattr(tool, "reliability_tier", "variable")
        fallback_policy = getattr(tool, "fallback_policy", "retry_or_fail")
        failure_mode = getattr(tool, "failure_mode", "recoverable")
        policy_text = (
            f"Tool runtime: reliability={reliability}, fallback={fallback_policy}, failure={failure_mode}."
        )
        if fallback_policy == "retry_or_fail":
            action_text = "Retry with narrower inputs or switch tools if the same failure repeats."
        elif fallback_policy == "degrade_or_fail":
            action_text = "A degraded path may be acceptable; explain the downgrade before continuing."
        elif fallback_policy == "fail_closed":
            action_text = "Do not silently bypass this failure; stop or ask for a safer path."
        else:
            action_text = "Choose the next step explicitly instead of assuming silent recovery."
        return f"{message}\n\n{policy_text} {action_text}"

    @property
    def tool_names(self) -> list[str]:
        """Get list of registered tool names."""
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
