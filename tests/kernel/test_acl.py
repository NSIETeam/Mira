from mira.kernel.acl import CapabilityPolicy, CapabilityRequest, CapabilityRule


def test_capability_policy_allows_whitelisted_path() -> None:
    policy = CapabilityPolicy(
        agent="reviewer-1",
        rules=(CapabilityRule("/fs/read", allow=("/repo/*",), deny=("/repo/private/*",)),),
    )

    result = policy.evaluate(
        CapabilityRequest(agent="reviewer-1", capability="/fs/read", target="/repo/README.md")
    )

    assert result.allowed is True
    assert policy.audit_log == []


def test_capability_policy_denies_and_audits() -> None:
    policy = CapabilityPolicy(
        agent="reviewer-1",
        rules=(CapabilityRule("/shell/exec", deny=("*",)),),
    )

    result = policy.evaluate(
        CapabilityRequest(agent="reviewer-1", capability="/shell/exec", target="rm -rf /")
    )

    assert result.decision == "deny"
    assert policy.audit_log[-1].capability == "/shell/exec"
    assert policy.audit_log[-1].target == "rm -rf /"


def test_capability_policy_requires_approval() -> None:
    policy = CapabilityPolicy(
        agent="writer-1",
        rules=(CapabilityRule("/fs/write", allow=("/tmp/mira-*",), require_approval=True),),
    )

    result = policy.evaluate(
        CapabilityRequest(agent="writer-1", capability="/fs/write", target="/tmp/mira-out")
    )

    assert result.decision == "approval_required"
    assert policy.audit_log[-1].decision == "approval_required"


def test_child_policy_cannot_gain_parent_capabilities() -> None:
    parent = CapabilityPolicy(
        agent="parent",
        rules=(
            CapabilityRule("/fs/read", allow=("/repo/*",)),
            CapabilityRule("/web/search", allow=("*",)),
        ),
    )

    child = parent.derive_child(
        agent="child",
        requested_caps=frozenset({"/fs/read", "/shell/exec"}),
    )

    assert child.evaluate(
        CapabilityRequest(agent="child", capability="/fs/read", target="/repo/a.py")
    ).allowed
    assert child.evaluate(
        CapabilityRequest(agent="child", capability="/shell/exec", target="pwd")
    ).decision == "deny"
