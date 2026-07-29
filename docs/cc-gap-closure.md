# Mira vs Claude Code Gap Closure

This document tracks the fastest path from "agent kernel" to a more mature
Claude Code-like product experience.

## Closed or materially improved

### Desktop startup must not silently flash and crash

- Issue: #93
- Current closure: native `mira-launcher` writes startup diagnostics before
  handing off to Python.
- Operator path: run `mira-launcher --dry-run` or inspect
  `~/Library/Logs/Mira/launcher.log`.
- Remaining product polish: desktop shell should render the last launcher error
  directly in the GUI.

### Release automation and package-size gates

- Issue: #98
- Current closure: release workflow now builds Rust native boundary tools and
  audits DMG/EXE/Linux artifacts through `mira-pack`.
- Default limit: `180 MB`, override with `MIRA_RELEASE_SIZE_LIMIT_MB`.
- Failure behavior: missing package exits `2`; over-limit package exits `3`.

### Tool failure recovery

- Issue: #97
- Current closure: tool failures include reliability, fallback, and failure
  posture in the runner/registry path.
- Operator rule: retry narrower inputs for recoverable failures, switch tools
  for degraded paths, and stop on fail-closed tools.

### Automatic context and memory recall maturity

- Issue: #94
- Current closure: virtual context manager provides deterministic old-turn
  breadcrumbs; group memory and principal policy are explicit in runtime
  surfaces.
- Current explainability: `VirtualContextManager.explain(...)` reports strategy,
  budget, kept messages, paged messages, and whether a breadcrumb was injected.
- Remaining product polish: automatic recall scoring and WebUI explanation of
  why a specific memory was injected.

### WebUI execution visibility

- Issue: #96
- Current closure: session status dots, runtime/admin surfaces, and issue #90
  module contracts exist. Backend diagnostics are exposed through
  `/api/kernel/diagnostics` so the GUI can show launcher logs and recovery
  actions. Session rows now expose a `Diagnose` action hook that can be handled
  by the active shell or by the `mira:request-diagnostics` browser event.
- Remaining product polish: failed turns should render a full one-click
  doctor/log panel and retry/fork actions from the same session row.

### Signed and notarized release installers

- Issue: #95
- Current closure: workflow has macOS notarization and Windows signing gates for
  tag releases when secrets are configured.
- Required macOS secrets:
  - `MACOS_CERTIFICATE_P12`
  - `MACOS_CERTIFICATE_PASSWORD`
  - `MACOS_CODESIGN_IDENTITY`
  - `APPLE_ID`
  - `APPLE_TEAM_ID`
  - `APPLE_APP_SPECIFIC_PASSWORD`
- Required Windows secrets:
  - `WINDOWS_CERTIFICATE_PFX`
  - `WINDOWS_CERTIFICATE_PASSWORD`
- Remaining product polish: publish only signed trusted artifacts as public
  release assets; mark unsigned dev builds clearly.

## Current maturity verdict

Mira is now structurally closer to a mature agent workbench: the kernel is
modular, users/groups/policies exist, native diagnostic boundaries exist, and
release packaging has a measurable gate.

The largest remaining gap versus Claude Code is product polish, not core agent
capability: first-run error UI, visible recovery actions, automatic memory
explanations, and consistently trusted installers.
