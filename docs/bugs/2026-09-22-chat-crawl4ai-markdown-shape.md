# BUG-20260922-chat-crawl4ai-markdown-shape：Crawl4AI 服务返回的 markdown 对象被当作字符串喂给模型

- 首次记录：2026-09-22
- 最近更新：2026-09-22
- 状态：已修复，单测回归通过；真实 Crawl4AI 服务待验证
- 检索词：智能问答、fetch_web_content、Crawl4AI、raw_markdown、fit_markdown、字典 repr、crawl_service、/crawl、/md、priority

## 现象与复现

### 影响页面与接口
- 影响界面：工作台智能问答页面 `/chat`（已配置 `SCENEFLOW_CRAWL4AI_BASE_URL` 时）
- 影响接口：`POST /api/chat/sessions/{session_id}/messages/stream` 中的 `fetch_web_content` 工具

### 触发条件与表现
1. 配置了 Crawl4AI REST 服务（0.5 及以上版本）；
2. 用户让助手读取一个网页链接；
3. 工具返回给模型的“正文”是 Python 字典的 repr，形如 `{'raw_markdown': '# ...', 'fit_markdown': '', ...}`，模型据此总结时夹带大量转义与键名，或因内容像代码而答非所问。

最小复现（mock）：让 `/crawl` 返回 `{"results": [{"markdown": {"raw_markdown": "# Raw title\n\nraw body", "fit_markdown": ""}, "metadata": {"title": "T"}}]}`，修复前 `crawl_web_page()` 输出包含 `{'raw_markdown'`。

## 根因与定位

- 入口：`backend/app/services/crawl_service.py` 中 `crawl_web_page()` 解析 Crawl4AI 响应的分支。
- 已核对 crawl4ai 主��源码 `crawl4ai/models.py`：`CrawlResult.model_dump()` 显式把 `markdown` 写成 `MarkdownGenerationResult.model_dump()`，即含 `raw_markdown`、`fit_markdown` 等键的字典；顶层没有 `fit_markdown`。Docker API `/crawl` 返回 `{"success", "results": [该字典...]}`。
- 修复前代码 `str(fit_md or raw_md)` 对字典做 `str()`，把 repr 原样送入模型；`metadata` 为 `None` 时 `.get("title")` 还会抛异常。
- 现有测试 `test_crawl_via_crawl4ai_api` 使用的是字符串形态的假响应，因此没有暴露。
- 附带发现：请求体里的 `priority` 字段在当前 `CrawlRequest` 模型中不存在（被忽略）；`/md` 端点只在 `/crawl` 返回 404 时才尝试，当前版本两者并存，该分支实际不会触发。

## 修复与影响

1. 新增 `_markdown_from_crawl4ai()`：顶层 `fit_markdown`（旧版）优先，再取 `markdown` 对象里的 `fit_markdown`、`raw_markdown`，再兼容纯字符串 `markdown` 与 `content`；跳过空值与 `<property object ...>` 之类的无效串。
2. 新增 `_title_from_crawl4ai()`：`metadata` 非字典时安全回退到默认标题。
3. 请求体去掉无效的 `priority`；保留 404 时回退 `/md` 的逻辑，其返回的字符串 `markdown` 由同一解析函数处理。
4. 调用方不变（`agent_service.fetch_web_content` → `crawl_web_page`）。

## 验证

1. 新增 `tests/test_crawl_service.py::test_crawl_via_crawl4ai_api_reads_markdown_object`：对象形态解析出正文与 `metadata.title`，输出不含 `{'raw_markdown'`；同时覆盖 fit 优先、纯字符串、`content` 回退与 `metadata=None`。
2. 既有 `test_crawl_via_crawl4ai_api`（字符串形态、顶层 `fit_markdown` 优先）保持通过，并断言请求体不含 `priority`。
3. `sh scripts/run_tests.sh test_crawl_service`：PASS（见 [BUG-20260922-chat-fetch-web-content-ssrf](2026-09-22-chat-fetch-web-content-ssrf.md) 的完整命令与全量结果）。
4. 未执行：未对接真实 Crawl4AI Docker 服务验证；`/md` 回退分支只有代码核对，没有实网结果。

## 历史与关联

- 2026-09-21：commit `4b2249e` 引入 Crawl4AI 集成。
- 2026-09-22：审查时核对上游源码后修复。相关：[BUG-20260922-chat-fetch-web-content-ssrf](2026-09-22-chat-fetch-web-content-ssrf.md)。
