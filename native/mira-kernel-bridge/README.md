# Mira Kernel Bridge

This crate is the native-side bridge for Mira's execution kernel.

Purpose:
- provide a tiny C ABI for pushing execution events from Rust, C, or firmware adapters
- expose queue depth, recent command/event history, and per-module state to higher-level shells
- stay small enough to embed beside MCU-facing runtimes later

Current surface:
- `mira_kernel_publish_event`
- `mira_kernel_poll_event`
- `mira_kernel_set_module_state`
- `mira_kernel_read_module_state_at`
- `mira_kernel_queue_depth`
- `mira_kernel_recent_event_count`
- `mira_kernel_read_recent_event_at`
- `mira_kernel_module_count`
- `mira_kernel_submit_command`
- `mira_kernel_poll_command`
- `mira_kernel_read_last_command`
- `mira_kernel_recent_command_count`
- `mira_kernel_read_recent_command_at`
- `mira_kernel_command_depth`

Intended flow:
1. Native runtime or board-support package emits kernel events.
2. The Mira shell or host adapter can queue control commands for native runtimes.
3. A host adapter drains the queue and reads recent snapshots for commands, events, and module state.
4. The web shell or operator console renders faults, module health, queue pressure, and replayable native control history.

Snapshot notes:
- `mira_kernel_read_module_state_at` exposes module snapshots in a stable name-sorted order.
- Recent command/event readers are intended for shell diagnostics, not archival history.
- `mira_kernel_poll_command` drains the live execution queue.
- `mira_kernel_read_last_command` returns the latest retained native command snapshot, even after the active command queue has been drained.

This is intentionally small. It creates a stable bridge first, then higher-level schedulers,
drivers, and board integrations can grow around it without bloating the Python agent core.
