This file provides guidance to AI coding agents working with this repository.

## Project Overview

Mira is a lightweight execution-kernel platform built from the original mira codebase, with a Python backend and React/TypeScript WebUI. It centers around a small agent loop that receives messages from chat channels, invokes an LLM provider, executes tools, and manages session memory.

## Development Commands

Current compatibility note: the product/workbench identity is `Mira`, while the
CLI/runtime layer keeps `mira` compatibility and now also exposes a `mira`
launcher alias.

```bash
# Python: run single test / lint
pytest tests/test_openai_api.py::test_function -v
ruff check mira/

# WebUI: dev server (proxies API/WS to gateway :8765), build, test
# Build outputs to ../mira/web/dist (bundled into the Python wheel)
cd webui && bun run dev      # or mira_API_URL=... bun run dev
cd webui && bun run build
cd webui && bun run test

# Gateway
mira gateway
```

## High-Level Architecture

### Core Data Flow

Messages flow through an async `MessageBus` (`mira/bus/queue.py`) that decouples chat channels from the agent core:

1. **Channels** (`mira/channels/`) receive messages from external platforms and publish `InboundMessage` events to the bus.
2. **`AgentLoop`** (`mira/agent/loop.py`) consumes inbound messages, builds context, and coordinates the turn.
3. **`AgentRunner`** (`mira/agent/runner.py`) handles the actual LLM conversation loop: send messages to the provider, receive tool calls, execute tools, and stream responses.
4. Responses are published as `OutboundMessage` events back to the appropriate channel.

### Key Subsystems

- **Agent Loop** (`mira/agent/loop.py`, `runner.py`): The core processing engine. `AgentLoop` manages session keys, hooks, and context building. `AgentRunner` executes the multi-turn LLM conversation with tool execution.
- **LLM Providers** (`mira/providers/`): Provider implementations (Anthropic, OpenAI-compatible, OpenAI Responses API, Azure, Bedrock, GitHub Copilot, OpenAI Codex, etc.) built on a common base (`base.py`). Includes image generation (`image_generation.py`) and audio transcription (`transcription.py`). `factory.py` and `registry.py` handle instantiation and model discovery.
- **Channels** (`mira/channels/`): Platform integrations (Telegram, Discord, Slack, Feishu, Matrix, WhatsApp, QQ, WeChat, WeCom, DingTalk, Email, MoChat, MS Teams, WebSocket, Mattermost). `manager.py` discovers and coordinates them. Channels are self-contained packages auto-discovered via `pkgutil` scanning.
- **Tools** (`mira/agent/tools/`): Agent capabilities exposed to the LLM: filesystem (read/write/edit/list), shell execution (with sandbox backends), web search/fetch, MCP servers, cron, notebook editing, subagent spawning, long-running tasks / sustained goals (`long_task.py`), image generation, and self-modification. Tools are auto-discovered via `pkgutil` scan + entry-point plugins.
- **Memory** (`mira/agent/memory.py`): Session history persistence with Dream two-phase memory consolidation. Uses atomic writes with fsync for durability.
- **Session Management** (`mira/session/`): Per-session history, context compaction, TTL-based auto-compaction (`manager.py`), and sustained goal state tracking (`goal_state.py`).
- **Config** (`mira/config/schema.py`, `loader.py`): Pydantic-based configuration loaded from `~/.mira/config.json`. Supports camelCase aliases for JSON compatibility.
- **WebUI** (`webui/`): Vite-based React SPA that talks to the gateway over a WebSocket multiplex protocol. The dev server proxies `/api`, `/webui`, `/auth`, and WebSocket traffic to the gateway.
- **API Server** (`mira/api/server.py`): OpenAI-compatible HTTP API (`/v1/chat/completions`, `/v1/models`) for programmatic access.
- **Command Router** (`mira/command/`): Slash command routing and built-in command handlers.
- **Heartbeat** (`mira/templates/HEARTBEAT.md`): Periodic task list checked via `cron` jobs (legacy dedicated service removed).
- **Pairing** (`mira/pairing/`): DM sender approval store with persistent pairing codes per channel.
- **Skills** (`mira/skills/`): Built-in skill definitions (cron, github, image-generation, etc.) loaded into agent context.
- **Security** (`mira/security/`): PTH file guard and other security measures activated at CLI entry.

### Entry Points

- **CLI**: `mira/cli/commands.py` (`mira` compatibility command plus `mira` launcher alias)
- **Python SDK**: `mira/mira.py`

## Project-Specific Notes

- Architecture constraints: [`.agent/design.md`](.agent/design.md)
- Security boundaries: [`.agent/security.md`](.agent/security.md)
- Common gotchas: [`.agent/gotchas.md`](.agent/gotchas.md)

## Contribution Flow

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for contribution flow and PR guidelines.

## Code Style

- Python 3.11+, asyncio throughout.
- Line length: 100.
- Linting: `ruff` with rules E, F, I, N, W (E501 ignored).
- pytest with `asyncio_mode = "auto"`.

## Common File Locations

- Config schema: `mira/config/schema.py`
- Provider base / new provider template: `mira/providers/base.py`
- Channel base / new channel template: `mira/channels/base.py`
- Tool registry: `mira/agent/tools/registry.py`
- WebUI dev proxy config: `webui/vite.config.ts`
- Tests mirror the `mira/` package structure.

## Kernel Host Contract

- The execution kernel should stay reusable and shell-agnostic. UI-specific behavior belongs in shell descriptors and host hooks, not in the agent loop or provider layer.
- Backend shell declarations live in `mira/kernel/shell.py`.
- Frontend shell contract types live in `webui/src/shells/types.ts`.
- WebUI transport payloads for shell descriptors live in `webui/src/lib/types.ts`.
- Shell registration and compatibility coercion live in `webui/src/shells/registry.ts`.
- Prefer grouped shell capabilities over flat booleans:
  - `chrome`: sidebar/search visibility
  - `surfaces`: utility/workspace/runtime-control surfaces
  - `actions`: execution-level actions such as fork
  - `composer`: composer availability and read-only posture
- Host orchestration should be implemented as hooks under `webui/src/shells/` and `webui/src/shells/engineering/`.
- New shells should primarily provide:
  - a descriptor from the kernel
  - a stable `mode`
  - a layout component
  - grouped host capabilities
