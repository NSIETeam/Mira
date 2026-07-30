# Execution Layer Direction

mira is being refactored into a reusable execution layer with a thin, replaceable workbench shell.

## Target split

### Execution layer

Owns:

- execution state and lifecycle
- model, tool, and approval orchestration
- runtime policy and workspace scope
- normalized kernel events
- memory, goals, and durable execution history

### Workbench shell

Owns:

- presentation and navigation
- branding and product framing
- shell-specific controls and diagnostics
- optional thread, task, or single-run affordances

The shell should stay cheap to replace. The execution layer should stay stable enough to carry multiple shells.

## Public surface

The kernel package now exposes two explicit concepts:

- `ExecutionKernel` / `KernelApp`: reusable runtime surface, available from `mira.kernel.app`
- runtime contracts also surface directly from `mira.kernel.runtime_adapter`, `mira.kernel.runtime_bridge`, `mira.kernel.runtime_control`, and `mira.kernel.module_registry`
- execution/worker contracts surface through `mira.kernel.app` (inlined helpers; previously `mira.kernel.execution_plane`, `mira.kernel.scheduler`, `mira.kernel.worker_plane`)
- embedded board contracts surface through `mira.kernel.app`
- topology aggregation surfaces through `mira.kernel.app`
- `ShellDescriptor`: shell metadata and capability contract
- `ExecutionSnapshot` / `KernelEvent`: stable state and event contracts for shells

The kernel manifest is versioned. Shells should treat it as a contract, not an
incidental payload.

The shell can now consume a single `runtime_topology` object instead of
manually re-assembling adapters, bridges, workers, queues, and lanes.

For finer-grained host integrations, the gateway now also exposes dedicated
kernel snapshots:

- `/api/kernel/topology`
- `/api/kernel/embedded`
- `/api/kernel/scheduler`
- `/api/kernel/workers`
- `/api/kernel/diagnostics`
- `/api/kernel/lanes`

This lets a Codex-style shell poll only the subsystem it needs instead of
re-fetching the entire manifest every time.

That split matters because product forks should not need to mutate core agent internals just to change navigation or UI posture.

## Engineering workbench default

The default shell is an engineering workbench:

- execution-oriented
- approval-aware
- runtime-controls aware
- file-activity aware
- thread-capable, but not thread-bound

This keeps the shipped GUI useful for serious engineering work without baking a single product identity into the kernel.

## Shell capability contract

Shell metadata is a runtime contract, not decoration.

Current capability switches:

- `supports_threads`
- `supports_runtime_controls`
- `supports_file_activity`

Expected behavior:

- `supports_threads=false`
  - hide sidebar-driven execution history management
  - hide fork and conversation-navigation affordances
  - present a single execution workbench instead of a thread manager
- `supports_runtime_controls=false`
  - hide model badges, preset switching, and workspace runtime controls
  - keep the main surface focused on execution, not environment tuning
- `supports_file_activity=false`
  - hide file-edit activity clusters
  - disable file preview side panels and related entry points

This is the key to cheap shell replacement: products can reshape the surface without forking the execution loop.

## Shell registry

The execution layer now owns a shell registry instead of assuming one hard-coded
surface.

Current shell helpers:

- `default_engineering_shell()`
- `single_execution_shell()`
- `review_shell()`
- `register_shell(name, factory)`
- `get_shell(name)`
- `list_shells()`

`build_kernel_manifest()` publishes `shell_registry` so a workbench or desktop
host can expose shell selection without importing kernel internals directly.

Server-side default shell selection now comes from `config.kernel.shell_name`.
Frontend local selection may still override that default for the current user.

## Contract versioning

`build_kernel_manifest()` now publishes:

- `contracts.manifest_version`
- `contracts.event_version`
- `contracts.snapshot_version`

It also declares the execution contract shape:

- `execution.supports_streaming`
- `execution.supports_snapshots`
- `execution.supports_background`
- `execution.supports_resumption`
- `execution.event_types`
- `execution.event_actions`
- `execution.event_states`
- `execution.snapshot_statuses`
- `execution.lifecycle_states`

That gives shells a stable way to reason about compatibility as the execution
layer evolves.

## Frontend naming rule

The frontend should prefer neutral execution/workbench language unless thread semantics are strictly required by the user experience or by protocol compatibility.

That means:

- top-level UI state should talk about executions, not chats
- reusable shell components should export execution-first names
- thread/chat/session names may remain only as compatibility aliases or protocol shims

## Current direction

The current refactor is intentionally pushing the WebUI toward this split:

- execution-first hooks and client APIs
- workbench-first shell and sidebar surfaces
- kernel-event consumption instead of transport-event coupling
- shell capability switches that suppress product-specific affordances cleanly
- a stable kernel manifest via `KernelApp.describe()` for shell bootstrapping
- a stable one-shot execution result via `KernelApp.execute() -> ExecutionSnapshot`
- semantic `KernelEvent` subtyping (`action/state`) so GUI code can follow
  common streaming flows without binding directly to raw transport event names
- aligned Python/WebUI event contracts so `KernelEvent` carries the same
  `type/action/state` semantics across the execution layer boundary
- lifecycle-aware execution snapshots so the contract can explicitly grow into
  background, approval-gated, resumable, and long-running execution flows
- session-runtime projection helpers such as
  `merge_snapshot_with_session_metadata(...)` so existing goal/continuation
  signals can enrich the stable snapshot contract without exposing internal
  session structures to shells

`KernelApp` now exposes that projection path directly:

- `KernelApp.snapshot_from_result(result, session_metadata=...)`
- `KernelApp.enrich_snapshot(snapshot, session_metadata=...)`

That keeps snapshot enrichment inside the kernel surface instead of forcing
shells to compose low-level helpers themselves.

## Remaining work

1. Finish reducing protocol-era `chat/session` naming that still exists only for compatibility.
2. Keep moving any remaining WebUI consumers to kernel events instead of raw transport assumptions.
3. Keep shell code presentation-focused and prevent provider/channel logic from leaking upward.
4. Add more shell descriptors over time instead of branching kernel logic per product.
