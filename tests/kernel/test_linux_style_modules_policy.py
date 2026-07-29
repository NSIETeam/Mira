from __future__ import annotations

from mira.agent.loop import AgentLoop
from mira.bus.queue import MessageBus
from mira.config.schema import Config, ModuleConfig, ModulesConfig
from mira.kernel.module_registry import module_summary
from mira.kernel.profile import get_profile
from mira.security.policy import effective_principal_policy
from tests.agent.conftest import make_provider


def test_module_summary_accepts_configured_overrides():
    config = Config.model_validate({
        "modules": {
            "registry": {
                "subagents": {"enabled": False},
            }
        }
    })

    summary = module_summary(get_profile(config.kernel.profile_name), config.modules)
    subagents = next(row for row in summary["modules"] if row["name"] == "subagents")

    assert subagents["status"] == "disabled"
    assert "estimated_memory_cost_mb" in summary


def test_temporary_user_policy_denies_dangerous_tools_by_default():
    policy = effective_principal_policy(user_id="alice", group_id="growth")

    assert policy.role == "guest"
    assert not policy.allows_tool("exec")
    assert policy.allows_tool("read_file")
    assert policy.memory_scope == "group"


def test_config_policy_can_extend_deny_table():
    config = Config.model_validate({
        "security": {
            "policies": {
                "group:growth": {
                    "role": "service",
                    "denyTools": ["spawn"],
                    "execPosture": "disabled",
                }
            }
        }
    })

    policy = effective_principal_policy(config.security, user_id="bot", group_id="growth")

    assert policy.role == "service"
    assert not policy.allows_tool("spawn")
    assert policy.exec_posture == "disabled"


def test_agent_loop_unregisters_disabled_tool_modules(tmp_path):
    loop = AgentLoop(
        bus=MessageBus(),
        provider=make_provider(spec=False),
        workspace=tmp_path,
        modules_config=ModulesConfig(registry={"exec": ModuleConfig(enabled=False)}),
    )

    assert "exec" not in loop.tools.tool_names
