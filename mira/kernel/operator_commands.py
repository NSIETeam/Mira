"""Operator command parsing and dispatch for :class:`mira.kernel.app.KernelApp`.

This module keeps the large operator command table out of the kernel facade while
preserving the public ``KernelApp.execute_operator_command`` API.
"""

from __future__ import annotations

import shlex
from typing import Any

from mira.session.goal_state import goal_state_ws_blob, sustained_goal_active
from mira.session.turn_continuation import (
    internal_continuation_pending,
    reset_goal_continuation_rounds,
)
from mira.tool_contracts import (
    tool_contract_family,
    tool_contract_family_counts,
    tool_contract_family_groups,
)

from .scheduler import prioritize_lane


def _copy_rows(rows: list[dict[str, Any]], *, limit: int | None = None) -> list[dict[str, Any]]:
    source = rows[:limit] if isinstance(limit, int) else rows
    return [dict(row) for row in source]


def execute_operator_command(self: Any, command_line: str) -> dict[str, Any]:
    raw = str(command_line or "").strip()
    if not raw:
        raise ValueError("missing command")
    parts = shlex.split(raw)
    command = (parts[0] if parts else "").strip().lower()
    args = parts[1:]
    if command in {"adapter", "board", "bridge", "runtime", "fault", "goal", "lane", "maintenance", "module", "scheduler", "worker", "event", "session", "workspace", "repo", "tool"}:
        subject = command
        verb = (args[0] if args else "").strip().lower()
        tail = args[1:]
        alias_map = {
            ("adapter", "switch"): ("switch-adapter", tail),
            ("adapter", "status"): ("adapter-status", tail),
            ("adapter", "list"): ("adapter-list", tail),
            ("board", "attach"): ("attach-board", tail),
            ("board", "detach"): ("detach-board", tail),
            ("board", "status"): ("board-status", tail),
            ("board", "ports"): ("board-ports", tail),
            ("board", "target"): ("board-target", tail),
            ("board", "transport"): ("board-transport", tail),
            ("board", "mode"): ("board-mode", tail),
            ("bridge", "status"): ("bridge-status", tail),
            ("bridge", "list"): ("bridge-list", tail),
            ("bridge", "fault"): ("bridge-fault", tail),
            ("runtime", "gate"): ("runtime-gate", tail),
            ("runtime", "health"): ("runtime-health", tail),
            ("runtime", "orchestration"): ("runtime-orchestration", tail),
            ("runtime", "queues"): ("runtime-queues", tail),
            ("runtime", "adapters"): ("runtime-adapters", tail),
            ("runtime", "bridges"): ("runtime-bridges", tail),
            ("runtime", "pause"): ("pause-runtime", tail),
            ("runtime", "resume"): ("resume-runtime", tail),
            ("runtime", "degrade"): ("degrade-runtime", tail),
            ("runtime", "drain"): ("drain-background", tail),
            ("runtime", "status"): ("runtime-status", tail),
            ("fault", "clear"): ("clear-fault", tail),
            ("fault", "record"): ("record-fault", tail),
            ("fault", "show"): ("fault-status", tail),
            ("scheduler", "status"): ("scheduler-status", tail),
            ("lane", "prioritize-goal"): ("prioritize-goal-lane", tail),
            ("lane", "show"): ("lane-status", tail),
            ("lane", "list"): ("lane-list", tail),
            ("maintenance", "enter"): ("enter-maintenance", tail),
            ("maintenance", "exit"): ("exit-maintenance", tail),
            ("maintenance", "status"): ("maintenance-status", tail),
            ("module", "focus"): ("focus-module", tail),
            ("module", "show"): ("module-status", tail),
            ("module", "list"): ("module-list", tail),
            ("module", "actions"): ("module-actions", tail),
            ("worker", "show"): ("worker-status", tail),
            ("worker", "list"): ("worker-list", tail),
            ("event", "show"): ("event-status", tail),
            ("event", "tail"): ("event-tail", tail),
            ("session", "status"): ("session-status", tail),
            ("session", "goal"): ("session-goal", tail),
            ("session", "continuation"): ("session-continuation", tail),
            ("goal", "resume"): ("goal-resume", tail),
            ("goal", "complete"): ("goal-complete", tail),
            ("goal", "cancel"): ("goal-cancel", tail),
            ("privilege", "status"): ("privilege-status", tail),
            ("goal", "reset"): ("goal-reset", tail),
            ("kernel", "profile"): ("kernel-profile", tail),
            ("kernel", "manifest"): ("kernel-manifest", tail),
            ("topology", "runtime"): ("runtime-topology", tail),
            ("topology", "embedded"): ("embedded-topology", tail),
            ("workspace", "status"): ("workspace-status", tail),
            ("workspace", "scope"): ("workspace-scope", tail),
            ("workspace", "modules"): ("workspace-modules", tail),
            ("workspace", "focus-module"): ("workspace-focus-module", tail),
            ("native", "status"): ("native-status", tail),
            ("native", "last-command"): ("native-last-command", tail),
            ("native", "replay-last"): ("native-replay-last", tail),
            ("native", "replay"): ("native-replay", tail),
            ("native", "focus"): ("native-focus", tail),
            ("native", "inspect"): ("native-inspect", tail),
            ("native", "modules"): ("native-modules", tail),
            ("repo", "status"): ("repo-status", tail),
            ("repo", "root"): ("repo-root", tail),
            ("repo", "tools"): ("repo-tools", tail),
            ("repo", "prepare-tool"): ("repo-prepare-tool", tail),
            ("tool", "inspect"): ("tool-inspect", tail),
            ("tool", "dispatch"): ("tool-dispatch", tail),
            ("tool", "queue"): ("tool-queue", tail),
            ("tool", "clear-queue"): ("tool-clear-queue", tail),
            ("tool", "prioritize"): ("tool-prioritize", tail),
            ("tool", "drain"): ("tool-drain", tail),
            ("tool", "delegate-goal"): ("tool-delegate-goal", tail),
            ("tool", "delegate-subagent"): ("tool-delegate-subagent", tail),
            ("tool", "complete"): ("tool-complete", tail),
            ("tool", "fail"): ("tool-fail", tail),
            ("tool", "status"): ("tool-status", tail),
        }
        mapped = alias_map.get((subject, verb))
        if mapped is None:
            raise ValueError(f"unknown operator command: {raw}")
        command, args = mapped
    self._assert_operator_command_allowed(command, raw=raw)
    if command == "help":
        return {
            "command": raw,
            "ok": True,
            "target_pane": "control_plane",
            "output": (
                "commands: help, pane <name>, switch-adapter [name], focus-module <name>, "
                "adapter-status [name], adapter-list, module-status [name], module-list, module-actions [name], board-status, board-ports, board-target, board-transport, board-mode, native-status, native-last-command, native-replay-last, native-replay <target> <action> [value], native-focus <module>, native-inspect <module>, native-modules, bridge-status [name], bridge-list, bridge-fault [name], runtime-status, runtime-gate, runtime-health, runtime-orchestration, runtime-queues, runtime-adapters, runtime-bridges, fault-status, scheduler-status, lane-status, lane-list, maintenance-status, worker-status, worker-list, "
                "event-status, event-tail [count], session-status, session-goal, session-continuation, privilege-status, goal-reset, goal-resume, goal-complete, goal-cancel, kernel-profile, kernel-manifest, runtime-topology, embedded-topology, workspace-status, workspace-scope, workspace-modules, workspace-focus-module <name>, repo-status, repo-root, repo-tools, repo-prepare-tool <name>, tool-inspect <name>, tool-dispatch <name>, tool-queue, tool-clear-queue, tool-prioritize, tool-drain, tool-delegate-goal, tool-delegate-subagent, tool-complete, tool-fail, tool-status, "
                "attach-board [port] [transport], detach-board, restart-bridge [adapter], "
                "clear-fault [adapter], record-fault [level] [adapter], pause-runtime [reason], "
                "resume-runtime, degrade-runtime [reason], drain-background, "
                "prioritize-goal-lane, enter-maintenance [reason], exit-maintenance; "
                "aliases: adapter switch|status|list <name>, module focus|show|list|actions <name>, "
                "board attach|detach|status|ports|target|transport|mode [port] [transport], native status|last-command|replay-last|replay <target> <action> [value]|focus <module>|inspect <module>|modules, bridge status|list|fault <name>, runtime pause|resume|degrade|drain|status|gate|health|orchestration|queues|adapters|bridges, fault clear|record|show, "
                "scheduler status, worker show|list, maintenance enter|exit|status, lane prioritize-goal|show|list, event show|tail [count], session status|goal|continuation, privilege status, goal reset|resume|complete|cancel, kernel profile|manifest, topology runtime|embedded, workspace status|scope|modules|focus-module <name>, repo status|root|tools|prepare-tool <name>, tool inspect|dispatch <name>, tool queue|clear-queue|prioritize|drain|delegate-goal|delegate-subagent|complete|fail|status"
            ),
            "runtime_control": self.runtime_control_snapshot(),
            "details": {
                "subject": "help",
                "mode": "reference",
            },
        }
    if command == "pane":
        if not args:
            raise ValueError("missing pane")
        return {
            "command": raw,
            "ok": True,
            "target_pane": args[0],
            "output": f"pane -> {args[0]}",
            "runtime_control": self.runtime_control_snapshot(),
            "details": {
                "subject": "pane",
                "target": args[0],
            },
        }

    target_pane: str | None = None
    output = ""
    details: dict[str, Any] = {}
    if command == "switch-adapter":
        adapter = args[0] if args else self._runtime_control.get("active_adapter")
        if not adapter:
            raise ValueError("missing adapter")
        state = self.switch_runtime_adapter(str(adapter))
        target_pane = "adapters"
        output = f"adapter -> {adapter}"
        details = {"subject": "adapter", "action": "switch", "adapter": adapter}
    elif command == "adapter-status":
        adapter_name = str(args[0] if args else self._runtime_control.get("active_adapter") or "")
        bridge = next(
            (row for row in self._runtime_bridges if str(row.get("adapter") or "") == adapter_name),
            None,
        )
        adapter = next(
            (row for row in self._runtime_adapters if str(row.get("name") or "") == adapter_name),
            None,
        )
        target_pane = "adapters"
        state = self.runtime_control_snapshot()
        output = (
            f"adapter {adapter_name or 'unset'}"
            f" stage={adapter.get('runtime_stage') if isinstance(adapter, dict) else 'unknown'}"
            f" health={bridge.get('health') if isinstance(bridge, dict) else 'unknown'}"
            f" mode={bridge.get('runtime_mode') if isinstance(bridge, dict) else 'unknown'}"
        )
        details = {
            "subject": "adapter",
            "action": "status",
            "adapter": adapter_name or "unset",
            "stage": adapter.get("runtime_stage") if isinstance(adapter, dict) else "unknown",
            "health": bridge.get("health") if isinstance(bridge, dict) else "unknown",
            "mode": bridge.get("runtime_mode") if isinstance(bridge, dict) else "unknown",
        }
    elif command == "adapter-list":
        adapters = [str(row.get("name") or "unknown") for row in self._runtime_adapters]
        target_pane = "adapters"
        state = self.runtime_control_snapshot()
        output = f"adapters count={len(adapters)} active={self._runtime_control.get('active_adapter') or 'unset'}"
        details = {
            "subject": "adapter",
            "action": "list",
            "count": len(adapters),
            "active": self._runtime_control.get("active_adapter") or "unset",
            "items": ", ".join(adapters) or "none",
        }
    elif command == "focus-module":
        if not args:
            raise ValueError("missing module")
        module_name = " ".join(args).strip()
        state = self.focus_runtime_module(module_name)
        target_pane = "modules"
        output = f"module focus -> {module_name}"
        details = {"subject": "module", "action": "focus", "module": module_name}
    elif command == "module-status":
        module_name = " ".join(args).strip() if args else str(
            self._runtime_control.get("module_focus")
            or (self._runtime_modules[0].get("name") if self._runtime_modules else "")
        )
        module = next(
            (row for row in self._runtime_modules if str(row.get("name") or "") == module_name),
            None,
        )
        if not module_name:
            raise ValueError("missing module")
        target_pane = "modules"
        state = self.runtime_control_snapshot()
        output = (
            f"module {module_name}"
            f" status={module.get('status') if isinstance(module, dict) else 'unknown'}"
            f" category={module.get('category') if isinstance(module, dict) else 'unknown'}"
        )
        details = {
            "subject": "module",
            "action": "status",
            "module": module_name,
            "status": module.get("status") if isinstance(module, dict) else "unknown",
            "category": module.get("category") if isinstance(module, dict) else "unknown",
        }
    elif command == "module-list":
        modules = [str(row.get("name") or "unknown") for row in self._runtime_modules]
        target_pane = "modules"
        state = self.runtime_control_snapshot()
        output = f"modules count={len(modules)} focus={self._runtime_control.get('module_focus') or 'unset'}"
        details = {
            "subject": "module",
            "action": "list",
            "count": len(modules),
            "focus": self._runtime_control.get("module_focus") or "unset",
            "items": ", ".join(modules) or "none",
        }
    elif command == "module-actions":
        module_name = " ".join(args).strip() if args else str(
            self._runtime_control.get("module_focus")
            or (self._runtime_modules[0].get("name") if self._runtime_modules else "")
        )
        module = next(
            (row for row in self._runtime_modules if str(row.get("name") or "") == module_name),
            None,
        )
        if not module_name:
            raise ValueError("missing module")
        actions = list(module.get("operator_actions", [])) if isinstance(module, dict) else []
        target_pane = "modules"
        state = self.runtime_control_snapshot()
        output = f"module actions {module_name} count={len(actions)}"
        details = {
            "subject": "module",
            "action": "actions",
            "module": module_name,
            "count": len(actions),
            "items": ", ".join(str(action) for action in actions) or "none",
        }
    elif command == "attach-board":
        port = args[0] if args else None
        transport = args[1] if len(args) > 1 else None
        state = self.attach_board(
            port=str(port).strip() or None if port is not None else None,
            transport=str(transport).strip() or None if transport is not None else None,
        )
        target_pane = "adapters"
        output = f"board attach -> {port or state.get('board', {}).get('port') or 'auto'}"
        board = self._board_runtime_snapshot(dict(state.get("board", {})))
        details = {
            "subject": "board",
            "action": "attach",
            "transport": board.get("transport"),
            "port": board.get("port"),
            "attached": board.get("attached"),
            "health": board.get("health"),
            "mode": board.get("runtime_mode"),
            "error": board.get("last_error"),
        }
    elif command == "detach-board":
        state = self.detach_board()
        target_pane = "adapters"
        output = "board detached"
        details = {"subject": "board", "action": "detach"}
    elif command == "board-status":
        board = self._board_runtime_snapshot(dict(self._runtime_control.get("board", {})))
        target_pane = "adapters"
        state = self.runtime_control_snapshot()
        output = (
            f"board attached={bool(board.get('attached'))}"
            f" health={board.get('health') or 'unknown'}"
            f" transport={board.get('transport') or board.get('preferred_transport') or 'unset'}"
            f" port={board.get('port') or 'auto'}"
            f" mode={board.get('runtime_mode') or 'unprobed'}"
            f" error={board.get('last_error') or 'none'}"
        )
        details = {
            "subject": "board",
            "action": "status",
            "attached": bool(board.get("attached")),
            "health": board.get("health") or "unknown",
            "transport": board.get("transport") or board.get("preferred_transport") or "unset",
            "port": board.get("port") or "auto",
            "mode": board.get("runtime_mode") or "unprobed",
            "error": board.get("last_error") or "none",
        }
    elif command == "board-ports":
        board = self._board_runtime_snapshot(dict(self._runtime_control.get("board", {})))
        ports = list(board.get("available_ports") or [])
        target_pane = "adapters"
        state = self.runtime_control_snapshot()
        output = f"board ports count={len(ports)} preferred={board.get('preferred_transport') or 'unset'}"
        details = {
            "subject": "board",
            "action": "ports",
            "count": len(ports),
            "preferred_transport": board.get("preferred_transport") or "unset",
            "items": ", ".join(str(port) for port in ports) or "none",
        }
    elif command == "board-target":
        board = self._board_runtime_snapshot(dict(self._runtime_control.get("board", {})))
        target_pane = "adapters"
        state = self.runtime_control_snapshot()
        output, details = (
            f"board target={board.get('target') or 'unknown'}"
            f" attached={bool(board.get('attached'))}",
            {
                "subject": "board",
                "action": "target",
                "target": board.get("target") or "unknown",
                "attached": bool(board.get("attached")),
                "mode": board.get("runtime_mode") or "unprobed",
            },
        )
    elif command == "board-transport":
        board = self._board_runtime_snapshot(dict(self._runtime_control.get("board", {})))
        target_pane = "adapters"
        state = self.runtime_control_snapshot()
        transport = board.get("transport") or board.get("preferred_transport") or "unset"
        output, details = (
            f"board transport={transport}"
            f" port={board.get('port') or 'auto'}",
            {
                "subject": "board",
                "action": "transport",
                "transport": transport,
                "preferred_transport": board.get("preferred_transport") or "unset",
                "port": board.get("port") or "auto",
                "ports_known": len(list(board.get("available_ports") or [])),
            },
        )
    elif command == "board-mode":
        board = self._board_runtime_snapshot(dict(self._runtime_control.get("board", {})))
        target_pane = "adapters"
        state = self.runtime_control_snapshot()
        output, details = (
            f"board mode={board.get('runtime_mode') or 'unprobed'}"
            f" artifact={board.get('bridge_artifact') or 'none'}",
            {
                "subject": "board",
                "action": "mode",
                "mode": board.get("runtime_mode") or "unprobed",
                "artifact": board.get("bridge_artifact") or "none",
                "error": board.get("last_error") or "none",
            },
        )
    elif command == "native-status":
        native_context = self._native_runtime_snapshot()
        native_last_command = dict(native_context.get("last_command") or {})
        target_pane = "adapters"
        state = self.runtime_control_snapshot()
        queue_depth = native_context.get("queue_depth", 0)
        module_count = native_context.get("module_count", 0)
        last_summary = native_last_command.get("summary") or "none:none"
        artifact = native_context.get("bridge_artifact") or "none"
        details = self._native_summary_details(
            action="status",
            command="status",
            status=str(native_last_command.get("status") or "idle"),
            code=int(native_last_command.get("code") or 0),
            updated_at_ms=native_last_command.get("updated_at_ms"),
        )
        details["module_focus"] = self._runtime_control.get("module_focus") or "none"
        details["status_row"] = {
            "queue_depth": int(queue_depth or 0),
            "command_depth": int(details.get("command_depth") or 0),
            "module_count": int(module_count or 0),
            "last_target": str(details.get("last_target") or "none"),
            "last_action": str(details.get("last_action") or "none"),
            "last_summary": str(last_summary or "none:none"),
            "module_focus": str(details.get("module_focus") or "none"),
            "artifact": str(artifact or "none"),
            "updated_at_ms": native_last_command.get("updated_at_ms"),
        }
        output, details = (
            f"native queue={queue_depth}"
            f" modules={module_count}"
            f" last={last_summary}"
            f" artifact={artifact}",
            details,
        )
    elif command == "native-last-command":
        native_context = self._native_runtime_snapshot()
        native_last_command = dict(native_context.get("last_command") or {})
        target_pane = "adapters"
        state = self.runtime_control_snapshot()
        target = native_last_command.get("target") or "none"
        action = native_last_command.get("action") or "none"
        command_text = native_last_command.get("command") or action
        queue_depth = native_last_command.get("queue_depth", 0)
        details = self._native_summary_details(
            action="last-command",
            target=target,
            command=command_text,
            value=str(native_last_command.get("value") or ""),
            status=str(native_last_command.get("status") or "idle"),
            code=int(native_last_command.get("code") or 0),
            updated_at_ms=native_last_command.get("updated_at_ms"),
        )
        details["action_row"] = {
            "target": target,
            "action": action,
            "command": command_text,
            "value": str(native_last_command.get("value") or ""),
            "status": str(native_last_command.get("status") or "idle"),
            "code": int(native_last_command.get("code") or 0),
            "queue_depth": int(queue_depth or 0),
            "artifact": str(native_last_command.get("artifact") or details.get("artifact") or "none"),
            "updated_at_ms": native_last_command.get("updated_at_ms"),
        }
        output, details = (
            f"native last-command target={target}"
            f" action={action}"
            f" depth={queue_depth}",
            details,
        )
    elif command == "native-replay-last":
        native_context = self._native_runtime_snapshot()
        native_last_command = dict(native_context.get("last_command") or {})
        target = str(native_last_command.get("target") or "").strip()
        action = str(native_last_command.get("action") or "").strip()
        value = str(native_last_command.get("value") or "")
        if not target or not action:
            raise ValueError("native replay unavailable")
        state, output, details, target_pane = self._dispatch_native_action(
            action_label="replay-last",
            target=target,
            command=action,
            value=value,
        )
    elif command == "native-replay":
        target = str(args[0] if len(args) > 0 else "").strip()
        action = str(args[1] if len(args) > 1 else "").strip()
        value = " ".join(str(arg) for arg in args[2:]).strip() if len(args) > 2 else ""
        if not target or not action:
            raise ValueError("usage: native replay <target> <action> [value]")
        state, output, details, target_pane = self._dispatch_native_action(
            action_label="replay",
            target=target,
            command=action,
            value=value,
        )
    elif command == "native-focus":
        module_name = str(args[0] if args else self._runtime_control.get("module_focus") or "").strip()
        if not module_name:
            raise ValueError("missing module")
        state = self.focus_runtime_module(module_name)
        details = self._native_command_details(
            action="focus",
            target=module_name,
            command="focus_module",
            value=module_name,
        )
        output = f"native focus module={module_name} depth={details.get('queue_depth', 0)}"
        target_pane = "modules"
    elif command == "native-inspect":
        module_name = str(args[0] if args else self._runtime_control.get("module_focus") or "").strip()
        if not module_name:
            raise ValueError("missing module")
        self._dispatch_native_control(target=module_name, action="inspect", value="status")
        native_context = self._native_runtime_snapshot()
        native_modules = dict(native_context.get("modules") or {})
        native_state = dict(native_modules.get(module_name) or {})
        state = self.runtime_control_snapshot()
        status = native_state.get("status") or "unknown"
        last_code = native_state.get("last_code") if native_state else 0
        details = self._native_command_details(
            action="inspect",
            target=module_name,
            command="inspect",
            value="status",
            status=status,
            code=last_code,
            updated_at_ms=native_state.get("updated_at_ms") if native_state else None,
        )
        output = (
            f"native inspect module={module_name}"
            f" status={status}"
            f" code={last_code}"
            f" depth={details.get('queue_depth', 0)}"
        )
        details["last_code"] = last_code
        details["inspect_row"] = {
            "module": module_name,
            "status": status,
            "code": last_code,
            "command": "inspect",
            "value": "status",
            "queue_depth": int(details.get("queue_depth") or 0),
            "artifact": str(details.get("artifact") or "none"),
            "updated_at_ms": native_state.get("updated_at_ms") if native_state else None,
        }
        target_pane = "modules"
    elif command == "native-modules":
        native_context = self._native_runtime_snapshot()
        native_modules = dict(native_context.get("modules") or {})
        module_count = int(native_context.get("module_count", len(native_modules)))
        target_pane = "modules"
        state = self.runtime_control_snapshot()
        details = self._native_summary_details(
            action="modules",
            command="modules",
            status="ready" if module_count else "idle",
            updated_at_ms=max(
                (
                    int(row.get("updated_at_ms") or 0)
                    for row in native_modules.values()
                    if isinstance(row, dict)
                ),
                default=0,
            ) or None,
        )
        details["count"] = module_count
        details["items"] = ", ".join(
            f"{name}:{row.get('status', 'unknown')}"
            for name, row in native_modules.items()
            if isinstance(row, dict)
        ) or "none"
        details["codes"] = ", ".join(
            f"{name}:{row.get('last_code', 0)}"
            for name, row in native_modules.items()
            if isinstance(row, dict)
        ) or "none"
        details["updated"] = ", ".join(
            f"{name}:{row.get('updated_at_ms', 0)}"
            for name, row in native_modules.items()
            if isinstance(row, dict)
        ) or "none"
        details["module_rows"] = [
            {
                "name": name,
                "status": row.get("status", "unknown"),
                "code": row.get("last_code", 0),
                "updated_at_ms": row.get("updated_at_ms"),
            }
            for name, row in native_modules.items()
            if isinstance(row, dict)
        ]
        output, details = (
            f"native modules count={module_count}",
            details,
        )
    elif command == "bridge-status":
        bridge_name = str(args[0] if args else self._runtime_control.get("active_adapter") or "")
        bridge = next(
            (row for row in self._runtime_bridges if str(row.get("adapter") or "") == bridge_name),
            None,
        )
        target_pane = "adapters"
        state = self.runtime_control_snapshot()
        bridge = bridge if isinstance(bridge, dict) else {}
        health = bridge.get("health") or "unknown"
        status = bridge.get("status") or "unknown"
        mode = bridge.get("runtime_mode") or "unknown"
        output, details = (
            f"bridge {bridge_name or 'unset'}"
            f" health={health}"
            f" status={status}"
            f" mode={mode}",
            {
                "subject": "bridge",
                "action": "status",
                "bridge": bridge_name or "unset",
                "health": health,
                "status": status,
                "mode": mode,
                "runtime": bridge.get("runtime") or bridge_name or "unknown",
                "version": bridge.get("version") or "unknown",
                "queue_depth": int(bridge.get("queue_depth") or 0),
                "module_count": int(bridge.get("module_count") or 0),
                "updated_at_ms": bridge.get("updated_at_ms"),
                "manifest": bridge.get("manifest") or "none",
                "abi": bridge.get("abi") or "unknown",
                "status_symbol": bridge.get("status_symbol") or "none",
                "kernel_surface": bridge.get("kernel_surface") or "mira",
                "runtime_stage": bridge.get("runtime_stage") or "unknown",
                "free_symbol": bridge.get("free_symbol") or "none",
                "attach_symbol": bridge.get("attach_symbol") or "none",
                "capabilities": ", ".join(bridge.get("capabilities") or []) or "none",
                "module_states": ", ".join(
                    f"{name}:{row.get('status', 'unknown')}:{row.get('last_code', 0)}"
                    for name, row in dict(bridge.get("module_states") or {}).items()
                    if isinstance(row, dict)
                ) or "none",
                "last_command": (
                    f"{dict(bridge.get('last_command') or {}).get('target', 'runtime')}:"
                    f"{dict(bridge.get('last_command') or {}).get('action', 'status')}:"
                    f"{dict(bridge.get('last_command') or {}).get('status', 'unknown')}:"
                    f"{dict(bridge.get('last_command') or {}).get('code', 0)}"
                ),
                "recent_commands": ", ".join(
                    f"{dict(row).get('target', 'runtime')}:{dict(row).get('action', 'status')}:{dict(row).get('status', 'unknown')}:{dict(row).get('code', 0)}"
                    for row in list(bridge.get("recent_commands") or [])
                    if isinstance(row, dict)
                ) or "none",
                "recent_command_rows": [
                    {
                        "target": dict(row).get("target") or "runtime",
                        "action": dict(row).get("action") or "status",
                        "status": dict(row).get("status") or "unknown",
                        "code": int(dict(row).get("code") or 0),
                        "updated_at_ms": dict(row).get("updated_at_ms"),
                    }
                    for row in list(bridge.get("recent_commands") or [])
                    if isinstance(row, dict)
                ],
                "status_row": {
                    "bridge": bridge_name or "unset",
                    "runtime": bridge.get("runtime") or bridge_name or "unknown",
                    "health": health,
                    "status": status,
                    "mode": mode,
                    "queue_depth": int(bridge.get("queue_depth") or 0),
                    "module_count": int(bridge.get("module_count") or 0),
                    "updated_at_ms": bridge.get("updated_at_ms"),
                },
                "board_capable": bool(bridge.get("board_capable")),
            },
        )
    elif command == "bridge-list":
        bridges = [str(row.get("adapter") or "unknown") for row in self._runtime_bridges]
        target_pane = "adapters"
        state = self.runtime_control_snapshot()
        active_adapter = str(self._runtime_control.get("active_adapter") or "")
        output, details = (
            f"bridges count={len(bridges)} active={active_adapter or 'unset'}",
            {
                "subject": "bridge",
                "action": "list",
                "count": len(bridges),
                "active": active_adapter or "unset",
                "items": ", ".join(bridges) or "none",
            },
        )
    elif command == "bridge-fault":
        bridge_name = str(args[0] if args else self._runtime_control.get("active_adapter") or "")
        bridge = next(
            (row for row in self._runtime_bridges if str(row.get("adapter") or "") == bridge_name),
            None,
        )
        target_pane = "faults"
        state = self.runtime_control_snapshot()
        bridge = bridge if isinstance(bridge, dict) else {}
        health = bridge.get("health") or "unknown"
        error = bridge.get("last_error") or "none"
        output, details = (
            f"bridge fault {bridge_name or 'unset'}"
            f" health={health}"
            f" error={error}",
            {
                "subject": "bridge",
                "action": "fault",
                "bridge": bridge_name or "unset",
                "health": health,
                "error": error,
                "status": bridge.get("status") or "unknown",
            },
        )
    elif command == "restart-bridge":
        adapter = args[0] if args else None
        state = self.restart_bridge(str(adapter).strip() or None if adapter is not None else None)
        target_pane = "adapters"
        output = f"bridge restart -> {adapter or self._runtime_control.get('active_adapter') or 'active'}"
        details = {
            "subject": "bridge",
            "action": "restart",
            "adapter": adapter or self._runtime_control.get("active_adapter") or "active",
        }
    elif command == "clear-fault":
        adapter = args[0] if args else None
        state = self.clear_fault(str(adapter).strip() or None if adapter is not None else None)
        target_pane = "faults"
        output, details = (
            "fault posture cleared",
            {
                "subject": "fault",
                "action": "clear",
                "adapter": adapter or "active",
            },
        )
    elif command == "record-fault":
        level = args[0] if args else "fault"
        adapter = args[1] if len(args) > 1 else None
        state = self.record_fault(
            str(level).strip() or "fault",
            str(adapter).strip() or None if adapter is not None else None,
        )
        target_pane = "faults"
        output, details = (
            f"fault recorded -> {str(level) or 'fault'}",
            {
                "subject": "fault",
                "action": "record",
                "level": str(level) or "fault",
                "adapter": adapter or "active",
            },
        )
    elif command == "fault-status":
        posture = dict(self._runtime_control.get("fault_posture", {}))
        target_pane = "faults"
        state = self.runtime_control_snapshot()
        current_level = posture.get("level") or "unknown"
        supervisor = posture.get("supervisor") or "unknown"
        adapters = ",".join(posture.get("affected_adapters") or []) or "none"
        output, details = (
            f"fault level={current_level}"
            f" supervisor={supervisor}"
            f" adapters={adapters}",
            {
                "subject": "fault",
                "action": "status",
                "level": current_level,
                "supervisor": supervisor,
                "adapters": adapters,
            },
        )
    elif command == "scheduler-status":
        scheduler = self.scheduler_snapshot(session_metadata=self._active_session_metadata())
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        queues = list(scheduler.get("queues", []))
        active_runtime = scheduler.get("active_runtime", {})
        active_adapter = active_runtime.get("adapter") if isinstance(active_runtime, dict) else "none"
        output = (
            f"scheduler policy={scheduler.get('policy') or 'unknown'}"
            f" queues={len(queues)}"
            f" active_runtime={active_adapter or 'none'}"
        )
        details = {
            "subject": "scheduler",
            "action": "status",
            "policy": scheduler.get("policy") or "unknown",
            "queues": len(queues),
            "foreground_depth": next((q.get("depth") for q in queues if q.get("id") == "foreground"), 0),
            "goal_depth": next((q.get("depth") for q in queues if q.get("id") == "goal_background"), 0),
        }
    elif command == "lane-status":
        lanes = self.execution_lanes(session_metadata=self._active_session_metadata())
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        lead = lanes[0] if lanes else {}
        output, details = (
            f"lanes count={len(lanes)}"
            f" lead={lead.get('id', 'none')}"
            f" state={lead.get('state', 'unknown')}",
            {
                "subject": "lane",
                "action": "status",
                "count": len(lanes),
                "lead": lead.get("id", "none"),
                "lead_mode": lead.get("mode", "unknown"),
                "lead_state": lead.get("state", "unknown"),
            },
        )
    elif command == "lane-list":
        lanes = self.execution_lanes(session_metadata=self._active_session_metadata())
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output, details = (
            f"lanes count={len(lanes)}",
            {
                "subject": "lane",
                "action": "list",
                "count": len(lanes),
                "items": ", ".join(str(lane.get("id") or "unknown") for lane in lanes) or "none",
            },
        )
    elif command == "maintenance-status":
        maintenance = dict(self._runtime_control.get("maintenance_mode", {}))
        gate = dict(self._runtime_control.get("execution_gate", {}))
        target_pane = "control_plane"
        state = self.runtime_control_snapshot()
        enabled = "on" if maintenance.get("enabled") else "off"
        output = (
            f"maintenance enabled={enabled}"
            f" gate={gate.get('state') or 'unknown'}"
        )
        details = {
            "subject": "maintenance",
            "action": "status",
            "enabled": enabled,
            "reason": maintenance.get("reason") or "none",
            "gate": gate.get("state") or "unknown",
        }
    elif command == "worker-status":
        workers = self.worker_snapshot(session_metadata=self._active_session_metadata())
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        lead = workers[0] if workers else {}
        output, details = (
            f"workers count={len(workers)}"
            f" lead={lead.get('id', 'none')}"
            f" state={lead.get('state', 'unknown')}",
            {
                "subject": "worker",
                "action": "status",
                "count": len(workers),
                "lead": lead.get("id", "none"),
                "lead_kind": lead.get("kind", "unknown"),
                "lead_state": lead.get("state", "unknown"),
            },
        )
    elif command == "worker-list":
        workers = self.worker_snapshot(session_metadata=self._active_session_metadata())
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output, details = (
            f"workers count={len(workers)}",
            {
                "subject": "worker",
                "action": "list",
                "count": len(workers),
                "items": ", ".join(str(worker.get("id") or "unknown") for worker in workers) or "none",
            },
        )
    elif command == "event-status":
        event_rows = _copy_rows(self._event_log)
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        head = event_rows[0] if event_rows else {}
        output, details = (
            f"events count={len(event_rows)}"
            f" latest={head.get('type', 'none')}"
            f" state={head.get('state', 'idle')}",
            {
                "subject": "event",
                "action": "status",
                "count": len(event_rows),
                "latest": head.get("type", "none"),
                "state": head.get("state", "idle"),
                "items": ", ".join(str(row.get("type") or "event") for row in event_rows[:6]) or "none",
            },
        )
    elif command == "event-tail":
        event_rows = _copy_rows(self._event_log)
        limit = 5
        if args:
            try:
                limit = max(1, min(int(args[0]), 12))
            except ValueError as exc:
                raise ValueError("event tail count must be an integer") from exc
        selected = event_rows[:limit]
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output, details = (
            f"event tail count={len(selected)}",
            {
                "subject": "event",
                "action": "tail",
                "count": len(selected),
                "items": ", ".join(
                    f"{row.get('type', 'event')}:{row.get('state', 'unknown')}"
                    for row in selected
                ) or "none",
            },
        )
    elif command == "session-status":
        session_key = self._active_session_key or "none"
        status = self._session_status.get(session_key, "idle") if session_key != "none" else "idle"
        latency = self._session_latency.get(session_key)
        metadata = self._active_session_metadata() or {}
        checkpoint = self._active_checkpoint()
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        goal_blob = goal_state_ws_blob(metadata)
        continuation = "on" if internal_continuation_pending(metadata) else "off"
        latency_value = latency if latency is not None else "n/a"
        output, details = (
            f"session {session_key}"
            f" status={status}"
            f" latency_ms={latency_value}"
            f" continuation={continuation}",
            {
                "subject": "session",
                "action": "status",
                "session": session_key,
                "status": status,
                "latency_ms": latency_value,
                "continuation": continuation,
                "goal_active": "on" if goal_blob.get("active") else "off",
                "memory": "on" if self._profile.memory_enabled else "off",
                "checkpoint_phase": str((checkpoint or {}).get("phase") or "none"),
                "checkpoint_iteration": int((checkpoint or {}).get("iteration") or 0),
                "metadata_keys": len(metadata),
            },
        )
    elif command == "session-goal":
        metadata = self._active_session_metadata() or {}
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        goal_blob = goal_state_ws_blob(metadata)
        active = "on" if goal_blob.get("active") else "off"
        continuation = "on" if internal_continuation_pending(metadata) else "off"
        rounds = int(metadata.get("_sustained_goal_continuation_rounds") or 0) if metadata else 0
        output, details = (
            f"goal active={active}"
            f" status={goal_blob.get('status') or 'idle'}",
            {
                "subject": "session",
                "action": "goal",
                "active": active,
                "status": goal_blob.get("status") or "idle",
                "summary": goal_blob.get("ui_summary") or goal_blob.get("objective") or "none",
                "continuation": continuation,
                "continuation_rounds": rounds,
                "memory": "on" if self._profile.memory_enabled else "off",
            },
        )
    elif command == "session-continuation":
        metadata = self._active_session_metadata() or {}
        rounds = int(metadata.get("_sustained_goal_continuation_rounds") or 0) if metadata else 0
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        pending = "on" if internal_continuation_pending(metadata) else "off"
        goal_active = "on" if sustained_goal_active(metadata) else "off"
        output, details = (
            f"continuation pending={pending}"
            f" rounds={rounds}"
            f" goal_active={goal_active}",
            {
                "subject": "session",
                "action": "continuation",
                "pending": pending,
                "rounds": rounds,
                "goal_active": goal_active,
                "session": self._active_session_key or "none",
                "memory": "on" if self._profile.memory_enabled else "off",
                "metadata_keys": len(metadata),
            },
        )
    elif command == "privilege-status":
        host_contract = self._shell.host_contract if isinstance(self._shell.host_contract, dict) else {}
        surfaces = host_contract.get("surfaces", {}) if isinstance(host_contract.get("surfaces", {}), dict) else {}
        privilege = host_contract.get("privilege", {}) if isinstance(host_contract.get("privilege", {}), dict) else {}
        privilege_role = str(privilege.get("role") or self._operator_privilege_role())
        can_elevate = bool(privilege.get("canElevate"))
        elevation_mode = str(privilege.get("elevationMode") or ("live" if privilege_role == "root" else "none"))
        elevate_hint = str(privilege.get("elevateHint") or "").strip() or "none"
        drop_hint = str(privilege.get("dropHint") or "").strip() or "none"
        session_policy = str(privilege.get("sessionPolicy") or "observe-only")
        controls_enabled = bool(surfaces.get("allowPrivilegedRuntimeControls"))
        target_pane = "control_plane"
        state = self.runtime_control_snapshot()
        output, details = (
            f"privilege role={privilege_role}"
            f" can_elevate={'yes' if can_elevate else 'no'}"
            f" mode={elevation_mode}"
            f" controls={'enabled' if controls_enabled else 'restricted'}",
            {
                "subject": "privilege",
                "action": "status",
                "role": privilege_role,
                "can_elevate": can_elevate,
                "elevation_mode": elevation_mode,
                "controls_enabled": controls_enabled,
                "session_policy": session_policy,
                "elevate_hint": elevate_hint,
                "drop_hint": drop_hint,
            },
        )
    elif command == "goal-resume":
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output, details = self._operator_goal_update("resume")
    elif command == "goal-complete":
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output, details = self._operator_goal_update("complete")
    elif command == "goal-cancel":
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output, details = self._operator_goal_update("cancel")
    elif command == "goal-reset":
        metadata = self._active_session_metadata()
        if metadata is None:
            raise ValueError("no active session")
        reset_goal_continuation_rounds(metadata)
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output = "goal continuation budget reset"
        details = {
            "subject": "goal",
            "action": "reset",
            "continuation": "off",
            "session": self._active_session_key or "none",
        }
    elif command == "kernel-profile":
        profile = self._profile.to_dict()
        target_pane = "control_plane"
        state = self.runtime_control_snapshot()
        output = (
            f"kernel profile name={profile.get('name') or 'unknown'}"
            f" gui={'on' if profile.get('gui_enabled') else 'off'}"
            f" api={'on' if profile.get('api_enabled') else 'off'}"
            f" targets={len(profile.get('runtime_targets') or [])}"
        )
        details = {
            "subject": "kernel",
            "action": "profile",
            "profile": profile.get("name") or "unknown",
            "targets": ", ".join(profile.get("runtime_targets") or []) or "none",
            "languages": ", ".join(profile.get("implementation_languages") or []) or "none",
            "automations": "on" if profile.get("automations_enabled") else "off",
            "memory": "on" if profile.get("memory_enabled") else "off",
        }
    elif command == "kernel-manifest":
        manifest = self.manifest_snapshot()
        identity = dict(manifest.get("identity", {}))
        contracts = dict(manifest.get("contracts", {}))
        target_pane = "control_plane"
        state = self.runtime_control_snapshot()
        output = (
            f"kernel manifest app={identity.get('app_name') or 'unknown'}"
            f" cli={identity.get('cli_name') or 'unknown'}"
            f" adapters={len(manifest.get('runtime_adapters') or [])}"
            f" modules={len(manifest.get('runtime_modules') or [])}"
        )
        details = {
            "subject": "kernel",
            "action": "manifest",
            "app": identity.get("app_name") or "unknown",
            "cli": identity.get("cli_name") or "unknown",
            "manifest_version": contracts.get("manifest_version") or 0,
            "event_version": contracts.get("event_version") or 0,
            "snapshot_version": contracts.get("snapshot_version") or 0,
        }
    elif command == "runtime-topology":
        topology = self.runtime_topology_snapshot(session_metadata=self._active_session_metadata())
        scheduler = dict(topology.get("scheduler", {}))
        workers = list(topology.get("workers", []))
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output = (
            f"runtime topology adapters={len(topology.get('adapters', []))}"
            f" modules={len(topology.get('modules', []))}"
            f" lanes={len(topology.get('execution_lanes', []))}"
            f" workers={len(workers)}"
        )
        details = {
            "subject": "topology",
            "action": "runtime",
            "preferred_lane": scheduler.get("preferred_lane") or "interactive",
            "dispatch_handoff": scheduler.get("dispatch_handoff_lane") or "none",
            "adapters": ", ".join(str(row.get("name") or "unknown") for row in topology.get("adapters", [])) or "none",
            "modules": ", ".join(str(row.get("name") or "unknown") for row in topology.get("modules", [])) or "none",
            "lanes": ", ".join(str(row.get("id") or "lane") for row in topology.get("execution_lanes", [])) or "none",
        }
    elif command == "embedded-topology":
        topology = self.embedded_topology_snapshot()
        board = dict(topology.get("board", {}))
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output = (
            f"embedded topology attached={'yes' if board.get('attached') else 'no'}"
            f" transport={board.get('transport') or board.get('preferred_transport') or 'unset'}"
            f" target={board.get('target') or 'host'}"
        )
        details = {
            "subject": "topology",
            "action": "embedded",
            "attached": "yes" if board.get("attached") else "no",
            "port": board.get("port") or "none",
            "transport": board.get("transport") or board.get("preferred_transport") or "unset",
            "target": board.get("target") or "host",
            "runtime_mode": board.get("runtime_mode") or "userland",
            "available_ports": ", ".join(board.get("available_ports") or []) or "none",
        }
    elif command == "workspace-status":
        workspace = self._workspace_root()
        target_pane = "workspace"
        state = self.runtime_control_snapshot()
        output = f"workspace {workspace.name} path={workspace}"
        details = {
            "subject": "workspace",
            "action": "status",
            "name": workspace.name or "workspace",
            "path": str(workspace),
            "session": self._active_session_key or "none",
        }
    elif command == "workspace-scope":
        workspace = self._workspace_root()
        repo = self._repo_root()
        target_pane = "workspace"
        state = self.runtime_control_snapshot()
        output = (
            f"workspace scope root={workspace}"
            f" repo={'attached' if repo is not None else 'detached'}"
        )
        details = {
            "subject": "workspace",
            "action": "scope",
            "path": str(workspace),
            "repo_root": str(repo) if repo is not None else "none",
            "restrict_mode": "workspace",
        }
    elif command == "workspace-modules":
        workspace = self._workspace_root()
        modules = [
            str(row.get("name") or "unknown")
            for row in self._runtime_modules
            if str(row.get("status") or "") == "enabled"
        ]
        target_pane = "workspace"
        state = self.runtime_control_snapshot()
        output = f"workspace modules count={len(modules)} root={workspace.name or 'workspace'}"
        details = {
            "subject": "workspace",
            "action": "modules",
            "root": str(workspace),
            "count": len(modules),
            "items": ", ".join(modules) or "none",
        }
    elif command == "workspace-focus-module":
        if not args:
            raise ValueError("missing module")
        module_name = " ".join(args).strip()
        workspace = self._workspace_root()
        state = self.focus_runtime_module(module_name)
        target_pane = "modules"
        output = f"workspace {workspace.name or 'workspace'} module focus -> {module_name}"
        details = {
            "subject": "workspace",
            "action": "focus-module",
            "root": str(workspace),
            "module": module_name,
        }
    elif command == "repo-status":
        repo = self._repo_root()
        workspace = self._workspace_root()
        target_pane = "workspace"
        state = self.runtime_control_snapshot()
        output = (
            f"repo {'attached' if repo is not None else 'missing'}"
            f" root={repo if repo is not None else workspace}"
        )
        details = {
            "subject": "repo",
            "action": "status",
            "attached": repo is not None,
            "root": str(repo) if repo is not None else str(workspace),
            "workspace": str(workspace),
        }
    elif command == "repo-root":
        repo = self._repo_root()
        if repo is None:
            raise ValueError("repo root unavailable")
        target_pane = "workspace"
        state = self.runtime_control_snapshot()
        output = f"repo root -> {repo}"
        details = {
            "subject": "repo",
            "action": "root",
            "root": str(repo),
            "name": repo.name or "repo",
        }
    elif command == "repo-tools":
        repo = self._repo_root()
        workspace = self._workspace_root()
        tools = list(self._profile.tools)
        families = sorted({tool_contract_family(tool) for tool in tools})
        family_counts = tool_contract_family_counts(tools)
        family_groups = tool_contract_family_groups(tools)
        target_pane = "workspace"
        state = self.runtime_control_snapshot()
        output = (
            f"repo tools count={len(tools)}"
            f" root={(repo if repo is not None else workspace).name or 'workspace'}"
            f" families={','.join(f'{family}:{family_counts[family]}' for family in sorted(family_counts)) or 'none'}"
        )
        details = {
            "subject": "repo",
            "action": "tools",
            "root": str(repo) if repo is not None else str(workspace),
            "count": len(tools),
            "items": ", ".join(str(tool) for tool in tools) or "none",
            "families": ", ".join(families) or "none",
            "family_counts": ", ".join(
                f"{family}:{family_counts[family]}" for family in sorted(family_counts)
            ) or "none",
            "family_groups": "; ".join(
                f"{family}=[{', '.join(items)}]" for family, items in family_groups.items()
            ) or "none",
        }
    elif command == "repo-prepare-tool":
        if not args:
            raise ValueError("missing tool")
        tool_name = " ".join(args).strip()
        if tool_name not in self._profile.tools:
            raise ValueError(f"unknown tool contract: {tool_name}")
        tool_family = tool_contract_family(tool_name)
        repo = self._repo_root()
        workspace = self._workspace_root()
        self._record_kernel_event(
            "tool_contract_prepared",
            state="ready",
            message=(
                f"{tool_name} [{tool_family}] prepared for "
                f"{(repo if repo is not None else workspace).name or 'workspace'}"
            ),
        )
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output = f"tool contract prepared -> {tool_name} [{tool_family}]"
        details = {
            "subject": "repo",
            "action": "prepare-tool",
            "tool": tool_name,
            "family": tool_family,
            "root": str(repo) if repo is not None else str(workspace),
            "status": "ready",
        }
    elif command == "tool-inspect":
        if not args:
            raise ValueError("missing tool")
        tool_name = " ".join(args).strip()
        if tool_name not in self._profile.tools:
            raise ValueError(f"unknown tool contract: {tool_name}")
        tool_family = tool_contract_family(tool_name)
        repo = self._repo_root()
        workspace = self._workspace_root()
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output = f"tool {tool_name} contract available [{tool_family}]"
        details = {
            "subject": "tool",
            "action": "inspect",
            "tool": tool_name,
            "family": tool_family,
            "root": str(repo) if repo is not None else str(workspace),
            "workspace": str(workspace),
        }
    elif command == "tool-dispatch":
        if not args:
            raise ValueError("missing tool")
        tool_name = " ".join(args).strip()
        if tool_name not in self._profile.tools:
            raise ValueError(f"unknown tool contract: {tool_name}")
        tool_family = tool_contract_family(tool_name)
        repo = self._repo_root()
        workspace = self._workspace_root()
        active_module = str(
            self._runtime_control.get("module_focus")
            or (self._runtime_modules[0].get("name") if self._runtime_modules else "session_state")
        )
        self._dispatch_queue.insert(
            0,
            {
                "tool": tool_name,
                "family": tool_family,
                "module": active_module,
                "root": str(repo) if repo is not None else str(workspace),
                "status": "queued",
                "lifecycle": "queued",
            },
        )
        self._dispatch_queue = self._dispatch_queue[:12]
        self._record_kernel_event(
            "tool_dispatch_requested",
            state="queued",
            message=(
                f"{tool_name} [{tool_family}] dispatched via {active_module}"
                f" in {(repo if repo is not None else workspace).name or 'workspace'}"
            ),
        )
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output = f"tool dispatched -> {tool_name} [{tool_family}]"
        details = {
            "subject": "tool",
            "action": "dispatch",
            "tool": tool_name,
            "family": tool_family,
            "module": active_module,
            "root": str(repo) if repo is not None else str(workspace),
            "status": "queued",
        }
    elif command == "tool-queue":
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        queue_snapshot = self._dispatch_queue_snapshot()
        output = f"tool queue depth={len(self._dispatch_queue)}"
        details = {
            "subject": "tool",
            "action": "queue",
            "count": queue_snapshot["queue_depth"],
            "priority": queue_snapshot["priority"],
            "handoff": queue_snapshot["handoff"],
            "items": queue_snapshot["items"],
            "lifecycle": queue_snapshot["lifecycle"],
            "roots": queue_snapshot["roots"],
        }
    elif command == "tool-clear-queue":
        cleared = len(self._dispatch_queue)
        self._dispatch_queue = []
        self._record_kernel_event(
            "tool_dispatch_queue_cleared",
            state="ok",
            message=f"cleared {cleared} queued tool dispatch(es)",
        )
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output = "tool queue cleared"
        details = {
            "subject": "tool",
            "action": "clear-queue",
            "cleared": cleared,
        }
    elif command == "tool-prioritize":
        for row in self._dispatch_queue:
            row["lifecycle"] = "prioritized"
        self._scheduler_state = prioritize_lane(
            self._scheduler_state,
            lane="interactive",
        )
        self._scheduler_state["dispatch_priority"] = True
        self._record_kernel_event(
            "tool_dispatch_prioritized",
            state="ok",
            message="scheduler priority shifted toward tool dispatch queue",
        )
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        queue_snapshot = self._dispatch_queue_snapshot()
        output = "tool dispatch queue prioritized"
        details = {
            "subject": "tool",
            "action": "prioritize",
            "count": queue_snapshot["queue_depth"],
            "preferred_lane": "interactive",
            "priority": queue_snapshot["priority"],
            "handoff": queue_snapshot["handoff"],
            "items": queue_snapshot["items"],
        }
    elif command == "tool-drain":
        drained = min(len(self._dispatch_queue), 3)
        for row in self._dispatch_queue[:drained]:
            row["lifecycle"] = "drained"
        self._dispatch_queue = self._dispatch_queue[drained:]
        self._scheduler_state["dispatch_priority"] = False
        self._scheduler_state["dispatch_handoff_lane"] = None
        self._record_kernel_event(
            "tool_dispatch_drained",
            state="ok",
            message=f"drained {drained} queued tool dispatch(es)",
        )
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        queue_snapshot = self._dispatch_queue_snapshot()
        output = "tool dispatch queue drained"
        details = {
            "subject": "tool",
            "action": "drain",
            "drained": drained,
            "remaining": queue_snapshot["queue_depth"],
            "items": queue_snapshot["items"],
            "lifecycle": queue_snapshot["lifecycle"],
        }
    elif command == "tool-delegate-goal":
        for row in self._dispatch_queue:
            row["lifecycle"] = "delegated_goal"
        self._scheduler_state = prioritize_lane(
            self._scheduler_state,
            lane="sustained_goal",
        )
        self._scheduler_state["dispatch_handoff_lane"] = "sustained_goal"
        self._record_kernel_event(
            "tool_dispatch_goal_handoff",
            state="queued",
            message="tool dispatch queue handed to sustained goal lane",
        )
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        queue_snapshot = self._dispatch_queue_snapshot()
        output = "tool dispatch queue delegated to goal lane"
        details = {
            "subject": "tool",
            "action": "delegate-goal",
            "count": queue_snapshot["queue_depth"],
            "lane": "sustained_goal",
            "handoff": queue_snapshot["handoff"],
            "items": queue_snapshot["items"],
        }
    elif command == "tool-delegate-subagent":
        for row in self._dispatch_queue:
            row["lifecycle"] = "delegated_subagent"
        self._scheduler_state = prioritize_lane(
            self._scheduler_state,
            lane="subagent",
        )
        self._scheduler_state["dispatch_handoff_lane"] = "subagent"
        self._record_kernel_event(
            "tool_dispatch_subagent_handoff",
            state="queued",
            message="tool dispatch queue handed to subagent lane",
        )
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        queue_snapshot = self._dispatch_queue_snapshot()
        output = "tool dispatch queue delegated to subagent lane"
        details = {
            "subject": "tool",
            "action": "delegate-subagent",
            "count": queue_snapshot["queue_depth"],
            "lane": "subagent",
            "handoff": queue_snapshot["handoff"],
            "items": queue_snapshot["items"],
        }
    elif command == "tool-complete":
        completed = min(len(self._dispatch_queue), 1)
        if completed:
            self._dispatch_queue[0]["lifecycle"] = "completed"
        self._dispatch_queue = self._dispatch_queue[completed:]
        if not self._dispatch_queue:
            self._scheduler_state["dispatch_priority"] = False
            self._scheduler_state["dispatch_handoff_lane"] = None
        self._record_kernel_event(
            "tool_dispatch_completed",
            state="ok",
            message=f"completed {completed} queued tool dispatch(es)",
        )
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        queue_snapshot = self._dispatch_queue_snapshot()
        output = "tool dispatch marked completed"
        details = {
            "subject": "tool",
            "action": "complete",
            "completed": completed,
            "remaining": queue_snapshot["queue_depth"],
            "items": queue_snapshot["items"],
            "lifecycle": queue_snapshot["lifecycle"],
        }
    elif command == "tool-fail":
        failed = min(len(self._dispatch_queue), 1)
        if failed:
            self._dispatch_queue[0]["lifecycle"] = "failed"
        self._dispatch_queue = self._dispatch_queue[failed:]
        if not self._dispatch_queue:
            self._scheduler_state["dispatch_priority"] = False
            self._scheduler_state["dispatch_handoff_lane"] = None
        self._record_kernel_event(
            "tool_dispatch_failed",
            state="fault",
            message=f"failed {failed} queued tool dispatch(es)",
        )
        target_pane = "faults"
        state = self.runtime_control_snapshot()
        queue_snapshot = self._dispatch_queue_snapshot()
        output = "tool dispatch marked failed"
        details = {
            "subject": "tool",
            "action": "fail",
            "failed": failed,
            "remaining": queue_snapshot["queue_depth"],
            "items": queue_snapshot["items"],
            "lifecycle": queue_snapshot["lifecycle"],
        }
    elif command == "tool-status":
        queue_snapshot = self._dispatch_queue_snapshot()
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output = (
            f"tool orchestration queue={queue_snapshot['queue_depth']}"
            f" priority={queue_snapshot['priority']}"
            f" handoff={queue_snapshot['handoff']}"
        )
        details = {
            "subject": "tool",
            "action": "status",
            "queue_depth": queue_snapshot["queue_depth"],
            "priority": queue_snapshot["priority"],
            "handoff": queue_snapshot["handoff"],
            "items": queue_snapshot["items"],
            "lifecycle": queue_snapshot["lifecycle"],
            "roots": queue_snapshot["roots"],
        }
    elif command == "pause-runtime":
        state = self.pause_runtime(" ".join(args).strip() or None)
        target_pane = "runtime"
        output = "runtime paused"
        details = {"subject": "runtime", "action": "pause", "reason": " ".join(args).strip() or "operator-paused"}
    elif command == "resume-runtime":
        state = self.resume_runtime()
        target_pane = "runtime"
        output = "runtime resumed"
        details = {"subject": "runtime", "action": "resume"}
    elif command == "degrade-runtime":
        state = self.degrade_runtime(" ".join(args).strip() or None)
        target_pane = "runtime"
        output = "runtime degraded"
        details = {"subject": "runtime", "action": "degrade", "reason": " ".join(args).strip() or "fault-containment"}
    elif command == "runtime-status":
        gate = dict(self._runtime_control.get("execution_gate", {}))
        maintenance = dict(self._runtime_control.get("maintenance_mode", {}))
        active_adapter = str(self._runtime_control.get("active_adapter") or "unset")
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output = (
            f"runtime gate={gate.get('state') or 'unknown'}"
            f" reason={gate.get('reason') or 'none'}"
            f" adapter={active_adapter}"
            f" maintenance={'on' if maintenance.get('enabled') else 'off'}"
        )
        details = {
            "subject": "runtime",
            "action": "status",
            "gate": gate.get("state") or "unknown",
            "reason": gate.get("reason") or "none",
            "adapter": active_adapter,
            "maintenance": "on" if maintenance.get("enabled") else "off",
        }
    elif command == "runtime-gate":
        gate = dict(self._runtime_control.get("execution_gate", {}))
        maintenance = dict(self._runtime_control.get("maintenance_mode", {}))
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output = (
            f"runtime gate={gate.get('state') or 'unknown'}"
            f" maintenance={'on' if maintenance.get('enabled') else 'off'}"
        )
        details = {
            "subject": "runtime",
            "action": "gate",
            "gate": gate.get("state") or "unknown",
            "reason": gate.get("reason") or "none",
            "maintenance": "on" if maintenance.get("enabled") else "off",
            "maintenance_reason": maintenance.get("reason") or "none",
        }
    elif command == "runtime-health":
        active_adapter = str(self._runtime_control.get("active_adapter") or "unset")
        bridge = next(
            (row for row in self._runtime_bridges if str(row.get("adapter") or "") == active_adapter),
            None,
        )
        gate = dict(self._runtime_control.get("execution_gate", {}))
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output = (
            f"runtime health adapter={active_adapter}"
            f" bridge={bridge.get('health') if isinstance(bridge, dict) else 'unknown'}"
            f" gate={gate.get('state') or 'unknown'}"
        )
        details = {
            "subject": "runtime",
            "action": "health",
            "adapter": active_adapter,
            "bridge_health": bridge.get("health") if isinstance(bridge, dict) else "unknown",
            "bridge_status": bridge.get("status") if isinstance(bridge, dict) else "unknown",
            "gate": gate.get("state") or "unknown",
            "reason": gate.get("reason") or "none",
        }
    elif command == "runtime-orchestration":
        scheduler = self.scheduler_snapshot(session_metadata=self._active_session_metadata())
        lanes = self.execution_lanes(session_metadata=self._active_session_metadata())
        workers = self.worker_snapshot(session_metadata=self._active_session_metadata())
        dispatch_queue = next(
            (queue for queue in list(scheduler.get("queues", [])) if queue.get("id") == "tool_dispatch"),
            {},
        )
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output = (
            f"orchestration lane={scheduler.get('preferred_lane') or 'interactive'}"
            f" dispatch={dispatch_queue.get('state') or 'ready'}"
            f" depth={dispatch_queue.get('depth') or 0}"
            f" workers={len(workers)}"
        )
        details = {
            "subject": "runtime",
            "action": "orchestration",
            "preferred_lane": scheduler.get("preferred_lane") or "interactive",
            "dispatch_state": dispatch_queue.get("state") or "ready",
            "dispatch_depth": dispatch_queue.get("depth") or 0,
            "handoff": scheduler.get("dispatch_handoff_lane") or "none",
            "lanes": ", ".join(str(lane.get("id") or "lane") for lane in lanes) or "none",
            "workers": len(workers),
        }
    elif command == "runtime-queues":
        scheduler = self.scheduler_snapshot(session_metadata=self._active_session_metadata())
        queues = list(scheduler.get("queues", []))
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output = (
            f"runtime queues count={len(queues)}"
            f" foreground={next((q.get('depth') for q in queues if q.get('id') == 'foreground'), 0)}"
        )
        details = {
            "subject": "runtime",
            "action": "queues",
            "count": len(queues),
            "foreground_depth": next((q.get("depth") for q in queues if q.get("id") == "foreground"), 0),
            "goal_depth": next((q.get("depth") for q in queues if q.get("id") == "goal_background"), 0),
            "automation_depth": next((q.get("depth") for q in queues if q.get("id") == "automation"), 0),
        }
    elif command == "runtime-adapters":
        adapters = [str(row.get("name") or "unknown") for row in self._runtime_adapters]
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output = (
            f"runtime adapters count={len(adapters)}"
            f" active={self._runtime_control.get('active_adapter') or 'unset'}"
        )
        details = {
            "subject": "runtime",
            "action": "adapters",
            "count": len(adapters),
            "active": self._runtime_control.get("active_adapter") or "unset",
            "items": ", ".join(adapters) or "none",
        }
    elif command == "runtime-bridges":
        bridges = [str(row.get("adapter") or "unknown") for row in self._runtime_bridges]
        healthy = sum(1 for row in self._runtime_bridges if str(row.get("health") or "") == "ready")
        target_pane = "runtime"
        state = self.runtime_control_snapshot()
        output = f"runtime bridges count={len(bridges)} ready={healthy}"
        details = {
            "subject": "runtime",
            "action": "bridges",
            "count": len(bridges),
            "ready": healthy,
            "items": ", ".join(bridges) or "none",
        }
    elif command == "drain-background":
        state = self.drain_background()
        target_pane = "runtime"
        output = "background drain requested"
        details = {"subject": "runtime", "action": "drain-background"}
    elif command == "prioritize-goal-lane":
        state = self.prioritize_goal_lane()
        target_pane = "runtime"
        output = "goal lane prioritized"
        details = {"subject": "lane", "action": "prioritize-goal"}
    elif command == "enter-maintenance":
        state = self.enter_maintenance(" ".join(args).strip() or None)
        target_pane = "control_plane"
        output = "maintenance enabled"
        details = {"subject": "maintenance", "action": "enter", "reason": " ".join(args).strip() or "operator-maintenance-window"}
    elif command == "exit-maintenance":
        state = self.exit_maintenance()
        target_pane = "control_plane"
        output = "maintenance cleared"
        details = {"subject": "maintenance", "action": "exit"}
    else:
        raise ValueError(f"unknown operator command: {raw}")
    action_result = {
        "command": raw,
        "target_pane": target_pane,
        "ok": True,
        "status": details.get("status") or "ok",
        "code": details.get("code", 0),
        "subject": details.get("subject"),
        "action": details.get("action"),
        "output": output,
        "details": details,
    }
    return {
        "command": raw,
        "ok": True,
        "target_pane": target_pane,
        "output": output,
        "runtime_control": state,
        "details": details,
        "action_result": action_result,
    }
