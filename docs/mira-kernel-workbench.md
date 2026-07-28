# Mira Kernel Workbench

This document describes the current Mira-facing execution kernel surface that now sits on top of the original nanobot runtime.

## Purpose

Mira is no longer just a conversation-first agent shell. The current target is a compact execution kernel with:

- a thin engineering GUI;
- a shell-style operator console;
- explicit runtime, module, workspace, and orchestration controls;
- enough structure to evolve toward desktop, server, and embedded control targets.

## Current status

As of July 28, 2026, the local source tree is already Mira-first in product shape:

- the primary runtime/workbench identity is Mira
- the operator shell behaves like a compact kernel console
- runtime, queue, lane, worker, bridge, board, and fault state are exposed through one engineering surface
- Python remains the live orchestration layer while Rust and C-adjacent targets stay represented through adapters and bridges

What is still outside code-only completion:

- build/runtime verification has not yet been run for the current migration pass
- deeper Otto-pattern migration and validation still need explicit implementation and verification work
- compatibility-bound surfaces such as `nanobot`, `~/.mira/`, `mira/...`, and `mira.wiki` remain intentionally retained for now

## Current workbench shape

The current Mira workbench is built around a kernel boundary and an operator-facing control plane.

Core layers:

- `KernelApp` as the stable runtime facade
- `MiraKernelConsole` as the engineering shell/workbench surface
- runtime adapters and bridges for Python, Rust, and C-adjacent execution targets
- embedded board attachment and bridge probing hooks
- orchestration projections across diagnostics, queues, lanes, workers, and timeline views

## Operator shell

The operator shell now acts like a small kernel console rather than a chat input.

It supports:

- runtime inspection
- adapter and bridge inspection
- module focus and module action routing
- board attach/detach and runtime probe status
- fault and maintenance controls
- session, goal, and continuation inspection
- workspace and repo inspection
- tool dispatch orchestration

Representative command groups:

- `runtime health`
- `runtime orchestration`
- `session goal`
- `session continuation`
- `workspace status`
- `repo tools`
- `tool status`
- `tool dispatch <name>`
- `tool delegate-goal`
- `tool delegate-subagent`
- `tool complete`
- `tool fail`

## Execution orchestration

The current kernel workbench includes a compact orchestration model inspired by an operating-system control surface.

Implemented concepts:

- tool dispatch queue
- dispatch priority
- goal-lane handoff
- subagent-lane handoff
- queue drain
- queue clear
- runtime orchestration summary
- task lifecycle projection

Current lifecycle states:

- `queued`
- `prioritized`
- `delegated_goal`
- `delegated_subagent`
- `completed`
- `failed`
- `drained`

## Visibility model

The same orchestration state is now visible across multiple views so operators do not have to infer state from a single panel.

Current visibility surfaces:

- runtime orchestration summary command
- operator shell command output
- task-kernel runtime panel
- diagnostics snapshot
- execution timeline
- scheduler queues
- execution lanes
- worker/task summaries

This means a tool dispatch can be observed from creation to handoff and terminal state without leaving the engineering workbench.

In practice, the current orchestration chain is:

1. `tool dispatch`
2. dispatch queue
3. priority or handoff decision
4. lane projection
5. worker/task projection
6. terminal lifecycle state

## Runtime targets

Mira is being shaped as a general execution layer rather than a single chat application.

Current target posture:

- desktop operator console
- server/runtime orchestration
- embedded-lab / firmware-control direction

Current implementation-language posture:

- Python for the live runtime shell and orchestration layer
- Rust as a preferred systems/runtime target
- C for low-level bridge and embedded-control direction

The current codebase already contains runtime adapter and runtime bridge scaffolding aligned with that direction.

## Workspace and repo posture

The kernel workbench now treats workspace and repo as first-class execution objects instead of passive metadata.

Current workspace/repo operations include:

- workspace status
- workspace scope
- workspace module projection
- repo root/status projection
- repo tool contract projection

This gives the workbench a clearer engineering posture similar to Codex-style project execution rather than a generic chat session.

## Delivery status

As of July 28, 2026, the Mira workbench already has:

- a Mira-branded kernel/runtime surface
- a Codex-style engineering panel direction
- a shell-like operator console
- multi-layer execution observability
- a compact orchestration model for dispatch, handoff, and lifecycle tracking

Remaining work is mostly in three categories:

- final verification and delivery checks
- residual outward-facing compatibility cleanup
- deeper orchestration migration from Otto-style execution patterns

For the release-prep checklist that matches the current implementation, see
[Mira Delivery Readiness](./mira-delivery-readiness.md).
