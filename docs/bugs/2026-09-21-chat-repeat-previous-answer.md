# BUG-20260921-chat-repeat-previous-answer：连续多轮对话重复回复上一轮内容

- 首次记录：2026-09-21
- 最近更新：2026-09-21
- 状态：已修复，单测回归与端到端复现通过
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
