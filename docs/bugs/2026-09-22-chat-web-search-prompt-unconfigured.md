# BUG-20260922-chat-web-search-prompt-unconfigured：未配置 SearXNG 时系统提示词仍宣称拥有 web_search 工具

- 首次记录：2026-09-22
- 最近更新：2026-09-22
- 状态：已修复，单测回归通过
- 检索词：智能问答、联网搜索、web_search、SearXNG 未配置、系统提示词、_agent_system_prompt、is_searxng_configured、工具不存在、编造搜索结果

## 现象与复现

### 影响页面与接口
- 影响界面：工作台智能问答页面 `/chat`（`SCENEFLOW_SEARXNG_BASE_URL` 为空的部署，即默认配置）
- 影响接口：`POST /api/chat/sessions/{session_id}/messages/stream`

### 触发条件与表现
1. 后端未配置 SearXNG；
2. 用户提出需要实时信息的问题（例如“今天有什么新闻”）；
3. 提示词告诉模型“你拥有通过 web_search 进行全网广度搜索……的能力”，但注册的工具列表里没有 `web_search`；
4. 模型可能发出对不存在工具的调用（OpenAI 兼容网关返回 400），或直接编造“搜索到”的内容。

最小复现：`SEARXNG_BASE_URL=""` 时 `create_chat_tools()` 返回的工具名不含 `web_search`，而 `_agent_system_prompt()` 文本包含 `web_search`。

## 根因与定位

- 入口：`backend/app/services/agent_service.py` 的 `_agent_system_prompt()`。
- 工具注册按 `is_searxng_configured()` 分支，提示词却无条件拼接搜索流程说明；既有测试 `test_agent_system_prompt_temporal_and_search_optimization` 只在 patch 为已配置时断言。
- 已确认原因。

## 修复与影响

1. `_agent_system_prompt(web_search_enabled=None)` 按 `is_searxng_configured()` 分支：已配置时保留原搜索/抓取流程并写明每轮 3 次搜索上限；未配置时明确“没有网络搜索工具，不要声称已联网搜索”，只说明 `fetch_web_content` 与相对时间处理。
2. 调用方 `_agent()` 不变。

## 验证

1. 新增 `tests/test_agent_service.py::test_agent_system_prompt_without_search_does_not_advertise_web_search`：未配置时提示词不含 `web_search`、包含“没有网络搜索工具”与 `fetch_web_content`，工具列表同样不含 `web_search`。
2. `sh scripts/run_tests.sh test_searxng_service test_crawl_service test_agent_service test_chat_balance`：全部 PASS。
3. 未执行：未用真实模型验证行为差异。

## 历史与关联

- 2026-09-21：commit `4b2249e` 引入。
- 2026-09-22：审查中复现并修复。相关：[BUG-20260922-chat-web-search-turn-cache](2026-09-22-chat-web-search-turn-cache.md)。
