# BUG-20261016-chat-fallback-usage-unmetered：智能问答纯文本补救流未计量，有输出但输入/输出/花费为 0

- 首次记录：2026-10-16
- 最近更新：2026-10-16
- 状态：已修改待验证（后端自检尚未执行，原因见「验证」）
- 检索词：智能问答、输入 0、输出 0、花费为 0、token 为 0、有回复却计费为 0、纯文本补救、fallback to plain chat model stream、usage_metadata、agent_complete、record_usage、Claude、claude-sonnet、中转平台

## 现象与复现

### 影响页面与接口
- 影响界面：工作台智能问答 `/chat` 的使用记录页，以及管理后台用量页（二者都读 `usage_logs` 的 `input_tokens` / `output_tokens` / `cost_micros`；接口 `GET /api/usage/logs`、`GET /api/admin/usage-logs`）。
- 影响接口：`POST /api/chat/sessions/{session_id}/messages/stream`（前端智能问答实际使用的流式入口；非流式 `POST .../messages` 同样受影响面见「修复与影响」）。

### 触发条件与表现
1. 用户以官方 Claude（`claude-sonnet-5.5`）进行智能问答。对话有完整回复正文，但用量记录里「输入」「输出」均为 0、花费 $0.000000；同一时间段的 `gpt-6.1-sol` 记录（5297 输入 / 26 输出 / $0.532300）正常。用户 2026-10-16 截图共 5 条 Claude 记录（用时 25.7s ~ 158.7s）全部为 0。
2. 源码核对的触发前提：当聊天端点（常见于中转平台）在「配置了 tools 的 agent 流」上丢弃正文、返回空流时，`stream_chat_agent` 会走**纯文本补救流**重新生成回复；用户看到的正文来自补救流。补救流此前完全未被计量（根因 1）。
3. 另一条独立前提：该轮被丢弃的调用本身是否回报 usage 取决于上游平台；若它也没回报，而补救流的 usage 又被丢弃（根因 1 修复前的必然结果），整轮即全 0。

> 本机 `data/app.db` 中这些具体记录是否命中「补救流」路径，未能在本次排查中直接读取确认（见「验证」）；两条路径分别为「本应用丢失用量」（本次修复）与「上游不返回 usage」（本应用无法计算，现改为留 warning 日志）。

## 根因与定位

1. **补救流在用量回调作用域之外**（`app/services/agent_service.py::stream_chat_agent`，修复前约 544-573 行的纯文本补救分支）：agent 级 `get_usage_metadata_callback()` 的 `with` 只包住 `agent.astream_events(...)`；补救分支的 `plain_model.astream(base_messages)` 在其外部执行，且不累积任何 chunk 的 `usage_metadata`。补救流是一次真实的计费调用，其用量被整体丢弃。
2. **`agent_complete` 只携带 agent 回调的聚合值**（修复前约 589-594 行）：`usage = aggregate_token_usage(usage_callback.usage_metadata)`（及 final_output 消息回退）。补救场景下 agent 侧通常一无所获，最终 `usage` 全 0。
3. **落库**：`app/api/v1/chat.py::stream_message` 的 `persist_assistant_message` 用该 `usage` 调 `record_usage`，于是写入 `input_tokens=0, output_tokens=0, cost_micros=0` 的日志行——对用户即「明明有输出，输入/输出/花费都是 0」。
4. 历史关联：修复 [BUG-20260921-chat-stream-busy-timeout-lag](2026-09-21-chat-stream-busy-timeout-lag.md)（SQLite 写锁吞掉计费日志）时恢复了常规路径的计费，但未覆盖本补救流路径。

## 修复与影响

改动文件：`backend/app/services/agent_service.py`、`backend/tests/test_agent_service.py`。

1. **补救流独立计量**：补救流包进独立的 `get_usage_metadata_callback()`；回调为空时回退到累积后的最终消息 `usage_metadata`（与既有的两段式回退写法一致）。
2. **合并而非覆盖**：补救场景是两次真实调用（被丢弃的 agent 调用 + 补救调用），两者用量相加后写入 `agent_complete.usage`。
3. **可观测性**：`stream_chat_agent` 与 `run_chat_agent` 在「有正文但零用量」时记录 warning（`provider` / `model`，不含内容），用于区分「上游不上报 usage」与「本应用丢失用量」。
4. 调用方与契约不变：`app/api/v1/chat.py` 两个入口、NDJSON 事件形状、`usage_logs` 表结构均无变化。

## 验证

- **未执行**：本次排查期间 Bash 安全分类器不可用（`data/app.db` 只读查询与测试命令均被拒），后端自检尚未运行。交付前需补：
  ```bash
  cd backend
  check_dir=$(mktemp -d)
  SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh test_agent_service test_chat_balance test_usage_service
  ```
- 新增回归：`tests/test_agent_service.py::test_plain_fallback_stream_is_metered_into_agent_complete`（补救流带 usage 的 chunk 必须计入 `agent_complete.usage`）。已登记到该文件的 `__main__` 列表。
- 真实链路复核（待办）：用官方 Claude 配置发一次闲聊，确认（a）记录出现非零 token，或（b）服务端出现 `chat turn finished without usage metadata` warning（表示上游端点不返回 usage，需更换端点或接受无法计 token）。

## 已知限制

- 用户手动停止（Stop）或连接中断的轮次：`agent_complete` 未送达时 `usage` 仍为空，`persist_assistant_message` 会把该轮记为 0；被中断的 provider 调用是否计费本应用无法确认（与 [feature-billing](../design/feature-billing.md) 既有「Known gaps」一致）。本次未改动此路径。
- 若上游端点完全不返回 usage，即使补救流也无法得到真实 token；现在至少会留下 warning 日志。

## 历史与关联

- 2026-10-16 首次记录：用户截图反馈 Claude 智能问答输入/输出/花费均为 0；源码核对确认补救流未计量。
- 修复 [BUG-20260921-chat-repeat-previous-answer](2026-09-21-chat-repeat-previous-answer.md) 时新增纯文本补救（commit `0daac80`，2026-09-21），当时未同步加入计量；用量采集逻辑经 `85422ac` 重构迁入当前模块。
- 关联：[BUG-20260921-chat-stream-busy-timeout-lag](2026-09-21-chat-stream-busy-timeout-lag.md)（同一计费链路的上一次缺陷）、[feature-billing](../design/feature-billing.md)、[feature-chat](../design/feature-chat.md)。
