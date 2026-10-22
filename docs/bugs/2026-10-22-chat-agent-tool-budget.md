# BUG-20261022-chat-agent-tool-budget：智能问答工具循环达到递归上限

- 首次记录：2026-10-22
- 最近更新：2026-10-22
- 状态：已修复，模拟工具循环及相关自检通过；真实模型调用待验证
- 检索词：智能问答、GRAPH_RECURSION_LIMIT、Recursion limit of 12、LangGraph、create_agent、重复调用、工具预算、ChatToolBudget

## 现象与复现

用户报告智能问答出现 `failed to chat: Recursion limit of 12 reached without hitting a stop condition`。流式和非流式入口均使用 `agent_service`；复杂搜索/网页读取或反复工具调用时，流程仍未生成最终答案就被图执行器终止。

模拟复现序列：模型连续请求读取不同网页，工具成功返回资料，但模型继续发起下一次请求。原先模型节点与工具节点交替消耗固定的 12 步，应用没有预算耗尽时转入回答的逻辑。生产该轮的具体工具记录未取得，不能确认是正常多步任务还是重复/失败循环。

## 根因与定位

- `backend/app/services/agent_service.py::run_chat_agent` 和 `stream_chat_agent` 均硬编码 `recursion_limit=12`。这限制的是图执行步数，并非 12 个工具或 12 次用户消息。
- 仅靠系统提示词要求及时结束；没有代码级总工具预算、重复调用拦截、连续失败收尾。三次不同搜索的专项限制无法约束其他工具，模型也可能继续请求已被拒绝的搜索。
- `chat.py` 在异常路径直接输出框架异常；本次在到达该异常前结束正常工具循环，保留既有流事件/持久化边界。

## 修复与影响

- 新增 `services/chat_agent_middleware.py`，使用现有 LangChain middleware。每次 `_agent` 创建独立实例，两个问答入口共用策略。
- 每轮最多六轮工具交互、八次实际工具执行；并发工具在启动前占用预算，超额调用返回预算说明而不执行。
- 同工具名和相同 JSON 参数只执行一次，包括正在等待和已经失败的调用。缓存命中保留各自 `tool_call_id`；不同用户/轮次不共享缓存。
- 遇到重复、连续两次工具失败、或预算耗尽时，下一次模型调用移除 tools，保留已取得的结果，要求立即回答并说明未完成部分。
- 网关即使在未绑定工具时继续返回工具调用或空正文，也转为有界说明；仍保留该次响应的 usage。递归上限改为 32，仅作后备保护。
- `_reconcile_tool_artifacts` 被两个入口的 `_answer_with_artifacts` 以及流式 `_missing_tool_outcomes` 调用；缓存结果会产生多条相同结果消息，补充待追加块去重，避免同一文件或失败提示出现多次。
- 生成收尾回答的调用仍在原有计费回调作用域内，真实请求正常计量。取消等待会取消进行中的工具任务；普通无工具回答不增加模型调用。
- 文档：[聊天设计](../design/feature-chat.md)、[后端说明](../../backend/README.md)、[代码地图](../architecture/code-map.md)。接口/数据库结构未改动。

## 验证

新增 `tests/test_chat_agent_budget.py`，通过实际 `create_agent` + 模拟模型/工具覆盖九项场景：长流程的两个入口保留资料并计量最终回答；并发批量调用上限；串行/并发相同调用共享结果且保留工具 ID；连续失败；忽略工具禁用的模型；并发轮次隔离；普通回答无额外调用；重复图片只生成一个文件；取消传递到进行中的工具。

实际执行：

```bash
cd backend
check_dir=$(mktemp -d /private/tmp/sceneflow-chat-budget.XXXXXX)
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh test_chat_agent_budget test_agent_service test_anthropic_usage test_chat_balance test_artifact_service test_searxng_service test_crawl_service test_usage_service
```

结果：八组全部 PASS。测试运行器使用隔离临时数据库，媒体使用临时目录。

前端 `pnpm exec tsc --noEmit`、`pnpm lint` 均通过。`git diff --check` 通过。

测试开发时修正了模拟模型循环复用响应 ID 导致的用量断言失真；图片去重回归随后发现非流式结果追加相同文件两次，已补充结果块去重并重新通过上述八组。

## 限制与历史

- 2026-10-22：根据用户报告定位固定图上限和缺失预算控制；补充执行预算、重复复用与纯文本收尾。
- 未调用付费模型、真实 SearXNG/Crawl4AI，也未做浏览器端到端验证；未确认用户原始轮次的具体调用序列。
- 此预算约束每轮工具数量及循环次数，不是总请求墙钟超时。网络、提供方、鉴权等独立失败仍按原路径报错；不保证收尾模型一定能取得原本缺失的资料。
- 正常收尾调用也可能计费；上游未上报用量时沿用既有规则，不能估算填入。相关：[搜索专项预算](2026-09-22-chat-web-search-turn-cache.md)、[补救流计量](2026-10-16-chat-fallback-usage-unmetered.md)。
