# Mira Project Experience

This document records the practical engineering lessons from turning the original lightweight Nano BOT-style codebase into Mira: a smaller, more mature agent runtime with a desktop/WebUI product surface, Linux-style multi-user posture, policy controls, memory volumes, release packaging, and operational diagnostics.

## 1. Product Direction

Mira should stay a lightweight execution kernel, not become a heavy all-in-one application.

The winning direction is:

- Keep the Python agent loop and provider ecosystem.
- Put maturity around the loop: session control, policy, memory, modules, runtime health, release flow, and GUI visibility.
- Use Rust/C only at high-value process boundaries: launcher, sandbox, package audit.
- Make the GUI an operator surface over the kernel, not a second agent implementation.

## 2. Architecture Lessons

### Keep the kernel small

The default startup path should only load the essentials:

- config
- bus
- session
- provider
- scheduler
- auth
- minimal chat/WebUI bootstrap

Everything else should be lazy or module-gated:

- MCP
- heavy document tooling
- channels
- image generation
- memory consolidation
- doctor repair
- desktop host

### Treat UI shells as hosts

The agent loop should not know about desktop, browser, customer shells, or Claude Code-style interaction details. Shell behavior belongs in shell descriptors, frontend host contracts, and runtime/admin surfaces.

### Do not rewrite the agent loop in Rust

The agent loop depends on Python ecosystem velocity: providers, tools, MCP, memory, WebUI integration, tests. Rewriting it would burn time and increase risk. Native code should guard startup, sandboxing, and package size only.

## 3. Linux-style User Model

The right model is not just `--user` as a label. It should behave like a lightweight namespace model:

- `user` isolates sessions and workspace.
- `group` shares project memory and skills.
- `policy` decides tool access, workspace root, memory scope, and execution posture.
- `guest` and `service` default to restricted behavior.
- default/local user keeps compatibility.

Implemented behavior:

- WebUI bootstrap accepts user/group and returns effective policy.
- Temporary users get isolated session/workspace paths.
- Same group shares group memory volume.
- Runtime/Admin shows principal, namespace, policy, modules, and memory volume.
- Stale temporary users can be audited and cleaned by admin/root posture.

## 4. Policy Enforcement Lessons

Filtering tool definitions is necessary but not sufficient.

Mature policy enforcement needs three gates:

- The model should not see denied tools.
- Direct tool execution must fail closed.
- Subagent/cron/local-trigger paths must not bypass the current policy.

Implemented behavior:

- `AgentLoop` filters tools based on effective user/group policy.
- `RequestContext` carries the effective policy.
- `ToolRegistry.prepare_call()` refuses denied tools even if called directly.
- Subagents inherit the parent request policy.

Remaining risk:

- Shell execution is still app-layer restricted in v1.
- Strong untrusted-code isolation should later use Docker, bubblewrap, or system UID isolation.

## 5. Memory System Lessons

Project teams need shared memory, but not one global shared history.

The practical model is:

- user memory: private session/workspace context
- group memory: shared project volume
- global memory: default/local compatibility
- policy declares memory scope
- Runtime/Admin shows memory volume status

Implemented behavior:

- Group memory volume has path, size, topic count, quota, and breach status.
- Bootstrap and kernel memory API expose volume metadata.
- Runtime/Admin shows group memory audit state.

Future improvement:

- Add compact/archive action per group volume.
- Enforce hard quotas before writes.
- Add project-level memory ownership and retention policy.

## 6. GUI/Product Lessons

The fastest path to a credible agent product is not to add more tools first. It is to make execution visible and controllable.

Important UI decisions:

- Sidebar sessions should behave like execution records.
- Each session row needs visible status: running, processed, needs intervention.
- The three-dot action menu should always be reachable.
- Runtime/Admin must show effective user, group, policy, memory, modules, and execution posture.
- Guest/service users should see why controls are unavailable.

Implemented behavior:

- Execution list uses red/yellow/green status dots.
- Right-side action menu is always visible enough to discover.
- Runtime/Admin has read-only policy posture and module toggles for allowed principals.

## 7. Packaging and Release Lessons

A mature desktop agent is judged by whether it installs, opens, and updates reliably.

Key lessons:

- DMG/EXE generation alone is not enough.
- macOS needs signing and notarization to avoid harmful-app warnings.
- First-run smoke tests must run the packaged app, not just build it.
- Package size must be budgeted, not guessed.
- The release workflow should publish checksums.

Implemented behavior:

- GitHub Actions release flow builds macOS DMG, Windows EXE, and Linux tarball.
- Smoke tests run packaged apps.
- Package size audit script reports largest contributors.
- Release workflow enforces a 119 MB package budget.
- SHA256 metadata is generated for release artifacts.

Remaining release work:

- Configure Apple signing and notarization secrets.
- Configure Windows signing secrets.
- Fix first-run crash if it still reproduces in packaged desktop builds.
- Complete stable public release artifacts.

## 8. Size Discipline

Mira must stay smaller than Otto if it is positioned as a lightweight kernel.

Rules:

- Avoid bundling dev dependencies.
- Avoid eager loading heavy document/image/channel modules.
- Treat WebUI assets as visible package budget.
- Use package reports before arguing about size.
- Do not rewrite in Rust just for size unless packaging audit proves Python is the dominant cost.

Current package budget:

- Target: 119 MB or less.
- Tool: `python scripts/package_size_report.py <package-path> --budget-mb 119`.

## 9. Doctor and Operational Health

Doctor should not just repair local setup. It should explain operational readiness.

Useful checks:

- startup health
- package size
- port availability
- config validity
- workspace policy
- memory volume status
- release signing/notarization posture
- first-run crash hints

Future improvement:

- Add `mira doctor --profile lightweight` as the main operator path.
- Add release-specific doctor profile for packaged apps.

## 10. GitHub Issue Workflow Lessons

For this project, issues should be concrete and small enough to execute quickly.

Good issue shape:

- Goal
- Scope
- Acceptance
- Explicit out-of-scope notes

Avoid:

- abstract maturity labels
- large rewrite requests without boundary
- mixing Rust/toolchain work with Python/WebUI work
- closing issues based only on partial implementation

Current remaining issue categories:

- Rust optional boundary tools
- macOS/Windows signing
- first-run desktop stability
- settings-view/fetch mock test debt

## 11. Validation Lessons

Fast validation should be targeted first:

- Python policy tests for kernel/security changes.
- WebUI component tests for changed UI paths.
- Production WebUI build for TypeScript and bundling.
- Release workflow only when packaging changes affect artifacts.

Useful commands:

```bash
uv run --no-sync python -m ruff check mira/ tests/
uv run --no-sync python -m pytest -q tests/kernel/test_linux_style_modules_policy.py tests/webui/test_temporary_users.py
cd webui && npm test -- chat-list.test.tsx --run
cd webui && npm run build
python scripts/package_size_report.py dist/Mira.app --budget-mb 119
```

## 12. Practical Roadmap

The fastest route to final version is:

1. Stabilize desktop first-run behavior.
2. Configure signing/notarization secrets.
3. Publish clean DMG/EXE release artifacts.
4. Finish settings-view fetch mocks and full WebUI test stability.
5. Implement Rust launcher/sandbox/pack as optional boundary tools.
6. Add hard sandbox backend for untrusted shell execution.
7. Add group memory compaction/archive actions.

## 13. Product Judgment

Mira is no longer just a small bot demo. It is now a credible lightweight agent kernel with a usable operator UI, multi-user posture, shared project memory, policy control, module registry, release workflow, and package discipline.

It is not yet fully final because signed installers and first-run desktop stability still decide whether non-technical users can trust and open it without warnings.
