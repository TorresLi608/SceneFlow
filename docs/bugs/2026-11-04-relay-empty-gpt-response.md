# BUG-20261104-relay-empty-gpt-response：GPT 中转返回成功状态但正文为空

- 首次记录：2026-11-04
- 最近更新：2026-11-04
- 状态：实网确认中转响应为空；应用未修改，中转内部原因待提供方排查
- 检索词：gpt-6.1-sol-g、gpt-6.1-sol、gpt-5.6-sol、empty final content from agent、CHAT_STREAM_FAILED、Responses、completion_tokens、estimated

## 现象与复现

用户反馈选择“官方 · gpt-6.1-sol-g”聊天必现 `failed to chat: empty final content from agent`，但中转站显示模型调用成功。

只读核对本地配置：显示名称为 `gpt-6.1-sol-g`，实际 model ID 为 `gpt-6.1-sol`，provider 为 `openai`，base URL 为 `https://ai.xmiaom.com/v1`。这里的“官方”表示应用管理员提供的公共配置（`source=official`），不表示请求直达 OpenAI。中转 `/models` 列表包含实际请求的 `gpt-6.1-sol`。

使用该配置的密钥在进程内构造最小合成请求，绕过浏览器、Next BFF、LangChain agent 和聊天持久化接口，直接访问同一中转：

| 对照 | 参数与事件 | 实际结果 |
|---|---|---|
| Chat Completions SSE | 无 tools；`temperature=0.3`、`max_completion_tokens=4096`、`stream_options.include_usage=true`，与应用纯文本补救参数一致 | HTTP 200，`text/event-stream`；3 个 JSON chunk 后 `[DONE]`；`delta.content` 累计 0 字符；`finish_reason=stop` |
| Responses SSE | 无 tools、无 temperature；`max_output_tokens=4096` | HTTP 200；包含 `response.output_text.done` 和 `response.completed`，无 `response.output_text.delta`；结束响应的 `output_text` 长度为 0；状态 `completed` |

两次请求都指定 `gpt-6.1-sol`，响应 `model` 却为 `gpt-5.6-sol`；两者用量均为输入 6、输出 0、合计 6，并标记 `estimated=true`。这是响应元数据中的差异，不能据此证明中转内部实际执行了哪款模型。

## 根因与定位

- **已确认的故障边界：中转返回的原始协议就没有正文。** Chat Completions 没有可被解析器漏读的正文或 reasoning 字段；Responses 的最终正文也为空。该现象不依赖 React Activity、assistant-ui、前端切页或 agent 工具。
- `backend/app/services/agent_service.py::stream_chat_agent` 在无工具空回复时还会执行一次纯文本补救；若补救仍没有正文，则抛出 `ValueError("empty final content from agent")`。`api/v1/chat.py` 将异常转换成界面所见的流错误。应用没有把空响应当成有效回答保存，也不能用历史回答填补本轮缺失的正文。
- HTTP 200、`stop` / `completed` 只表示中转结束了响应；不能证明它返回了有效答案。中转仪表盘的“成功”与应用拒绝空正文可以同时发生。
- **尚未确认的内部根因：**模型别名/渠道映射、上游模型输出及中转协议转换均需提供方排查。响应模型名不一致和估算用量是排查线索，不能单独证明某一种内部错误。

## 处理与影响

本次仅记录诊断，没有修改模型配置、应用代码、真实聊天历史或计费记录，没有重启应用。切换 Responses 的单独对照同样为空，故没有加入按模型名强制切换接口或更多自动重试的补丁；这些操作没有已验证的修复效果。

提供方应核对 `gpt-6.1-sol` 的渠道映射，以及为何两个接口在输出 0 token 时仍报告成功。恢复后需要重新验证原始协议正文及实际应用聊天；当前未解决中转输出缺失。

长期流程与用量规则见 [聊天设计](../design/feature-chat.md)。历史的回答选择/补救问题见 [问答误用旧内容与正文缺失](2026-09-21-chat-repeat-previous-answer.md)，本次与该应用侧选择错误的根因不同。

## 验证

2026-11-04 本地临时诊断脚本使用项目现有 Python 环境、httpx 和 LangChain SDK；配置通过 SQLite `mode=ro` 读取，导入应用模块前设置临时 `DATABASE_URL` 和 `SCENEFLOW_PRIVATE_GENERATED_DIR`。只打印状态、字段名、字符计数、结束原因和用量，未输出密钥或真实用户内容。

本轮执行 1 次只读模型列表请求和 4 次最小生成探测：第一次 Chat Completions 流在收到响应头前 90 秒超时；非流式 SDK 对照收到 HTTP 400（没有保留具体原因，不能归因为某项参数）；随后原始 Chat Completions SSE 和 Responses SSE 均得到上表中的空成功响应。没有进行真实聊天接口端到端测试，未向真实会话写入测试消息。超时请求是否在中转内部继续执行/计费无法确认。

仓库只修改文档；交付前执行 `git diff --check` 及新增文档相对链接检查。未运行代码测试，未将历史测试结果作为本次验证。

## 历史与关联

- 2026-11-04：根据用户授权进行实网最小对照，确认空正文已存在于中转原始响应；未确认中转内部根因，未宣称修复。
