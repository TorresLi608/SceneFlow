# BUG-20260918-chat-image-tool-result-display：智能问答生成图片只在执行流程里显示链接

- 首次记录：2026-09-18
- 最近更新：2026-09-18
- 状态：已修改待浏览器验证
- 检索词：智能问答、生成图片、generate_image、执行流程、agent_step、artifact、Markdown 图片、工具失败、ToolException、handle_tool_error、Streamdown img

## 现象与复现

页面 `/chat`。让助手生成一张图片后：

- 「执行流程」面板里「生成图片」步骤的 detail 显示的是工具返回的 JSON 文本（含签名 URL），对话正文里没有图片。
- 只有模型自觉把工具返回的 `![标题](url)` 抄进最终回复时才会出现图片；模型只回一句“图片已生成”时用户什么都看不到。
- 图片模型未配置、余额不足、供应商报错时，「生成图片」步骤仍显示为 done（detail 是英文错误串），正文里没有任何失败提示；模型回复为空时整轮以 `empty content from agent` 失败。

最小复现：不启用图片模型，发送“画一只猫”，观察执行流程和正文。

## 根因与定位

1. `backend/app/services/agent_service.py`
   - `on_tool_end` 的 detail 直接取工具输出前 160 字符，即 `tool_result` 的 JSON，所以链接只出现在流程框。
   - 工具设置了 `handle_tool_error = True`，LangChain 会把 `ToolException` 变成 `status="error"` 的 `ToolMessage`，只触发 `on_tool_end`，不会触发 `on_tool_error`。原有 error 分支实际上不会执行，失败步骤显示为 done。
   - `_artifact_markdowns` 只补齐成功产物的 Markdown，失败没有任何回填；正文是否包含图片完全依赖模型是否遵守系统提示。
2. `frontend/src/app/(workspace)/chat/_components/chat-message-list.tsx`
   - Streamdown 默认 `img` 渲染器能显示图片，但加载失败时只显示一行灰色斜体“图片不可用”，没有链接和明确提示。
3. 执行流程是 transient 事件（见 [chat design](../design/feature-chat.md)），不会持久化；历史会话只能依赖正文内容。

## 修复与影响

- `agent_service.py`
  - 新增 `_tool_status` / `_tool_payload` / `_tool_output_detail` / `_failure_reason` / `_failure_notice`：`on_tool_end` 按 `ToolMessage.status` 区分成功与失败；成功时 detail 显示产物文件名（不再泄露签名 URL），失败时 status 为 `error` 并显示原因。
  - `_missing_tool_outcomes` 汇总成功产物 Markdown 和失败提示（`> ⚠️ 图片生成失败：原因`），凡正文没有的都以 `content_delta` 追加并写入持久化回复。模型回复为空时也不再因 `empty content` 失败。
  - 工具输出改为从 `on_tool_end` 事件收集（`tool_outputs`），不再只依赖根 `on_chain_end`；`run_chat_agent`（非流式端点）同样受益。
  - 图片工具的前置校验和余额门禁错误改为中文提示；`HTTPException` 只取 `detail`。
  - 系统提示增加“工具失败不要重复重试，简要告知用户”。
- `chat-message-list.tsx`：为 Streamdown 传入自定义 `img` 组件，图片以内联卡片显示、点击新窗口打开；加载失败显示带链接的提示（`chat.imageLoadFailed` / `chat.openImage`，`i18n.ts` 中英文均已添加）。
- 限制：图片是否能显示仍取决于 `SCENEFLOW_PUBLIC_BASE_URL` 能被浏览器访问（签名链接直连后端）。失败提示依赖工具抛出的 `ToolException` 文本，供应商原始报错未做翻译，只截断到 200 字符。

## 验证

- `cd backend && SCENEFLOW_PRIVATE_GENERATED_DIR=$(mktemp -d)/media sh scripts/run_tests.sh test_agent_service test_artifact_service test_chat_balance`：2026-09-18 通过。新增三个用例覆盖成功产物回填、流程 detail 不含 URL、失败步骤标记与失败提示回填、模型空回复仍有内容。
- `cd frontend && pnpm exec tsc --noEmit`：2026-09-18 通过。
- `pnpm lint`：2026-09-18 通过（0 error；随后消除了本次引入的一个未使用变量 warning，该修改后未能重跑 lint/tsc）。
- 前端单测（`node --test src/lib/*.test.mts …`）：2026-09-18 因执行环境限流未能运行。
- 浏览器实测（真实图片模型成功/失败两种路径）：未执行。
