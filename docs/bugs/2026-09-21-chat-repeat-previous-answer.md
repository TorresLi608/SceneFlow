# BUG-20260921-chat-repeat-previous-answer：问答结束时误用旧回复或工具前过程说明

- 首次记录：2026-09-21
- 最近更新：2026-10-22
- 状态：历史多轮问题已修复；2026-10-22 工具后正文缺失已修复，模拟中转回归通过，真实中转站待验证
- 检索词：智能问答、多轮对话、重复回复、一模一样、_final_answer、base_count、stream_chat_agent、agent_complete、persist_assistant_message、chat_messages

## 现象与复现

### 影响页面与接口
- 影响界面：工作台智能问答页面 `/chat?chat={session_id}`
- 影响接口：`POST /api/chat/sessions/{session_id}/messages/stream`

### 触发条件与表现
1. 在已有至少两轮有效问答（例如先问天气，再问详细旅游穿衣指南）的会话中；
2. 用户发送无需调用工具的简短夸赞或闲聊（例如“牛逼”）；
3. 后台大模型（在某些 OpenAI 兼容中转服务上绑定 tools 时）未触发 tool calls 且在 SSE 流式模式下返回了空内容（`finish_reason="stop"`, `content=""`）；
4. 后台 `_final_answer` 在本轮 AIMessage 为空时，错误倒序遍历包含了全部历史消息的列表，越界找到了上一轮关于旅游穿衣指南的 AIMessage 并作为本轮最终回答返回；
5. `chat.py` 流式接口在 `agent_complete` 事件中接收到该内容后，持久化落库并向前端推送，导致助手回复的内容与上一轮完全一模一样；
6. 接着用户追问“为啥不回答我的夸你‘牛逼’”，同样的过程再次发生，又一次复制并回复了穿衣指南。

## 根因与定位

1. **`_final_answer` 与 `_tool_messages` 缺少切片隔离（核心代码漏洞）**：
   - 入口位于 `backend/app/services/agent_service.py` 中的 `_final_answer`：
     ```python
     def _final_answer(output: Any) -> str:
         messages = output.get("messages", []) if isinstance(output, dict) else []
         for message in reversed(messages):
             if isinstance(message, AIMessage):
                 content = _content_text(message.content).strip()
                 if content:
                     return content
         return ""
     ```
   - LangGraph 图运行结束后，`output["messages"]` 包含传入图的所有历史消息加上本轮新产生的消息。
   - 当本轮新产生的 AIMessage 其 `content` 为空（或报错中断）时，`reversed(messages)` 越界搜寻到了历史消息中的旧 AIMessage，把过去的旧回复当作本轮的新输出。
2. **`stream_chat_agent` 在接收空流时未识别为无内容**：
   - 因为 `_final_answer` 伪造了非空的上一轮回答，导致路由层的防空检查 `if not answer.strip(): raise ValueError(...)` 失效。
   - 随后 `persist_assistant_message()` 把上一轮内容当做对新问题的回复写入数据库。
3. **部分中转渠道模型在 `tools` + `stream` 下闲聊返回空流**：
   - 某些中转平台在配置了 tools 但当前提问不需调用工具时，其 SSE 流式解析层可能丢弃 `content` chunk，造成流式输出全空。

## 修复与影响

1. **切片隔离历史消息**：
   - 在 `run_chat_agent` 和 `stream_chat_agent` 中记录输入消息的基础长度 `base_count = len(_lc_messages(messages))`。
   - `_final_answer` 和 `_tool_messages` 只在 `messages[base_count:]` 切片内检索，彻底杜绝越界窃取历史消息。
2. **空流自动容错降级**：
   - 在 `stream_chat_agent` 中，若本轮未触发任何工具调用且流式与最终答案均为空，自动使用非 tool 绑定的原生模型进行流式补救，保障闲聊和反馈等常规对话 100% 顺畅应答。
3. **严格防空与日志告警**：
   - 若模型调用彻底失败，正规抛出异常，不再静默复制旧内容落库。

## 验证

1. 针对原问题会话 `chat_aa3cc985cbebde56` 提取包含“牛逼”的消息历史，执行 `stream_chat_agent` 复现测试，验证修复后不再返回上一轮的穿衣指南，而是生成与“牛逼”匹配的亲切回应。
2. 单元测试回归：运行 `backend/tests/test_agent_service.py` 验证工具循环、图片工具、多轮回答完整性全部通过。
3. 前端类型检查与 Lint 验证通过。

## 历史与关联

- 2026-09-21：首次排查并修复会话 `chat_aa3cc985cbebde56` 出现的连续重复回复问题。


## 2026-10-22 复发：工具后仅返回思考，过程说明被当作最终答案

### 现象与证据

用户反馈中转 `claude-sonnet-5.5` 搜索科技新闻后停止，界面只留有继续读取页面的过程说明；思考片段显示正在准备摘要。没有取得生产请求 ID 或原始协议，不能断言该中转站具体的停止原因。

使用真实 `create_agent` 和模拟流复现：第一条 AIMessage 包含过程说明和网页工具调用，工具返回资料，最后一条 AIMessage 只有 thinking、没有正文。修复前确实返回了第一条过程说明。

### 确认根因

- 上次修复只限制了 `messages[base_count:]`，但 `_final_answer` 仍会跳过本轮最后的空响应，倒序找到工具调用前的文字；同一类回退选择错误仍可在本轮内发生。
- `stream_chat_agent` 又把累计 `streamed_content` 当作答案，且旧补救条件要求完全没有工具调用、没有累计文字。只要前面出现过程说明，工具后的空正文就不会补救。
- 工具预算只在重复/超限/连续失败时强制收尾；正常工具成功后的空正文尚未触发这些条件。

### 本次修复

- `_final_answer` 只读取本轮最后一条 AIMessage；空正文、有效/无效工具调用都不能回退为更早的过程说明。两个问答入口及共享产物拼接调用方使用相同规则。
- `ChatToolBudget.awrap_model_call` 在工具调用后的最终响应无正文、无新工具调用时，保留相同消息/工具资料并禁用新工具，最多补救一次。补救指令要求直接输出最终答案，不能只思考或承诺继续。
- 上游明确标记 `max_tokens`/`length` 截断且尚无正文时，仅将这一次补救的输出额度翻倍，最高 8192（当前常规问答为 4096）；未报告截断时保持原额度。
- 补救仍无正文或仍请求工具时，返回明确的正文缺失提示，不重跑工具、不形成循环。正常回答不多调用模型，原有六轮/八次工具预算不变。
- 补救仍在原有用量回调范围内，原空响应和补救调用均计量；日志只记录计数/决策，不写正文、工具参数或密钥。
- 流式入口不再使用累计过程说明兜底；无工具空回复保留原有纯文本补救，但结果单独判断是否为空。
- 另外修复最终正文只存在于结束事件时的增量遗漏，见 [独立流式记录](2026-10-22-chat-final-text-stream.md)。

### 本次验证与限制

新增 `test_chat_final_answer.py`，覆盖流式/非流式工具后仅思考、证据保留、禁止重跑工具、三次模型调用用量合并、补救仍为空时有界提示、末尾空响应不回退过程说明。另以 HTTP MockTransport 驱动真实 Anthropic SDK 的原生 SSE 协议（先 text/tool_use、再 thinking-only、最后 text），验证实际恢复请求无 tools、保留 tool_result、确认 max_tokens 截断后额度由 4096 提至 8192、最终正文进入增量与完成事件。

本次实际命令：

```bash
cd backend
check_dir=$(mktemp -d /private/tmp/sceneflow-chat-final.XXXXXX)
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh test_chat_final_answer test_agent_service test_chat_agent_budget test_anthropic_usage test_chat_model_temperature test_chat_error_logs test_chat_balance test_usage_service
```

八组 PASS。前端 `pnpm exec tsc --noEmit`、`pnpm lint` 以及聊天 `chat-message-state.test.mts`（1 项）通过。测试使用临时数据库与媒体目录。

未调用真实中转站或付费模型，未做本次浏览器端到端验证。该机制处理空最终正文；若上游把一段过程说明直接作为有正文的最终响应，不能仅凭自然语言可靠判断是否答完。补救是额外一次可能计费的模型请求，仍可能遇到提供方错误/超时；不扩大工具预算或无限重试。上文历史“100% 顺畅应答”的描述不能作为此类异常的保证。
