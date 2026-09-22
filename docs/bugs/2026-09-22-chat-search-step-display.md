# BUG-20260922-chat-search-step-display：搜索结果计数与执行流程面板文案不一致

- 首次记录：2026-09-22
- 最近更新：2026-09-22
- 状态：已修复，后端单测与前端类型检查/Lint 通过；浏览器未实测
- 检索词：智能问答、执行流程、agent_step、网络搜索、提取网页正文、共精选 N 条、检索到 N 条、formatStepDetail、英文界面、extract_search_step_summary、extract_crawl_step_summary、chat-message-list

## 现象与复现

### 影响页面与接口
- 影响界面：工作台智能问答页面 `/chat` 的执行流程面板
- 影响接口：`POST /api/chat/sessions/{session_id}/messages/stream` 的 `agent_step` 事件

### 触发条件与表现
1. **计数不准**：`format_search_results()` 先写头部“共精选 N 条”（N 为过滤后的全部条数），再按总字符预算截断条目；mock 中 5 条 180 字摘要、预算 500 字时只列出 2 条，头部与流程面板仍显示“5 条”。
2. **英文界面不翻译**：后端搜索完成的 detail 实际是“检索到 N 条精选网页”“检索到 N 条相关网页”“检索完成”“未检索到匹配网页”，抓取开始是“提取「url」”，而 `chat-message-list.tsx` 的英文映射写的是“精选 x 条相关网页结果”“抓取「xxx」”“提取完成，共 x 字符”，一个都对不上，英文界面下这些 detail 保持中文。
3. **抓取完成 detail 是整段 Markdown**：`fetch_web_content` 完成后 `_tool_output_detail()` 没有摘要分支，面板显示 `### 网页深度提取：...` 开头的前 160 字。

## 根因与定位

- `backend/app/services/searxng_service.py::format_search_results`：头部在截断前生成。
- `backend/app/services/agent_service.py::_tool_output_detail`：只处理搜索摘要。
- `frontend/src/app/(workspace)/chat/_components/chat-message-list.tsx::formatStepDetail`：正则按设想中的文案编写，未对照后端实际输出。
- 均为已确认原因。

## 修复与影响

1. `format_search_results()` 先裁剪条目再生成头部，“共精选 N 条”等于实际列出的条数；`extract_search_step_summary()` 随之准确，并新增“已达本轮搜索上限”映射。
2. `crawl_service.extract_crawl_step_summary()` 把抓取输出压缩为“已提取 N 字符正文”“已提取前 M 字符，原文约 N 字符”“未提取到有效文本”“提取完成”；`_tool_output_detail()` 依次尝试搜索摘要与抓取摘要。
3. 前端 `formatStepDetail` 改为匹配后端真实文案：`检索到 N 条精选/相关网页 → N web results`、`提取「url」/抓取「url」 → Fetching "url"`、`已提取 N 字符正文 → Extracted N characters`、`已提取前 M 字符，原文约 N 字符 → Extracted first M of ~N characters`，固定短语补充“检索完成”“未检索到匹配网页”“已达本轮搜索上限”“提取完成”“未提取到有效文本”。中文界面不受影响。
4. 未改动的部分：面板仍按中文 label 判断图标与翻译（既有模式），后端 `agent_step` 没有新增字段，BFF 与控制器无需改动。

## 验证

1. `tests/test_searxng_service.py::test_searxng_format_results_header_matches_listed_entries`：截断后头部为“共精选 2 条”，摘要为“检索到 2 条精选网页”；`test_searxng_step_summary` 覆盖上限文案。
2. `tests/test_crawl_service.py::test_extract_crawl_step_summary`；`tests/test_agent_service.py::test_web_search_runs_distinct_queries_and_caps_the_turn` 断言 `_tool_output_detail` 输出“已达本轮搜索上限”。
3. 后端：`sh scripts/run_tests.sh test_searxng_service test_crawl_service test_agent_service test_chat_balance` 全部 PASS。前端：`pnpm exec tsc --noEmit`、`pnpm lint` 通过。
4. 未执行：未在浏览器英文界面下实测面板显示。

## 历史与关联

- 2026-09-21：commit `4b2249e` 与 `e59b41e` 引入面板与英文映射。
- 2026-09-22：审查中修复。相关：[BUG-20260922-chat-web-search-turn-cache](2026-09-22-chat-web-search-turn-cache.md)、[BUG-20260918-chat-image-tool-result-display](2026-09-18-chat-image-tool-result-display.md)。
