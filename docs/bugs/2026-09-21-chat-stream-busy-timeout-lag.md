# BUG-20260921-chat-stream-busy-timeout-lag：智能问答回复完毕后仍悬挂延迟关闭

- 首次记录：2026-09-21
- 最近更新：2026-09-21
- 状态：已修复，真实端到端时序测量与全套单测通过
- 检索词：智能问答、延迟结束、悬挂、持续几秒钟才结束、busy_timeout、database is locked、SQLite 写锁死锁、persist_assistant_message、record_usage

## 现象与复现

### 影响页面与接口
- 影响界面：工作台智能问答页面 `/chat?chat={session_id}`
- 影响接口：`POST /api/chat/sessions/{session_id}/messages/stream`

### 触发条件与表现
1. 在智能问答对话中发送任何问题（包括简单的测试闲聊“测试”）；
2. 大模型回复的正文内容已完全在前端打印完毕，但界面光标仍持续闪烁，顶部状态栏持续显示“正在生成回复...”，右下角输入框仍为黑底白色方形“停止”按钮；
3. 整整卡顿悬挂约 30 秒后，流式才突然关闭，停止按钮才转为发送箭头；
4. 真实端到端 HTTP 测试测量发现：从收到最后一个 `content_delta` 到 HTTP 流连接完全关闭耗时长达 **31.18 秒**。

## 根因与定位

1. **`persist_assistant_message` 中嵌套开启 SQLite 写事务导致死锁互斥**：
   - 入口位于 `backend/app/api/v1/chat.py` 中的 `persist_assistant_message`：
     ```python
     def persist_assistant_message():
         ...
         try:
             with db() as session:
                 msg = save_chat_message(
                     session,
                     session_id,
                     "assistant",
                     answer.strip(),
                     config["provider"],
                     config["model"],
                     reasoning.strip(),
                 )
                 saved = True
                 try:
                     record_usage(user_id, config, "chat", started_at, usage)
                 except Exception:
                     pass
                 return msg
     ```
   - `save_chat_message` 在外层的 `with db() as session:` 块内执行了 `session.add`、`session.flush` 与 `session.execute(update(ChatSession)...)`，此时 SQLAlchemy 已在当前 SQLite 连接上获取了独占写锁且尚未提交事务。
   - 而在此 `session` 块内部紧接着调用了 `record_usage(...)`。
   - `record_usage`（位于 `app/services/usage_service.py`）内部又多次调用了 `with db() as session:` 来查表和插入 `UsageLog`。
   - 由于 SQLite 为单写者模式，外部事务未提交，内层的新连接试图获取写锁被阻塞，进入 SQLite 内部 busy 等待重试。
   - 依据 `app/core/database.py` 中设置的 `PRAGMA busy_timeout = 30000`（30 秒），内层连接整整阻塞重试了 30 秒，最终抛出 `sqlite3.OperationalError: database is locked`。
   - 该异常被 `except Exception: pass` 静默吞掉，内层超时退出后外层的 `with db() as session:` 才退出并提交，导致每次回复后必卡 30 秒，且用户的 Token 扣费日志完全未被正常记录。

## 修复与影响

1. **事务边界解耦**：
   - 将 `record_usage(user_id, config, "chat", started_at, usage)` 移至 `with db() as session:` 外部执行。
   - `save_chat_message` 在独立事务中完成回复落库并提交释放 SQLite 锁后，再由 `record_usage` 开启独立事务写入计费日志。
2. **时延从 31 秒骤降为 0.01 秒**：
   - 彻底消除了 30 秒的死锁重试等待，大模型最后一个 token 吐完后 0.01 秒即可完成落库和流式关闭，前端光标和按钮瞬间恢复就绪状态。
3. **计费日志恢复正常**：
   - 解除了 `record_usage` 被死锁超时的异常，准确恢复问答消费记录。

## 验证

1. **端到端 ASGI 与真实端口测量**：
   - 运行针对 8080 端口的真实 HTTP 测试，最后一个 `content_delta` 到 HTTP 流关闭耗时从修复前的 **31.18s** 下降至 **0.01s**。
2. **后端测试回归**：
   - `scripts/run_tests.sh test_chat_balance test_agent_service` 全部通过。
3. **前端检查**：
   - `pnpm exec tsc --noEmit && pnpm lint` 校验全部通过。
