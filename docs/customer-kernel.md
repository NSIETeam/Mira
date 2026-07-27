# Customer Kernel Target

This repository started from upstream nanobot, but the customer-delivery target
is narrower than the upstream product surface.

## Target

Build a kernel that is:

- mature enough to ship;
- light enough to customize quickly;
- explicit enough that client-specific features do not leak across projects.

## Kernel principle

The kernel should own:

- session state;
- model/tool execution;
- approvals;
- file and shell operations;
- normalized event streaming;
- optional memory.

The GUI should only own:

- input and output;
- activity rendering;
- approval UI;
- diagnostics display.

## Profile model

Customer delivery should not start from "all features on". It should start from
a profile.

Current kernel profiles live in `nanobot/kernel/profile.py`:

- `lite_customer_profile()`
- `desktop_customer_profile()`
- `automation_customer_profile()`

These are capability bundles, not separate runtimes. They exist so packaging,
surface area, and client scope can be decided explicitly.

## Recommended default

For most client work, use `lite_customer_profile()` first:

- channels: `webui`, `cli`
- tools: `filesystem`, `shell`, `apply_patch`, `search`
- features: `session_state`, `approvals`, `event_stream`
- no background automations by default

That gives a kernel that is still useful, but much easier to control,
understand, and customize than the full upstream surface.

## Delivery blocker right now

As of `2026-07-27`, publishing is blocked by external GitHub state:

- local checkout only has `upstream = HKUDS/nanobot`
- GitHub CLI reports the `NSIETeam` token is invalid
- the target repository name/url has not yet been identified in this checkout

Once the target repo URL is provided and GitHub auth is restored, this local
kernel-first baseline can be pushed directly.
