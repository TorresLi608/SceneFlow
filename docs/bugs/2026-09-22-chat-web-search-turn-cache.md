# BUG-20260922-chat-web-search-turn-cache：同一轮不同关键词的网络搜索返回第一次的结果

- 首次记录：2026-09-22
- 最近更新：2026-09-22
- 状态：已修复，单测回归通过
- 检索词：智能问答、联网搜索、web_search、SearXNG、searched_cache、对比类问题、答非所问、MAX_WEB_SEARCHES_PER_TURN、agent_service

## 现象与复现

### 影响页面与接口
- 影响界面：工作台智能问答页面 `/chat?chat={session_id}`（已配置 `SCENEFLOW_SEARXNG_BASE_URL` 时）
- 影响接口：`POST /api/chat/sessions/{session_id}/messages/stream` 中的 `web_search` 工具

### 触发条件与表现
1. 用户在一轮对话里提出需要多次搜索的问题，例如“比较一下成都和北京今天的天气”；
2. 模型先调用 `web_search("成都 天气")`，再调用 `web_search("北京 天气")`；
3. 第二次调用没有发起任何请求，直接返回了第一次“成都 天气”的结果，工具输出里的关键词仍是“成都 天气”；
4. 模型拿到与问题无关的资料，要么声称查不到北京天气，要么把成都数据当成北京作答。

最小复现（mock，无需真实 SearXNG）：patch `app.services.agent_service.search_searxng` 为按关键词返回不同文本的 `AsyncMock`，`create_chat_tools()` 后连续 `ainvoke` 两个不同 `query`，修复前第二次返回值与第一次完全相同且底层只被调用一次。

## 根因与定位

- 入口：`backend/app/services/agent_service.py` 中 `create_chat_tools()` 内的 `web_search` 闭包。
- 修复前逻辑：每轮一个 `searched_cache` 字典，命中同关键词返回缓存，**否则只要缓存非空就返回第一条缓存值**，注释称用于“防止模型反复循环或并发调用”。
- 实际效果：任何第二个不同关键词都被静默替换成第一次的结果，模型没有任何提示；而并发工具调用时缓存尚未写入，这段逻辑并不能阻止并发。
- 已确认原因，与提示词无关。

## 修复与影响

1. `web_search` 改为按关键词缓存、按次数限流：相同关键词（空白归一化后）复用本轮结果；不同关键词各自执行，每轮最多 `MAX_WEB_SEARCHES_PER_TURN = 3` 次；计数在调用开始时递增，并发调用也受限。
2. 超出预算时不再冒充结果，而是返回 `searxng_service.search_limit_notice()` 的说明文本（以 `SEARCH_LIMIT_NOTICE_MARKER` 开头），要求模型基于已有结果作答；`extract_search_step_summary` 把它显示为“已达本轮搜索上限”，不会在回复里追加“⚠️ 网络搜索失败”提示。
3. 系统提示词同步写明每轮最多 3 次不同关键词搜索、达到上限后直接作答。
4. 同模块附带调整（`searxng_service.py`）：
   - 请求只保留 SearXNG 实际读取的 `tokens` 查询参数和给反向代理用的 `Authorization: Bearer`，去掉重复的 `token`、`X-Token`（已核对 SearXNG `webapp.pre_request` 合并 GET 参数后交给 `Preferences.parse_dict`，`tokens` 为有效键）。
   - 日志不再记录搜索词，只记录超时/状态码/异常类型与关键词长度，符合聊天设计文档规则 5。
5. 长期规则：见 [聊天设计文档](../design/feature-chat.md) “Web tools”条目；环境变量与 SearXNG `json` 格式要求见 [backend/README.md](../../backend/README.md#environment)。

## 验证

1. 新增 `tests/test_agent_service.py::test_web_search_runs_distinct_queries_and_caps_the_turn`：三个不同关键词各自执行、重复关键词命中缓存、第四个关键词返回上限说明并且步骤摘要为“已达本轮搜索上限”。
2. `tests/test_searxng_service.py::test_searxng_search_with_token` 改为断言只发送 `tokens` 与 bearer 头。
3. 执行 `SCENEFLOW_PRIVATE_GENERATED_DIR=$tmp/media sh scripts/run_tests.sh test_searxng_service test_crawl_service test_agent_service test_chat_balance`：全部 PASS。
4. 全量后端套件：除既有失败 `test_episode_migration`（BUG-20260920）与 `test_config_service`（`test_video_capabilities_are_normalized_and_stored`，日志与本次改动模块无关）外全部 PASS。
5. 未执行：未连接真实 SearXNG 做端到端；未做浏览器实测。

## 历史与关联

- 2026-09-21：commit `4b2249e` 引入联网搜索时带入该缓存逻辑。
- 2026-09-22：代码审查中通过 mock 复现并修复。相关：[BUG-20260922-chat-web-search-prompt-unconfigured](2026-09-22-chat-web-search-prompt-unconfigured.md)、[BUG-20260922-chat-search-step-display](2026-09-22-chat-search-step-display.md)。
