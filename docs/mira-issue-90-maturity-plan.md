# Mira Issue 90 Maturity Plan

Issue #90 is implemented as a lightweight contract layer, not a heavy rewrite.

## Easy to hard rollout

1. Agent role profiles: named subagent behavior for implementer, reviewer, researcher, and doctor.
2. Tool middleware: before/after/error execution hooks for policy and observability.
3. Multimodal contract: stable media parts for text, image, audio, and files.
4. Virtual context manager: deterministic paging of older turns into compact breadcrumbs.
5. Workflow DSL: optional JSON workflow validation and expansion.
6. Computer Use: optional trusted host mount point, disabled by default and root-gated.

## Product boundary

Mira keeps the kernel small. These features are exposed as modules/contracts so
desktop and server builds can enable only what they need.

## Default posture

The default Mira Studio profile enables the cheap maturity layer:

- virtual context
- agent roles
- tool middleware
- multimodal contract

The risky or heavier mounts stay disabled until explicitly enabled:

- workflow DSL
- computer use
