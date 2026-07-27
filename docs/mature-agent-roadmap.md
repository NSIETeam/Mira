# Mature Agent Roadmap

This repo already has real capability breadth, but it has moved past the
original "tiny readable core" constraint. The right next step is not another
feature wave. It is a boundary cleanup.

## Target Shape

Mira should evolve toward:

- a small, explicit `kernel`;
- a thin GUI that consumes kernel events;
- tools behind one stable contract;
- approvals and runtime policy owned by the kernel;
- session and memory state clearly separated from presentation concerns.

## What changed in this first cut

The first code change introduces `mira/kernel/` as the stable product
boundary:

- `KernelApp` wraps the existing runtime without rewriting it;
- `KernelEvent` gives GUI code a compact event model;
- `normalize_stream_event(...)` converts richer SDK stream events into that compact model.

The WebUI baseline is also starting to adopt the same language:

- runtime host types now expose `KernelHost` / `KernelRuntimeInfo`;
- GUI-facing shared types include `KernelEventPayload`;
- existing `RuntimeHost` naming remains as a compatibility alias during migration.

This preserves current behavior while making later simplification possible.

## Refactor order

1. Move GUI code to depend only on `mira.kernel`.
2. Collapse overlapping runtime entry surfaces behind `KernelApp`.
3. Reduce tool/UI coupling by keeping GUI on normalized events only.
4. Audit approvals, file edits, and shell execution as kernel-owned policy.
5. Only then shrink internal module count or fold duplicated orchestration.

## Non-goals

These do not help code size or maturity right now:

- adding multi-agent orchestration frameworks;
- adding more channels before boundary cleanup;
- exposing GUI code directly to provider- or tool-specific event details;
- creating parallel runtime stacks for CLI, WebUI, and SDK.

## Standard for future changes

Any new product surface should answer three questions:

1. Is this kernel logic or GUI logic?
2. Does it fit through the stable kernel boundary?
3. Does it reduce or increase coupling to internal orchestration details?

If the answer to (2) is no, the change is probably expanding accidental
complexity.
