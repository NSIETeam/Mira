# Mira Delivery Readiness

This checklist is for packaging the current repository as a Mira-branded execution kernel workbench rather than the original nanobot-first surface.

Date baseline: July 27, 2026.

For the implementation-oriented overview of the current engineering surface, see
[Mira Kernel Workbench](./mira-kernel-workbench.md).

## What is already in place

The current codebase already includes the following Mira-facing delivery surfaces.

### Kernel and runtime surface

- `KernelApp` as the stable execution-kernel facade
- Mira runtime profiles for desktop/studio and embedded-lab direction
- runtime adapter and bridge projection for Python, Rust, and C-adjacent targets
- embedded board attachment, transport, and probe-oriented control state

### Engineering workbench

- `MiraKernelConsole` as the shell-style operator workbench
- Codex-style runtime/task-kernel panel direction
- pane routing for control-plane, runtime, workspace, faults, modules, and adapters
- quick-command operator workflow across runtime, modules, board, bridge, faults, and tools

### Orchestration layer

- tool dispatch queue
- queue priority controls
- queue drain controls
- goal-lane handoff
- subagent-lane handoff
- queue lifecycle projection
- queue terminal states for complete and fail

### Visibility and observability

- operator shell output cards
- execution timeline
- task-kernel runtime panel
- diagnostics snapshot
- scheduler queue projection
- execution lane projection
- worker/task projection
- runtime orchestration summary command

### Branding migration already done

- Mira runtime naming in key entrypoints
- Mira-oriented README positioning
- Mira-oriented WebUI core English strings
- Mira-oriented docs entry pages
- dedicated Mira kernel workbench document

## Explicitly retained compatibility layers

These remain intentionally retained and should not be mistaken for incomplete migration by themselves:

- published package name `mira`
- config and workspace home under `~/.mira/`
- legacy `nanobot` launcher
- internal Python package path `mira/...`
- namespace-forwarding compatibility shims under `mira/`

## Compatibility boundary matrix

This is the practical line between "intentional compatibility" and "still-visible Mira delivery debt".

| Surface | Current state | Keep for now | Delivery expectation |
| --- | --- | --- | --- |
| Runtime entrypoint | `mira` primary, `nanobot` legacy | Yes | New usage should default to `mira` |
| Published package | `mira` | Yes | Accept until package migration is planned separately |
| Config home | `~/.mira/` | Yes | Accept as compatibility storage root |
| Internal Python modules | `mira/...` | Yes | Internal-only until a deeper package migration is justified |
| Forwarding namespace | `mira/...` shims | Yes | Keep as the public-facing migration bridge |
| WebUI visible shell/workbench copy | Mostly Mira-first | No | Should read as Mira to an operator |
| WebUI visible storage keys | Mixed, partly Mira-first | No | New front-facing keys should prefer `mira.*` when safe |
| README positioning | Mira-first with compatibility notes | No | Should present Mira as the default product identity |
| Release-critical docs landing pages | Mira-first | No | Should not feel nanobot-first to a new user |
| Repo metadata and remote URLs | Mostly Mira-aligned in local source, still requires hosted verification | No | Must be aligned and checked manually at release time |

### Treat as compatibility, not a blocker by itself

- package/install naming that still depends on `mira`
- filesystem/config roots under `~/.mira/`
- internal imports and code organization under `mira/...`
- legacy launcher support for existing operators

### Treat as remaining product-facing cleanup

- user-visible WebUI copy that still says `nanobot`
- old front-end storage keys where migration risk is acceptable
- release-facing README phrasing that still centers nanobot instead of Mira
- repository naming, remote metadata, and public-facing URLs

## What still requires explicit verification

These items are not proven by code edits alone and still require explicit delivery-time verification.

### Build and runtime checks

- Python package install still resolves correctly
- WebUI build still succeeds
- Mira entrypoint still launches correctly
- operator shell commands still round-trip through the WebUI transport
- diagnostics payload remains consumable by the current frontend types

### Branding checks

- no broken asset references in WebUI branding surfaces
- no unacceptable outward-facing `mira` strings remain in release-critical surfaces
- repo metadata and remote URLs are aligned with the intended Mira repository
- package metadata points to `NSIETeam/Mira` rather than the upstream mira repository

## Repository rename execution

Code edits alone do not complete the repository rename. The repository/platform layer still needs an explicit release operator pass.

Required platform steps:

1. rename the GitHub repository to `Mira`
2. confirm the default branch, release pages, and badges now resolve under `NSIETeam/Mira`
3. update any remaining repository description, social preview, homepage, and topic metadata to match Mira
4. confirm local remotes point at `NSIETeam/Mira` instead of the upstream mira repository
5. only after that treat the repository-name migration as complete

Until those steps are performed, "Mira" is true for the local product surface but not yet fully true for the hosted repository identity.

### Workflow checks

- tool dispatch queue commands behave coherently in the running app
- lane/worker/task projections stay synchronized during real shell interaction
- embedded bridge/runtime scaffolding does not regress desktop runtime behavior

## Release recommendation

Before calling the migration done, the next operator should perform these steps in order:

1. build or typecheck the touched Python and WebUI surfaces
2. open the Mira WebUI and exercise the kernel console manually
3. verify the shell commands for runtime, session, workspace, and tool orchestration
4. confirm repo metadata, public URLs, and the `NSIETeam/Mira` repository naming
5. only then commit and push

## Practical completion standard

The migration should be considered truly complete only when all three are true:

1. the Mira engineering workbench is the primary visible runtime surface
2. the orchestration chain is observable from shell to queue to worker to lane
3. the remaining `mira` surfaces are compatibility-bound rather than accidental product-facing leftovers
