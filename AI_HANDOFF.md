# SceneFlow AI 接手摘要

更新时间：2026-07-06

## 2026-07-06 续接入口

- 本轮新增持续开发笔记：`task_plan.md`、`findings.md`、`progress.md`。
- 后续 AI 接手时先读：`AI_HANDOFF.md` → `RUNNING.md` → `findings.md`。
- 当前注意：`backend/sceneflow.db` 是本地 SQLite 数据且 git 已显示修改，除非用户明确要求，不要重置或覆盖。
- 当前测试面：未发现 test/spec 文件；优先跑后端 compileall、前端 lint/typecheck/build。
- 当前生成能力边界：图片生成仅支持 OpenAI；音频/视频生成仍是模拟进度和示例 URL。
- 智能问答已接入 assistant-ui 官方附件 primitives/adapters：前端可添加所有文件；图片走 image part，文本/代码文件直接读文本，PDF 通过 `pypdf` 后端解析，`.docx/.xlsx/.pptx` 通过后端 OpenXML 抽文本；解析不了的文件会生成明确的“无法解析该文件”说明。
- 智能问答前端流式状态已接入 Vercel AI SDK：`useChat` + `DefaultChatTransport` 负责发送、流式解析和进行中消息状态；Next BFF 将后端 FastAPI NDJSON 转成 AI SDK UI stream；Assistant UI 继续负责 composer/rendering。
- 聊天消息列表已补滚动体验：显示 scoped 滚动条，用户贴底时 SSE 输出自动跟随；用户向上滚动时停止跟随并显示向下箭头，点击后回到底部并恢复跟随。不要重新引入 `ResizeObserver` 做流式自动滚动，之前会造成明显抖动。

## 用户核心要求

- 前端智能问答 UI 参考 ChatGPT 网页版风格，明确使用 `@assistant-ui/react`，不要手搓成熟组件已有能力。
- 后端核心必须使用 LangChain 和 LangGraph；能用热门开源库就用，不要重复造轮子。
- 对话必须支持追问、上下文记忆，最大上下文按 1M token 预算处理，超过后摘要压缩。
- 需要 Agent Runtime，把执行事件实时推给前端，前端显示执行流程。
- 支持通义千问、豆包、DeepSeek、Claude Code、ChatGPT、Gemini、自定义中转站；选择供应商时自动填名称、Base URL、官方文档链接，API Key 和模型由用户填写。
- 所有项目/分镜相关增删改查必须存后端 SQLite，不存前端本地状态。

## 已完成改动

- 前端接入 `@assistant-ui/react`，新增 `frontend/src/components/chat/assistant-composer.tsx`，聊天输入区改为 Assistant UI Composer。
- 聊天界面改为更接近 ChatGPT 的布局；删除顶部 `WS: 未连接` 展示和残留文案。
- 修复 Select 展示不全：`frontend/src/components/ui/select.tsx` 增加 `min-w-0`、截断和宽度处理。
- 新增供应商默认配置：`frontend/src/lib/model-providers.ts`，设置页和后台官方配置页都会按供应商自动填默认名称、Base URL、文档链接。
- 后端模型调用恢复并扩展为 LangChain：
  - OpenAI 兼容供应商走 `ChatOpenAI`。
  - Claude/Anthropic 走 `ChatAnthropic`。
  - Gemini 走 OpenAI compatible endpoint。
- 新增 `backend/context_graph.py`：
  - 使用 LangGraph `StateGraph` 构建上下文加载/压缩流程。
  - 使用 `langgraph.runtime.Runtime` 和 `runtime.stream_writer` 发 Agent Runtime 事件。
  - 1M token 预算由 `MAX_CONTEXT_TOKENS = 1_000_000` 控制。
  - 超限时压缩旧消息，保留最近 20 条明细消息，摘要写入 `chat_sessions.context_summary`。
- 流式聊天接口现在实时推送：
  - `agent_step`: 加载历史上下文、压缩长期记忆、调用模型、保存回复、执行失败。
  - `reasoning_delta` / `content_delta`: 模型思考和正文增量。
- 前端新增执行流程展示：
  - `frontend/src/types/chat.ts` 增加 `ChatAgentStep`。
  - `use-chat-controller.ts` 通过 AI SDK transient `data-agent_step` 消费执行事件。
  - `chat-message-list.tsx` 显示“执行流程”。
- 前端聊天流式层改为 AI SDK：
  - `frontend/package.json` 增加 `@ai-sdk/react`、`ai`。
  - `frontend/src/app/api/bff/chat/sessions/[id]/messages/stream/route.ts` 将后端 NDJSON 翻译为 AI SDK UI stream/SSE chunks。
  - `frontend/src/actions/chat-actions.ts` 删除旧 `streamChatMessageAction` 手写 reader。
  - `frontend/src/components/chat/use-chat-controller.ts` 使用 `useChat` 和 `DefaultChatTransport`。
- 聊天滚动体验：
  - `frontend/src/app/globals.css` 增加 scoped `chat-message-list-scrollbar` 样式。
  - `frontend/src/components/chat/chat-message-list.tsx` 增加自动贴底、手动上滚停止跟随、浮动向下箭头。
- 项目 CRUD 已走后端 SQLite：
  - 后端：`backend/routers/projects.py`
  - 前端 BFF：`frontend/src/app/api/bff/projects/**`
  - 删除了前端模板路由 `frontend/src/app/api/bff/projects/templates/route.ts`。
- 根目录新增 `package.json`，提供前后端启动命令。
- 根目录新增 `RUNNING.md`，记录前后端本地运行方式。

## 关键依赖版本

后端依赖下限已抬到确认过的 PyPI 最新版本：

- `langgraph>=1.2.7`
- `langchain-core>=1.4.8`
- `langchain-openai>=1.3.3`
- `langchain-anthropic>=1.4.8`

前端新增：

- `@assistant-ui/react`
- `@ai-sdk/react`
- `ai`

后端新增：

- `pypdf`：用于 PDF 附件文本抽取。Office OpenXML 目前用 Python 标准库解析。

## 数据持久化约定

- SQLite 文件：`backend/sceneflow.db`
- 对话消息：`chat_messages`
- 对话摘要：`chat_sessions.context_summary`、`chat_sessions.context_summary_until`
- 项目：`projects`
- 分镜：`scenes`
- 前端 `localStorage` 仅保留登录态和用户偏好，不保存项目/分镜业务数据。

## 验证记录

早期基线曾跑通：

- `backend/.venv/bin/python -m compileall -q *.py routers`
- LangGraph Runtime 事件自检
- `frontend npm run lint`
- `frontend npx tsc --noEmit`
- `frontend npm run build`

本轮 AI SDK/滚动体验验证：

- `cd frontend && npm run lint`
- `cd frontend && npx tsc --noEmit`
- 注意：AI SDK 集成后曾尝试 `cd frontend && npm run build`，Next/Turbopack 停在 `Creating an optimized production build ...` 超过两分钟无新输出，已中断；不要把它记作通过。

注意：真实 LLM 调用仍需要用户配置有效 API Key 和模型名。

## 下次接手优先看

1. `backend/context_graph.py`：上下文记忆、压缩、Agent Runtime 事件。
2. `backend/routers/chat.py`：流式聊天事件如何输出到前端。
3. `backend/model.py`：LangChain 模型路由和供应商兼容。
4. `frontend/src/components/chat/use-chat-controller.ts`：前端如何消费流式事件。
5. `frontend/src/components/chat/chat-message-list.tsx`：执行流程 UI。
6. `frontend/src/lib/model-providers.ts`：供应商默认配置。
