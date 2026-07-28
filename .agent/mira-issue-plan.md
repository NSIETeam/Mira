# Mira issue plan

Date: 2026-07-28
Repository target: `NSIETeam/easygrowth-nanobot-kernel`
Current local codename: `Mira`

## Issue 1

Title: `kernel: remove remaining projection wrappers and keep diagnostics state-first`

Body:

```md
## Goal

Finish shrinking the Python kernel app layer so diagnostics are emitted directly from runtime state instead of passing through one-off projection helpers.

## Scope

- Continue removing low-value formatting/projection helpers in `mira/kernel/app.py`
- Keep runtime/native/fault/session/board/bridge outputs produced close to the source state
- Avoid reintroducing flat compatibility fields or duplicate output builders

## Done when

- Remaining one-shot projection helpers are either removed or justified
- `KernelApp` acts mainly as coordinator/dispatcher
- Diagnostics payload shape remains stable for WebUI consumers

## Notes

- Do not widen behavior scope
- Prefer deletion and inlining over new abstraction
```

## Issue 2

Title: `shell-contract: finish grouped host contract migration`

Body:

```md
## Goal

Complete the migration to grouped shell host contract semantics across backend and WebUI.

## Scope

- Standardize on:
  - `chrome`
  - `surfaces`
  - `actions`
  - `composer`
  - `privilege`
- Remove remaining historical naming bridges where safe
- Keep compatibility coercion minimal and explicit

## Done when

- Backend shell descriptors emit grouped contract only
- Frontend registry/contract/types consume grouped contract directly
- No new flat host contract fields are introduced

## Notes

- Preserve current shell modes: `engineering`, `single-execution`, `review`
- Keep root/user privilege contract explicit
```

## Issue 3

Title: `operator-console: eliminate positional action bindings`

Body:

```md
## Goal

Finish converting the engineering console from positional action-array access to stable action-id lookups.

## Scope

- Continue replacing `actions[n]` reads in `webui/src/shells/MiraKernelConsole.tsx`
- Keep event-first routing logic only where the event model is intentionally ordered
- Prefer local `find(action.id)` helpers for console sections

## Done when

- Native, bridge, fault, dispatch, topology, module, and runtime control sections use stable action ids
- Remaining positional reads are limited to intentional dynamic/event-order semantics
- UI action bindings no longer depend on backend action ordering

## Notes

- This is a shell hardening task, not a redesign
- Keep current operator UX and labels unless duplication is being removed
```

## Issue 4

Title: `native-bridge: continue rust-first kernel boundary extraction`

Body:

```md
## Goal

Keep moving command/event/module snapshot responsibilities into the native bridge so the Python layer stays thin.

## Scope

- Expand Rust bridge ownership of:
  - recent commands
  - last command
  - module state snapshots
  - native event history
- Keep Python-side bridge code focused on orchestration and normalization only

## Done when

- Native bridge contract is the primary source of native diagnostics metadata
- Python no longer duplicates action projection logic that belongs at the bridge boundary
- The bridge remains suitable for future embedded/board-oriented runtimes

## Notes

- Favor Rust over Python for new native-state machinery
- Preserve current snapshot payload compatibility where possible
```

## Issue 5

Title: `runtime-control: formalize root-user operator boundaries`

Body:

```md
## Goal

Make root/user privilege behavior explicit across runtime control, dispatch control, and fault control.

## Scope

- Ensure privileged actions consistently declare:
  - `required_role`
  - `privileged`
  - `privileged_reason`
- Keep WebUI rendering aligned with privilege contract
- Reduce scattered privilege special cases

## Done when

- Root-only actions are consistently described by contract metadata
- User-visible restriction messages come from contract data instead of local guesswork
- The engineering shell exposes a stable operator model similar to a kernel control plane

## Notes

- Do not widen permission surface during cleanup
- Prefer contract normalization over UI-only fixes
```

## Issue 6

Title: `cleanup: remove obsolete Mira compatibility leftovers`

Body:

```md
## Goal

Run a focused dead-code and compatibility-leftover sweep after the contract and console migrations.

## Scope

- Remove obsolete helper functions
- Remove duplicated action presentation paths
- Remove stale compatibility shims replaced by grouped contract or native bridge outputs

## Done when

- Obsolete wrappers and dead paths are removed
- No duplicate native/operator action rendering remains in the main engineering shell
- The repository is smaller and structurally cleaner without changing product direction

## Notes

- Prioritize deletion over refactor layering
- Keep the codebase small and mechanically obvious
```
