# Mira Kernel Bridge

This crate is the native-side bridge for Mira's execution kernel.

Purpose:
- provide a tiny C ABI for pushing execution events from Rust, C, or firmware adapters
- expose queue depth and per-module state to higher-level shells
- stay small enough to embed beside MCU-facing runtimes later

Current surface:
- `mira_kernel_publish_event`
- `mira_kernel_poll_event`
- `mira_kernel_set_module_state`
- `mira_kernel_read_module_state`
- `mira_kernel_queue_depth`

Intended flow:
1. Native runtime or board-support package emits kernel events.
2. A host adapter drains the queue and forwards snapshots to the Mira shell.
3. The web shell or operator console renders faults, module health, and queue pressure.

This is intentionally small. It creates a stable bridge first, then higher-level schedulers,
drivers, and board integrations can grow around it without bloating the Python agent core.
