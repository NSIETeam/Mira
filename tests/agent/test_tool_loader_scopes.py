import pytest

from mira.agent.tools.base import Tool
from mira.agent.tools.context import ToolContext
from mira.agent.tools.loader import ToolLoader
from mira.config.schema import ModuleConfig, ModulesConfig


class _CoreOnlyTool(Tool):
    _scopes = {"core"}

    @property
    def name(self):
        return "core_only"

    @property
    def description(self):
        return "..."

    @property
    def parameters(self):
        return {"type": "object"}

    async def execute(self, **_):
        return "ok"


class _SubagentOnlyTool(Tool):
    _scopes = {"subagent"}

    @property
    def name(self):
        return "sub_only"

    @property
    def description(self):
        return "..."

    @property
    def parameters(self):
        return {"type": "object"}

    async def execute(self, **_):
        return "ok"


class _UniversalTool(Tool):
    _scopes = {"core", "subagent", "memory"}

    @property
    def name(self):
        return "universal"

    @property
    def description(self):
        return "..."

    @property
    def parameters(self):
        return {"type": "object"}

    async def execute(self, **_):
        return "ok"


class _OptionalCoreTool(Tool):
    config_key = "optional_core"
    _scopes = {"core"}
    _core_default = False

    @property
    def name(self):
        return "optional_core"

    @property
    def description(self):
        return "..."

    @property
    def parameters(self):
        return {"type": "object"}

    async def execute(self, **_):
        return "ok"


@pytest.mark.asyncio
async def test_loader_filters_by_scope():
    from mira.agent.tools.registry import ToolRegistry

    loader = ToolLoader(test_classes=[_CoreOnlyTool, _SubagentOnlyTool, _UniversalTool])

    registry = ToolRegistry()
    ctx = ToolContext(config={}, workspace="/tmp")
    loader.load(ctx, registry, scope="core")

    assert registry.has("core_only")
    assert not registry.has("sub_only")
    assert registry.has("universal")


def test_loader_skips_optional_core_tools_until_explicitly_enabled():
    from mira.agent.tools.registry import ToolRegistry

    loader = ToolLoader(test_classes=[_CoreOnlyTool, _OptionalCoreTool])

    default_registry = ToolRegistry()
    loader.load(ToolContext(config={}, workspace="/tmp", modules=ModulesConfig()), default_registry)

    assert default_registry.has("core_only")
    assert not default_registry.has("optional_core")

    enabled_registry = ToolRegistry()
    loader.load(
        ToolContext(
            config={},
            workspace="/tmp",
            modules=ModulesConfig(registry={"optional_core": ModuleConfig(enabled=True)}),
        ),
        enabled_registry,
    )

    assert enabled_registry.has("core_only")
    assert enabled_registry.has("optional_core")
