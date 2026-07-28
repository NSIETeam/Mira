# Mira

<div align="center">

[![PyPI](https://img.shields.io/pypi/v/mira)](https://pypi.org/project/mira/)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.11-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)
[![Docs](https://img.shields.io/badge/docs-docs.mira.wiki-blue)](https://docs.mira.wiki)

</div>

[English](#english) | [中文](#chinese)

---

<a name="english"></a>
## English

**Mira** is a lightweight, self-hosted execution kernel for serious AI agents. It is built around a small reusable runtime, thin host shells, and a Codex-style engineering console for sessions, tools, runtime state, root/user posture, fault recovery, and native or embedded control from one workbench.

Today the default shell is no longer a demo chat page. It is an operator-facing agent workbench with kernel console, bridge telemetry, runtime controls, privilege posture, and recovery playbooks wired around the same small execution loop.

Mira is designed as execution infrastructure first, product shell second: the loop stays small, the control plane stays explicit, and the same kernel contract can back desktop operators, service hosts, and constrained device targets without collapsing into app-specific UI code.

### What is Mira?

- **Execution kernel** — reusable agent loop, tool runtime, memory, automations, and provider routing
- **Engineering shell** — browser workbench for sessions, runtime control, operator actions, and settings
- **Kernel console** — inspect runtime state, faults, bridges, modules, dispatch lanes, and operator commands
- **Privilege-aware runtime** — root/user shell posture, privileged controls, and recovery-oriented operations
- **Goal lifecycle control** — inspect, resume, complete, or cancel sustained objectives from the operator shell
- **Operator cockpit** — engineering-first GUI with visible shell control, execution stream, and status surfaces
- **Host boundary** — shell contracts keep GUI, channel, and product customization outside the core loop
- **Embedded posture** — runtime topology, board controls, and native module views keep the path open for MCU / device-host scenarios
- **Chat channels** — Telegram, Discord, Slack, WeChat, Feishu, Email, Mattermost, and more
- **Terminal** — interactive CLI agent and one-shot mode
- **Tools** — file system, shell, web search, web fetch, MCP, cron, image generation, sub-agents
- **Memory** — persistent session history and long-term context
- **Automations** — scheduled tasks and trigger-driven workflows
- **API & SDK** — OpenAI-compatible API and Python SDK for integrations
- **Deploy anywhere** — local desktop, Docker, or cloud (Render one-click)

### Quick Start

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

Opens `http://127.0.0.1:8765` in your browser. Configure your first model in **Settings -> Models**, then start your first execution.

```bash
mira webui --background   # Keep running after closing terminal
mira agent                # Terminal-only chat
mira agent -m "Hello!"    # One-shot query
mira gateway              # Long-running service
```

### Architecture

Mira keeps the core small: channels and shells feed the same execution kernel, the LLM decides when tools are needed, and shell-specific behavior stays outside the runtime loop. The default workbench is intentionally engineering-heavy, but the kernel contract itself stays generic enough for future Rust/C-native host bridges, embedded control surfaces, and thinner custom shells.

The operator shell now exposes the same long-task lifecycle the kernel persists internally: sustained goals can be inspected, resumed, completed, or cancelled from the workbench, and root/user privilege workflow stays explicit through the same host contract.

```
  Channels / Engineering Shell / Terminal / API
                    |
             Mira Execution Kernel
                    |
  Agent Loop | Tools | Memory | Skills | Automations | Runtime Control
                    |
        Shell Contracts | Operator Console | Provider Routing
```

### Documentation

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

### Contributing

PRs welcome. See [CONTRIBUTING.md](./CONTRIBUTING.md).

### Contact

Maintained by [Xubin Ren](https://github.com/re-bin) and open-source contributors.
Contact: [xubinrencs@gmail.com](mailto:xubinrencs@gmail.com)

### License

MIT — see [LICENSE](./LICENSE).

---

<a name="chinese"></a>
## 中文

**Mira** 是一个轻量级、可自托管的 AI Agent 通用执行内核。它围绕“小而稳”的运行时、薄外壳和接近 Codex 风格的工程控制台来构建，把会话、工具、运行时状态、root/user 权限姿态、故障恢复以及 native / 嵌入式控制统一进一个工作台。

现在默认壳层已经不是演示聊天页，而是一个面向操作者的 Agent 工作台：内核控制台、bridge 遥测、运行控制、权限姿态和恢复 playbook 都围绕同一套小内核接好。

Mira 优先被设计成执行基础设施，而不是某个单一产品：主循环保持精简，控制面保持显式，内核契约可以同时服务桌面操作者、服务宿主和受限设备目标，而不会把产品界面逻辑反灌回运行时核心。

### Mira 是什么？

- **执行内核** — 可复用的 Agent 循环、工具运行时、记忆、自动化和模型路由
- **工程外壳** — 面向工程场景的浏览器工作台，统一管理会话、运行控制和设置
- **内核控制台** — 查看运行时状态、故障、桥接器、模块、调度队列和操作命令
- **权限感知运行时** — 区分 root/user 壳层姿态，支持受限与特权恢复操作
- **目标生命周期控制** — 直接在 operator shell 中查看、恢复、完成或取消持续目标
- **操作者驾驶舱** — 工程优先 GUI，直接暴露 shell 控制、执行流和状态面板
- **宿主边界** — 用 shell contract 把 GUI、渠道接入和产品定制隔离在核心循环之外
- **嵌入式姿态** — 提供运行拓扑、板级控制和 native 模块视图，为 MCU / 设备宿主预留路径
- **聊天接入** — Telegram、Discord、Slack、微信、飞书、邮件、Mattermost 等
- **终端** — 交互式命令行 Agent 和单次查询模式
- **工具** — 文件系统、Shell、网页搜索、网页抓取、MCP、定时任务、图片生成、子 Agent
- **记忆** — 持久会话历史和长期上下文
- **自动化** — 定时任务和触发器驱动的工作流
- **API & SDK** — 兼容 OpenAI 的 API 和 Python SDK
- **随处部署** — 本地桌面、Docker 或云端（Render 一键部署）

### 快速开始

**一键安装（macOS / Linux）：**

```bash
curl -fsSL https://raw.githubusercontent.com/NSIETeam/Mira/main/scripts/install.sh | sh
```

**Windows PowerShell：**

```powershell
irm https://raw.githubusercontent.com/NSIETeam/Mira/main/scripts/install.ps1 | iex
```

**使用 uv：**

```bash
uv tool install mira
```

**从 PyPI 安装：**

```bash
pip install mira
```

**从源码安装：**

```bash
git clone https://github.com/NSIETeam/Mira.git
cd Mira
pip install .
```

环境要求：Python 3.11 以上，从源码构建 WebUI 需要 `bun` 或 `npm`。

### 启动

```bash
mira webui
```

浏览器自动打开 `http://127.0.0.1:8765`，在 **设置 -> 模型** 中配置第一个模型即可开始第一次执行。

```bash
mira webui --background   # 后台持续运行
mira agent                # 纯终端聊天
mira agent -m "你好!"      # 单次查询
mira gateway              # 长期运行的服务
```

### 架构

Mira 保持内核精简：聊天渠道和工程外壳都接入同一个执行内核，LLM 负责决策何时调用工具，而壳层特有行为不进入运行时主循环。默认工作台刻意偏工程化，但内核契约本身仍保持通用，后续可以继续接入 Rust/C 原生宿主桥接、更轻的嵌入式控制面和更薄的定制外壳。

现在 operator shell 已经把内核内部持久化的长任务生命周期直接暴露出来：持续目标可以在工作台内 inspect、resume、complete、cancel，root/user 权限工作流也通过同一份 host contract 保持显式一致。

```
  Channels / Engineering Shell / Terminal / API
                      |
               Mira Execution Kernel
                      |
 Agent Loop | 工具 | 记忆 | 技能 | 自动化 | Runtime Control
                      |
      Shell Contract | Operator Console | Provider Routing
```

### 文档

- [安装与快速开始](./docs/quick-start.md)
- [WebUI 指南](./docs/webui.md)
- [配置说明](./docs/configuration.md)
- [模型与供应商](./docs/providers.md)
- [聊天应用接入](./docs/chat-apps.md)
- [自动化任务](./docs/automations.md)
- [部署指南](./docs/deployment.md)
- [架构设计](./docs/architecture.md)
- [开发指南](./docs/development.md)
- [故障排查](./docs/troubleshooting.md)

### 贡献

欢迎 PR。详见 [CONTRIBUTING.md](./CONTRIBUTING.md)。

### 联系

由 [Xubin Ren](https://github.com/re-bin) 和开源贡献者共同维护。
联系邮箱：[xubinrencs@gmail.com](mailto:xubinrencs@gmail.com)

### 许可证

MIT — 详见 [LICENSE](./LICENSE)。
