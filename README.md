# Mira

<div align="center">

[![PyPI](https://img.shields.io/pypi/v/mira)](https://pypi.org/project/mira/)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.11-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)
[![Docs](https://img.shields.io/badge/docs-docs.mira.wiki-blue)](https://docs.mira.wiki)

</div>

**Mira** is a lightweight, self-hosted AI agent execution kernel. Run a personal AI assistant that connects to your chat apps, uses tools, maintains memory, and automates tasks — all under your control.

## What is Mira?

- **Web UI** — full browser-based workbench with topics, tools, and settings
- **Chat channels** — Telegram, Discord, Slack, WeChat, Feishu, Email, Mattermost, and more
- **Terminal** — interactive CLI agent and one-shot mode
- **Tools** — file system, shell, web search, web fetch, MCP, cron, image generation, sub-agents
- **Memory** — persistent session history and long-term context
- **Automations** — scheduled tasks and trigger-driven workflows
- **API & SDK** — OpenAI-compatible API and Python SDK for integrations
- **Deploy anywhere** — local desktop, Docker, or cloud (Render one-click)

## Quick Start

### Install

**One command (macOS / Linux):**

```bash
curl -fsSL https://raw.githubusercontent.com/NSIETeam/Mira/main/scripts/install.sh | sh
```

**Windows PowerShell:**

```powershell
irm https://raw.githubusercontent.com/NSIETeam/Mira/main/scripts/install.ps1 | iex
```

**With uv:**

```bash
uv tool install mira
```

**From PyPI:**

```bash
pip install mira
```

**From source:**

```bash
git clone https://github.com/NSIETeam/Mira.git
cd Mira
pip install .
```

Prerequisites: Python 3.11+, and optionally `bun`/`npm` for building the WebUI from source.

### Launch

```bash
mira webui
```

Opens `http://127.0.0.1:8765` in your browser. Configure your first model in **Settings -> Models**, then start chatting.

### Other entry points

```bash
# Keep running after closing the terminal
mira webui --background

# Terminal-only chat
mira agent

# One-shot query
mira agent -m "Hello!"

# Long-running gateway service
mira gateway
```

## Architecture

Mira keeps the core small: messages arrive from chat channels, the LLM decides when tools are needed, and memory or skills are loaded on demand. Everything extends from this minimal loop without becoming a monolith.

```
  Telegram / Discord / WeChat / Slack / WebUI / API
                    |
            Mira Agent Loop
                    |
    LLM Routing | Tools | Memory | Skills | Automations
```

## Project Status

Mira is under active development. See [GitHub Releases](https://github.com/NSIETeam/Mira/releases) for the latest.

Current focus areas:
- Multi-modal support (images, voice, video)
- Improved long-term memory
- Multi-step reasoning and planning
- More integrations (calendar, etc.)

## Documentation

- [Install & Quick Start](./docs/quick-start.md)
- [WebUI Guide](./docs/webui.md)
- [Configuration](./docs/configuration.md)
- [Providers & Models](./docs/providers.md)
- [Chat Apps](./docs/chat-apps.md)
- [Automations](./docs/automations.md)
- [Deployment](./docs/deployment.md)
- [Architecture](./docs/architecture.md)
- [Development](./docs/development.md)
- [Troubleshooting](./docs/troubleshooting.md)
- [Full docs index](./docs/README.md)

## Contributing

PRs welcome. See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

## Contact

Maintained by [Xubin Ren](https://github.com/re-bin) and open-source contributors.
Contact: [xubinrencs@gmail.com](mailto:xubinrencs@gmail.com)

## License

MIT — see [LICENSE](./LICENSE).
