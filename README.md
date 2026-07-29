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

### Mature Agent Traits

- **Plan-first by default** — turns are expected to decompose into explicit steps before execution, matching Codex-style operator workflow
- **Four-layer memory** — repository instructions, local/user overlays, indexed topic memory, and a knowledge graph work together instead of one flat history file
- **Knowledge graph assist** — sessions, files, modules, issues, decisions, and topics are linked so the agent can recover structure instead of only replaying text
- **Lightweight multi-subagent runtime** — subagents are scheduled like cheap shared-host threads, not heavyweight isolated workers
- **Host-aware scheduling** — concurrency, queue depth, and pressure adapt to available CPU and memory instead of assuming a dedicated machine
- **Operator-visible runtime state** — the GUI exposes memory layers, graph size, queue pressure, and runtime snapshots instead of hiding the kernel

### Current Productization Track

The current Mira track is Linux-style maturity without a full rewrite:

- **Micro-kernel path** — default boot stays focused on config, bus, session, provider, scheduler, auth, and minimal chat
- **Linux-style users** — `--user` isolates sessions/workspaces; `--group` shares project memory and policy
- **Lazy modules** — channels, MCP, document tools, desktop host, doctor repair, and memory consolidation load on demand
- **Policy table** — tool allow/deny, workspace root, memory scope, and execution posture are derived per user/group
- **Package discipline** — release artifacts are audited against a 119 MB budget before upload
- **Optional Rust boundaries** — `mira-launcher`, `mira-sandbox`, and `mira-pack` provide small native helpers without moving ownership of the Python kernel loop

### Native Rust Tools

The optional Rust boundary track is implemented in the `native/` workspace:

- `mira-launcher` — native entry point that locates Python/config/package roots and forwards to the Mira CLI with explicit errors
- `mira-sandbox` — app-layer execution helper that validates workspace paths, caps output, enforces timeouts, and returns structured JSON results
- `mira-pack` — release size auditor with JSON/table output, category totals, top offenders, and budget checks

This branch covers the acceptance scope for [#76](https://github.com/NSIETeam/Mira/issues/76), [#77](https://github.com/NSIETeam/Mira/issues/77), [#78](https://github.com/NSIETeam/Mira/issues/78), and [#79](https://github.com/NSIETeam/Mira/issues/79). GitHub still shows those issues open until the branch is merged and maintainers close them. Follow-up product-loop gaps remain tracked in [#99](https://github.com/NSIETeam/Mira/issues/99), including deeper desktop launcher wiring and release trust metadata.

Active follow-up work is tracked in [GitHub Issues](https://github.com/NSIETeam/Mira/issues), including release signing, Admin v2, and native Rust productization follow-ups.

The current Claude Code maturity gap closure is tracked in
[docs/cc-gap-closure.md](./docs/cc-gap-closure.md).

### Operational Commands

```bash
mira webui --user alice --group growth
mira doctor --profile lightweight
mira modules list
mira policy show --user alice --group growth
python scripts/package_size_report.py dist/Mira.app --budget-mb 119
cd native && cargo check --workspace && cargo test --workspace
cargo run --manifest-path native/Cargo.toml --bin mira-pack -- dist --format json --budget-mb 119
```

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
uv tool install mira-ai
```

**From PyPI:**

```bash
pip install mira-ai
```

**Desktop host (native window):**

```bash
pip install "mira-ai[desktop]"
mira desktop
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
mira desktop              # Native desktop shell around the local gateway
mira webui --background   # Keep running after closing terminal
mira agent                # Terminal-only chat
mira agent -m "Hello!"    # One-shot query
mira gateway              # Long-running service
```

Packaged desktop builds are published through GitHub Releases on version tags. The release workflow emits:

- `Mira.dmg`
- `Mira-Setup.exe`
- `Mira-linux.tar.gz`

Unsigned local macOS builds can still trigger Gatekeeper warnings. Public tag releases are intended to be signed and notarized when the required Apple and Windows signing secrets are configured in GitHub Actions.

### Architecture

Mira keeps the core small: channels and shells feed the same execution kernel, the LLM decides when tools are needed, and shell-specific behavior stays outside the runtime loop. The default workbench is intentionally engineering-heavy, but the kernel contract itself stays generic enough for future Rust/C-native host bridges, embedded control surfaces, and thinner custom shells.

The operator shell now exposes the same long-task lifecycle the kernel persists internally: sustained goals can be inspected, resumed, completed, or cancelled from the workbench, and root/user privilege workflow stays explicit through the same host contract.

Gateway startup now degrades into an unconfigured setup shell when no model API key is present, so the engineering workbench can still boot for inspection, shell control, and first-time configuration.

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

### 成熟 Agent 特性

- **默认先规划再执行** — 每次任务先拆步骤，再逐个攻克，工作流接近 Codex
- **四层记忆** — 仓库指令、用户/本地覆盖、主题索引记忆、知识图谱辅助记忆协同工作，而不是只堆一份历史
- **知识图谱辅助恢复上下文** — 会话、文件、模块、issue、决策、主题之间建立关系，恢复的是结构，不只是文本
- **超轻量多 Subagent** — 子 Agent 更像共享宿主资源的线程，而不是昂贵的独立进程
- **宿主感知调度** — 并发、排队深度、压力级别会根据 CPU 和内存自动调整，不假设机器独占
- **运行时状态可见** — GUI 直接暴露记忆层、图谱规模、队列压力和 runtime snapshot，而不是把内核藏起来

### 当前产品化改造主线

当前 Mira 的方向是“不全量重写”的 Linux-style 成熟化：

- **微内核启动路径** — 默认只保留 config、bus、session、provider、scheduler、auth 和最小聊天
- **Linux 用户模型** — `--user` 隔离 session/workspace，`--group` 共享项目 memory 和 policy
- **模块懒加载** — channel、MCP、文档工具、桌面壳、doctor repair、memory consolidation 按需加载
- **策略表权限** — 每个 user/group 派生工具 allow/deny、workspace root、memory scope 和执行姿态
- **包体纪律** — release 上传前按 119 MB 预算审计包体
- **可选 Rust 边界** — `mira-launcher`、`mira-sandbox`、`mira-pack` 提供小型 native helper，但 Python 仍然拥有内核主循环

### Native Rust 工具

可选 Rust 边界工具已经落在 `native/` workspace 中：

- `mira-launcher` — native 入口，定位 Python/config/package root，并把参数转发给 Mira CLI，失败时返回明确错误
- `mira-sandbox` — 应用层执行 helper，校验 workspace 路径，限制输出，执行 timeout，并返回结构化 JSON 结果
- `mira-pack` — release 包体审计工具，输出 JSON/table，统计分类、top offenders 和预算检查结果

当前分支覆盖 [#76](https://github.com/NSIETeam/Mira/issues/76)、[#77](https://github.com/NSIETeam/Mira/issues/77)、[#78](https://github.com/NSIETeam/Mira/issues/78)、[#79](https://github.com/NSIETeam/Mira/issues/79) 的 acceptance scope。GitHub 上这些 issue 在分支合并、维护者关闭之前仍会显示 open。后续产品闭环缺口继续由 [#99](https://github.com/NSIETeam/Mira/issues/99) 跟踪，包括更深入的桌面 launcher wiring 和 release trust metadata。

后续工作继续在 [GitHub Issues](https://github.com/NSIETeam/Mira/issues) 里跟踪，包括签名公证、Admin v2 和 native Rust 产品化 follow-up。

### 运维命令

```bash
mira webui --user alice --group growth
mira doctor --profile lightweight
mira modules list
mira policy show --user alice --group growth
python scripts/package_size_report.py dist/Mira.app --budget-mb 119
cd native && cargo check --workspace && cargo test --workspace
cargo run --manifest-path native/Cargo.toml --bin mira-pack -- dist --format json --budget-mb 119
```

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
uv tool install mira-ai
```

**从 PyPI 安装：**

```bash
pip install mira-ai
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

现在即使没有配置模型 API key，gateway 启动也会降级进入未配置 setup shell，不会直接退出；工程工作台仍可用于检查、控制台操作和首次配置。

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
