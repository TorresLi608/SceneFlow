# SceneFlow

<div align="center">

# 🎬 SceneFlow
### 全能型多模态 AI 短剧与动态漫创作生产工作台

<p align="center">
  <a href="README.md">English</a> · <b>简体中文</b>
</p>

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![React 19](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Tailwind CSS 4](https://img.shields.io/badge/Tailwind_CSS-v4-38B2AC?logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)

[架构设计文档](docs/architecture/overview.md) · [提交 Issue / 功能建议](https://github.com/TorresLi608/SceneFlow/issues) · [社区讨论](https://github.com/TorresLi608/SceneFlow/discussions)

</div>

---

## 📖 项目简介

**SceneFlow** 是一个专为 AI 短剧、动态漫与影视内容创作者打造的开源全流程生产工作台。它能够将剧本文本智能拆解为结构化镜头，围绕每个镜头生成高清分镜画面、运镜提示词与动态视频素材，并通过角色状态卡、道具设定、三视图参考图以及剧集基调图，深度保证跨镜头与跨剧集的视觉连续性与一致性。

系统采用现代化前后端分离架构：**Next.js 16** 前端（BFF 代理转发、响应式分镜工作台与 AI 创作助手）搭配 **FastAPI + SQLite** 后端（多模型路由编排、异步任务队列、带签名的私有媒体存储）。

> [!IMPORTANT]
> **SceneFlow 仍在持续高速迭代中。** AI 生成结果具有天然的不确定性，在公开发布或商业化使用前请进行人工审核，并确保你对所使用的剧本、人物肖像、声音与参考素材拥有合法权利。

---

## ✨ 核心能力

- 📝 **智能剧本拆镜**：将整集剧本精准拆解为叙事、对白、说话人、景别构图、画面提示、运镜轨迹、转场与时长等结构化镜头数据。
- 🎭 **连续性设定库**：通过角色卡、多形态状态卡、三视图设定图、道具绑定以及音色库，严格锁定跨集的人物样貌、服装与音色。
- 🎨 **两阶段分镜锚定**：首创两阶段渲染管线——先生成并确认整集「基调图（Tone Sheet）」锁定整体光影与画风，再携带基调图与上一镜头顺序渲染高清分镜。
- ⚡ **多模型自由路由**：项目级模型自由配置，按需混合搭配文本、图像、视频与音频模型（支持 OpenAI、Google Gemini、阿里通义/Wan、字节豆包 Seedance、DeepSeek、Anthropic 以及任意 OpenAI 兼容接口）。
- 💬 **AI 创作协作助手**：内置支持历史会话、上下文压缩、素材附件与流式响应的智能对话 Copilot。
- 🔒 **安全签名媒体分发**：生成媒体资产保存在受保护的本地目录，数据库只存相对路径，前端仅通过后端生成的防盗链限时 HMAC 签名链接访问。
- 🌐 **完备的中英双语**：全站 UI 原生内置中文与英文国际化支持。

---

## 🔄 生产工作流

```mermaid
flowchart LR
    A[📄 剧本输入] --> B[✂️ 智能拆镜]
    B --> C[👥 角色与道具设定]
    C --> D[🎨 剧集基调图锚定]
    D --> E[🖼️ 连续分镜渲染]
    E --> F[🎬 视频与运镜生成]
    F --> G[📦 成果导出与交付]
```

1. **项目与剧本创建**：建立短剧系列，导入分集剧本文本。
2. **模型与设定配置**：配置 AI 提供商模型密钥，创建角色三视图与音色参考。
3. **剧本拆解**：分离画面静态描述与动态运镜指令。
4. **基调图审核**：采样并审核全集视觉基调锚点。
5. **分镜与视频生成**：按上下文依赖关系批量或单镜头渲染分镜画面与动态视频。
6. **工作台微调与导出**：在可视化分镜工作台中调整、锁定、重生成并导出最终成片资产。

---

## 🏗️ 系统架构

```mermaid
flowchart LR
    subgraph Client [客户端浏览器]
        UI[Next.js 16 Web 工作台]
    end

    subgraph FrontendApp [前端服务层 :4000]
        BFF[BFF 接口代理 / Route Handlers]
    end

    subgraph BackendApp [后端服务层 :8080]
        FastAPI[FastAPI 业务路由与服务]
        Worker[进程内异步生成 Worker]
        DB[(SQLite 数据库)]
        Storage[私有生成媒体目录]
    end

    subgraph AIProviders [AI 模型服务商]
        LLM[OpenAI / Gemini / Claude / DeepSeek]
        MediaModels[通义万相 / 豆包视频 / 各类生成模型]
    end

    UI -->|HTTP / BFF| BFF
    UI -->|WebSocket 进度推送| FastAPI
    BFF -->|/api/bff/*| FastAPI
    FastAPI --> DB
    FastAPI --> Storage
    FastAPI --> Worker
    Worker --> AIProviders
```

- [架构概览](docs/architecture/overview.md)
- [模块边界说明](docs/architecture/boundaries.md)
- [端到端数据流](docs/architecture/data-flow.md)
- [本地开发指南](docs/reference/local-setup.md)

---

## 🛠️ 技术栈

| 层次 | 技术选型 |
|---|---|
| **前端** | Next.js 16、React 19、TypeScript、Tailwind CSS 4、React Query、Zustand、assistant-ui、AI SDK |
| **后端** | Python 3.11、FastAPI、Uvicorn、SQLModel、SQLAlchemy 2、Alembic |
| **AI 编排** | LangChain、LangGraph、多服务商动态模型路由 |
| **媒体与数据** | SQLite、Pillow、FFmpeg / FFprobe、HMAC 签名私有文件存储 |
| **容器化** | Docker、Docker Compose |

---

## 🚀 快速开始：Docker 部署

最省时省力的全功能本地体验方式。

### 环境要求

- **Git**
- **Docker Engine 或 Docker Desktop**（支持 Docker Compose v2）

### 一键构建与运行

```bash
# 1. 克隆代码仓库
git clone https://github.com/TorresLi608/SceneFlow.git
cd SceneFlow

# 2. 复制后端配置文件
cp backend/.env.example backend/.env

# 3. 启动容器服务
docker compose up -d --build
```

也可使用项目封装好的 pnpm 命令：

```bash
pnpm run docker:up       # 自动构建并在后台运行
pnpm run docker:backup   # 导出数据库与生成媒体备份快照
```

### 访问地址

| 服务 | 访问地址 | 说明 |
|---|---|---|
| **Web 创作工作台** | [http://127.0.0.1:4000](http://127.0.0.1:4000) | 前端界面 |
| **后端健康检查** | [http://127.0.0.1:8080/healthz](http://127.0.0.1:8080/healthz) | `{"status":"ok"}` |
| **OpenAPI 接口文档** | [http://127.0.0.1:8080/docs](http://127.0.0.1:8080/docs) | Swagger UI |

默认超级管理员账号（仅限开发环境）：
* **用户名**：`superAdmin`
* **密码**：`superAdmin@123`

---

## 💻 本地源码开发

### 环境要求

- **Python 3.11**
- **Node.js 22+** 与 **pnpm 10+**
- **FFmpeg 与 FFprobe**（已安装并配置进环境变量 PATH）
- **Git**

### 1. 克隆项目与安装依赖

```bash
git clone https://github.com/TorresLi608/SceneFlow.git
cd SceneFlow

# 安装后端虚拟环境 (.venv) 与 Python 依赖（全平台自适应）
pnpm run install:backend

# 安装前端 Node 依赖
pnpm run install:frontend
```

### 2. 准备环境变量

**macOS / Linux / Git Bash：**
```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

**Windows PowerShell：**
```powershell
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env.local
```

### 3. 启动开发服务

在终端 1 中启动后端：
```bash
pnpm run dev:backend
```

在终端 2 中启动前端：
```bash
pnpm run dev:frontend
```

在浏览器中打开 [http://localhost:4000](http://localhost:4000) 即可开始创作。

---

## ⚙️ 环境变量配置参考

### 后端配置（`backend/.env`）

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `PORT` | `8080` | 后端监听端口 |
| `SCENEFLOW_ENV` | `development` | 运行环境（`development` / `production`） |
| `SCENEFLOW_DB_PATH` | `./sceneflow.db` | SQLite 数据库文件路径 |
| `SCENEFLOW_PRIVATE_GENERATED_DIR` | `./private_generated` | 私有媒体文件存储目录 |
| `SCENEFLOW_PUBLIC_BASE_URL` | `http://127.0.0.1:8080` | 生成媒体签名链接时使用的后端公开地址 |
| `SCENEFLOW_JWT_SECRET` | *(开发默认值)* | JWT 签名密钥（生产环境必须替换） |
| `SCENEFLOW_AES_KEY` | *(开发默认值)* | 模型 API Key 加密主密钥（生产环境必须替换） |
| `SCENEFLOW_SUPER_ADMIN_PASSWORD` | `superAdmin@123` | 初始超级管理员密码 |
| `SCENEFLOW_CORS_ORIGINS` | `http://localhost:4000` | 允许跨域的前端 Origin 列表（逗号分隔） |
| `SCENEFLOW_MAX_CONTEXT_TOKENS` | `100000` | 聊天上下文最大 Token 上限 |
| `SCENEFLOW_LOG_LEVEL` | `INFO` | 日志输出级别 |

### 前端配置（`frontend/.env.local`）

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `BACKEND_API_BASE_URL` | `http://127.0.0.1:8080` | Next.js 服务端 BFF 代理目标地址 |
| `NEXT_PUBLIC_BFF_BASE_URL` | `""` | 浏览器客户端 BFF 基础地址（留空表示同源） |
| `NEXT_PUBLIC_WS_BASE_URL` | `ws://127.0.0.1:8080` | 浏览器 WebSocket 实时连接地址 |

---

## 🧪 测试与质量门禁

```bash
# 运行后端测试集
cd backend
sh scripts/run_tests.sh $(ls tests/test_*.py | xargs -n1 basename | sed 's/\.py$//')

# 运行前端类型检查与 Lint
cd ../frontend
pnpm exec tsc --noEmit
pnpm lint
node --no-warnings --experimental-strip-types --test src/lib/money.test.mts
```

---

## 📁 目录结构

```text
SceneFlow/
├── backend/                 # FastAPI 应用、SQLModel 数据模型、业务服务、迁移、测试
├── frontend/                # Next.js 16 页面、BFF 路由、状态仓库、UI 组件
├── docs/                    # 系统架构、功能设计、开发约定、项目计划与参考手册
├── scripts/                 # 跨平台开发启动与安装脚本（兼容 Mac / Windows / Linux）
├── docker-compose.yml       # 容器化部署编排配置
├── LICENSE                  # GNU AGPL v3 开源许可证
└── DISCLAIMER.md            # 中英文免责声明
```

---

## 🤝 参与贡献

热烈欢迎提交 Issue、功能建议与 Pull Request！

1. 开发前请查阅 [架构概览](docs/architecture/overview.md) 与 [工程约定规范](docs/conventions/README.md)。
2. 如涉及界面文本，请同步在 `frontend/src/lib/i18n.ts` 的中英文字典中增加词条。
3. 提交前确保通过后端测试与前端 `pnpm exec tsc --noEmit`。
4. 欢迎向 `main` 分支提交 PR。

---

## 📄 开源许可证与免责声明

- **开源协议**：SceneFlow 基于 [GNU Affero General Public License v3.0 or later](LICENSE)（`AGPL-3.0-or-later`）开源发布。
- **免责声明**：使用本项目即代表你已知悉并同意 [免责声明 DISCLAIMER.md](DISCLAIMER.md) 中的全部条款。

<div align="center">

**为全球 AI 短剧与动态视觉创作者用心打造 ❤️**

</div>
