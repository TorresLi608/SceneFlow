# BUG-20261022-claude-fable-temperature：Fable 5 拒绝非默认 temperature

- 首次记录：2026-10-22
- 最近更新：2026-10-22
- 状态：已修复，模拟协议及相关回归通过；真实中转站待验证
- 检索词：智能问答、claude-fable-5、temperature、non-default values、Sonnet 5.5、Anthropic、中转站

## 现象与复现

用户报告同一中转站 Sonnet 5.5 可以问答，Fable 5 返回 ``failed to chat: `temperature` is not supported for claude-fable-5 at non-default values.``。截图确认实际错误文本。

最小应用侧复现：通过 `ModelRouter.chat_model` 创建 Fable 5，传入问答使用的 `temperature=0.3`，检查发给提供方的 JSON；修复前会包含该非默认参数。

## 根因与定位

- `agent_service.py::_agent` 和 `stream_chat_agent` 的纯文本补救分支均设置 `temperature=0.3`。
- `llms/router.py::chat_model` 原样把参数交给 Anthropic 或 OpenAI 兼容适配器，没有按模型处理采样限制。其他调用方还包括配置测试、脚本解析/拆解、提示词与上下文摘要等公共文本流程。
- 上游错误确认该端点拒绝 Fable 5 的非默认温度；没有取得生产请求或官方能力文档，不能由报错断言中转站内部实现或其他采样参数的限制。

## 修复与影响

- 在公共 `chat_model` 入口解析模型 ID 后，针对 `claude-fable-5` 及以 `-`/`.` 开始的版本后缀移除显式 `temperature`，使用提供方默认值。
- 同时覆盖 Anthropic 原生官方/中转地址和 OpenAI 兼容中转地址（含 custom）。覆盖主问答、无工具补救及其他公共入口调用方。
- Sonnet 5.5 和其他模型保留现有行为；不匹配 `claude-fable-50`，没有全局关闭采样或异常后盲目重试。
- 无数据库、HTTP/NDJSON 契约变更。长期行为见 [聊天设计](../design/feature-chat.md)、[后端说明](../../backend/README.md)。

## 验证

新增 `tests/test_chat_model_temperature.py`：使用 HTTP MockTransport 检查 16 组实际 SDK 出站 JSON（官方地址、原生中转、OpenAI 兼容/custom × Fable、版本后缀、Sonnet、相似名称），并以真实 agent + 模拟 SSE 验证主调用和纯文本补救均省略温度。

实际执行：

```bash
cd backend
check_dir=$(mktemp -d /private/tmp/sceneflow-chat-errors.XXXXXX)
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh test_chat_model_temperature test_chat_error_logs test_anthropic_usage test_agent_service test_chat_agent_budget test_chat_balance test_log_time_ranges test_breakdown_api
```

八组全部 PASS；测试使用临时数据库和媒体目录。前端 `pnpm exec tsc --noEmit`、`pnpm lint` 均通过。未调用付费模型或真实中转站，部署后仍需用户实际验证。

## 历史与关联

- 2026-10-22：根据模型差异报错与截图，修复公共参数兼容。
- 同次任务独立修复 [错误日志丢失具体原因](2026-10-22-chat-error-log-summary.md)。工具循环是 [另一根因](2026-10-22-chat-agent-tool-budget.md)，不由本修复处理。
