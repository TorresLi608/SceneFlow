# SceneFlow AI 接手摘要

更新时间：2026-07-02

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
  - `use-chat-controller.ts` 消费 `agent_step`。
  - `chat-message-list.tsx` 显示“执行流程”。
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

## 数据持久化约定

- SQLite 文件：`backend/sceneflow.db`
- 对话消息：`chat_messages`
- 对话摘要：`chat_sessions.context_summary`、`chat_sessions.context_summary_until`
- 项目：`projects`
- 分镜：`scenes`
- 前端 `localStorage` 仅保留登录态和用户偏好，不保存项目/分镜业务数据。

## 验证记录

已跑通：

- `backend/.venv/bin/python -m compileall -q *.py routers`
- LangGraph Runtime 事件自检
- `frontend npm run lint`
- `frontend npx tsc --noEmit`
- `frontend npm run build`

注意：真实 LLM 调用仍需要用户配置有效 API Key 和模型名。

## 下次接手优先看

1. `backend/context_graph.py`：上下文记忆、压缩、Agent Runtime 事件。
2. `backend/routers/chat.py`：流式聊天事件如何输出到前端。
3. `backend/model.py`：LangChain 模型路由和供应商兼容。
4. `frontend/src/components/chat/use-chat-controller.ts`：前端如何消费流式事件。
5. `frontend/src/components/chat/chat-message-list.tsx`：执行流程 UI。
6. `frontend/src/lib/model-providers.ts`：供应商默认配置。
