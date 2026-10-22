# BUG-20261022-chat-error-log-summary：聊天错误日志只保留 failed to chat

- 首次记录：2026-10-22
- 最近更新：2026-10-22
- 状态：已修复，流式/非流式日志查询和脱敏回归通过
- 检索词：错误摘要、错误日志、failed to chat、CHAT_STREAM_FAILED、temperature、error_logs、record_http_error

## 现象与复现

用户截图显示聊天界面包含 Fable 5 的温度参数限制，管理后台同次请求摘要却只有 `failed to chat`。这不是两种不同错误，而是日志写入时丢失了原始诊断信息。

复现：令问答模型抛出温度限制异常，调用 `POST /api/chat/sessions/{session_id}/messages/stream`，再按请求 ID 查询 `/api/admin/error-logs`。原有流式日志只保存固定摘要；非流式包装后也会被日志服务裁去具体原因。

## 根因与定位

- `api/v1/chat.py::stream_message` 的 catch 向日志服务只传入固定的 `failed to chat`，但发送给界面的 NDJSON 拼接了真实异常。
- `error_log_service.py::record_http_error` 为防止上游回显私密内容，只保留冒号前的操作名称。因此简单拼接原始异常也无法解决，直接取消脱敏会泄露聊天/脚本、密钥、签名 URL 或提供方响应。
- 共享调用方为 `main.py` 的 HTTP/未捕获异常处理器与聊天流 catch；前端错误日志页直接展示已存的 message，没有另行替换摘要。

## 修复与影响

- 新增 `safe_error_reason`，从异常及 cause/context 链提取限定格式的参数/模型限制、图步骤限制、超时/连接事实、上游 HTTP 状态；无已知格式时只保留异常类型。带循环保护，不保存原始响应文本。
- `record_http_error` 新增可选关键字参数 exception，摘要在原操作名称后追加安全诊断，仍限制 220 字符；提取和写入都置于 best-effort 边界内。
- 聊天流 catch 和 HTTPException handler 传入异常，覆盖流式及保留 cause 的非流式包装；普通未捕获 500 仍使用通用摘要。错误码、响应体、权限、请求关联和数据库结构保持原契约。
- 流式响应已开始时 HTTP 仍为 200，日志记录的 502 表示诊断状态。
- 已写入的历史行没有存储具体原因，无法恢复；未识别的提供方错误保留类型/状态事实，不保证与界面原文逐字相同。
- 长期规则见 [日志约定](../conventions/logging.md)、[错误处理](../conventions/error-handling.md) 和 [聊天设计](../design/feature-chat.md)。

## 验证

新增 `tests/test_chat_error_logs.py`：通过真实聊天路由、HTTP 异常处理器和管理查询端点，模拟带私密后缀的提供方异常，断言两条链路各保存一条含具体限制的记录，且不存测试密钥/签名 URL。另覆盖超时、连接、SDK/httpx 状态、cause 链、步骤限制、循环异常链和日志格式化失败不覆盖原异常。

实际执行命令及八组 PASS 结果见 [同次温度修复的验证](2026-10-22-claude-fable-temperature.md#验证)。其中 `test_breakdown_api` 同时验证共享 HTTP 处理器仍不记录私密脚本。前端类型检查和 lint 通过；`git diff --check` 通过。未执行真实提供方请求或浏览器端到端验证。

## 历史与关联

- 2026-10-22：根据两个界面截图核对流式写入和共享日志脱敏，新增安全诊断提取及回归。
- 触发截图的上游限制由 [Fable 温度修复](2026-10-22-claude-fable-temperature.md) 处理；日志丢失原因是独立缺陷。
