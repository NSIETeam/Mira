# Kernel Host Contract

This document defines the boundary between the Mira execution kernel, the WebUI host, and shell-specific GUI layouts.

## Goal

The execution kernel must remain reusable across different GUI shells.

- The kernel owns execution semantics, session lifecycle, event transport, tool orchestration, and runtime capabilities.
- The host owns route/state orchestration for the active GUI surface.
- The shell owns layout, posture, and presentation of host-provided surfaces.

This separation keeps the backend stable while allowing multiple shells to be swapped in with minimal frontend change.

## Layer Model

### 1. Kernel layer

Primary backend files:

- `mira/kernel/app.py`
- `mira/kernel/profile.py`
- `mira/kernel/shell.py`
- `mira/webui/settings_api.py`
- `mira/webui/ws_http.py`

Kernel responsibilities:

- resolve active profile and shell
- expose kernel manifest and shell descriptor
- expose runtime capabilities and execution contract
- stay shell-agnostic

The kernel must not depend on a specific WebUI layout.

### 2. Host orchestration layer

Primary frontend files:

- `webui/src/App.tsx`
- `webui/src/shells/host.ts`
- `webui/src/shells/useShellUtilityState.ts`
- `webui/src/shells/useExecutionWorkspaceState.ts`
- `webui/src/shells/useExecutionRuntimeState.ts`
- `webui/src/shells/useExecutionSessionState.ts`
- `webui/src/shells/useShellPresentationState.ts`
- `webui/src/shells/engineering/useEngineeringChromeState.ts`
- `webui/src/shells/engineering/useEngineeringOverlayState.ts`
- `webui/src/shells/engineering/useEngineeringSidebarState.ts`

Host responsibilities:

- bootstrap auth and runtime connection
- translate kernel manifest into host state
- manage route/session/runtime/workspace orchestration
- mount the selected shell layout
- provide shell-facing surfaces as composed React nodes

The host should consume the shell contract, not invent shell-specific behavior ad hoc.

### 3. Shell layout layer

Primary frontend files:

- `webui/src/shells/EngineeringShellLayout.tsx`
- `webui/src/shells/SingleExecutionShellLayout.tsx`
- `webui/src/shells/ReviewShellLayout.tsx`
- `webui/src/shells/registry.ts`
- `webui/src/shells/types.ts`

Shell responsibilities:

- choose layout posture
- arrange host-provided surfaces
- expose shell metadata through DOM attributes if useful
- avoid owning execution semantics

Shells should be thin.

## Shell Descriptor Contract

Backend source of truth:

- `mira/kernel/shell.py`

Frontend payload/type surface:

- `webui/src/lib/types.ts`
- `webui/src/shells/types.ts`
- `webui/src/shells/registry.ts`

The shell descriptor must remain declarative.

Stable fields:

- `name`
- `display_name`
- `description`
- `theme`
- `supports_threads`
- `supports_file_activity`
- `supports_approvals`
- `supports_runtime_controls`
- `host_contract`
- `metadata`

## Host Contract Shape

`host_contract` is the main kernel-to-host GUI contract.

### Required top-level semantics

- `mode`

Current modes:

- `engineering`
- `single-execution`
- `review`

### Grouped capabilities

Preferred grouped capabilities:

- `chrome`
- `surfaces`
- `actions`
- `composer`

#### `chrome`

Controls shell chrome visibility.

- `showSidebarChrome`
- `showSearchDialog`

#### `surfaces`

Controls which host surfaces may appear.

- `allowUtilitySurface`
- `allowWorkspaceControls`
- `allowRuntimeModelControls`

#### `actions`

Controls execution-level actions.

- `allowExecutionFork`

#### `composer`

Controls composer posture.

- `allowComposer`
- `readOnlyExecution`

### Compatibility rule

The current implementation still tolerates legacy flat booleans in `host_contract`, but grouped capabilities are the preferred contract going forward.

New shells should emit grouped capabilities first.

## Registration Rules

Frontend registration logic lives in:

- `webui/src/shells/registry.ts`

Rules:

- shell layout selection should prefer `host_contract.mode`
- legacy shell names may be mapped for compatibility
- registry output should normalize the final contract before host consumption

This allows the backend to evolve descriptor naming without breaking layout resolution.

## Shell Authoring Rules

When adding a new shell:

1. Add a backend shell descriptor factory in `mira/kernel/shell.py`.
2. Give it a stable `mode`.
3. Emit grouped `host_contract` capabilities.
4. Add or map a frontend layout in `webui/src/shells/registry.ts`.
5. Keep the shell component presentation-only.
6. Put orchestration in host hooks, not in the shell component.

## Non-Goals

The shell contract should not directly describe:

- tool schemas
- provider-specific transport details
- low-level websocket protocol behavior
- internal agent loop state machines

Those belong to the kernel/runtime layer, not the shell layer.

## Design Direction

The intended long-term shape is:

- backend execution kernel is generic and mature
- host layer is reusable and engineering-focused
- shells are thin branded or posture-specific wrappers

That is the basis for turning Mira from a compact single-surface agent into a reusable execution platform.
