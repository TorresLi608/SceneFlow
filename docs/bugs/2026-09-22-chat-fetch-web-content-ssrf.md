# BUG-20260922-chat-fetch-web-content-ssrf：网页正文提取可被重定向和 DNS 绕过访问内网，且无响应大小与总时长上限

- 首次记录：2026-09-22
- 最近更新：2026-09-22
- 状态：已修复，单测回归与本机 DNS 实测通过；DNS 重绑定与 Crawl4AI 远端抓取仍有已知限制
- 检索词：智能问答、fetch_web_content、SSRF、内网探测、follow_redirects、nip.io、localtest.me、0177.0.0.1、is_safe_public_url、assert_public_url、_resolve_host、MAX_RESPONSE_BYTES、CRAWL_TOTAL_TIMEOUT_SECONDS、crawl_service、日志记录 URL

## 现象与复现

### 影响页面与接口
- 影响界面：工作台智能问答页面 `/chat`，任何登录用户
- 影响接口：`POST /api/chat/sessions/{session_id}/messages/stream` 中的 `fetch_web_content` 工具（无需配置 SearXNG 即注册）

### 触发条件与表现
1. **重定向绕过**：让助手读取一个公网地址，该地址 302 跳转到 `http://127.0.0.1:8080/...`；修复前内置抓取器 `follow_redirects=True` 直接跟随，把内网页面正文返回给模型。mock 复现中请求序列为 `public.example.com/article → 127.0.0.1:8080/internal`，内网文本出现在工具输出里。
2. **DNS 绕过**：`http://127.0.0.1.nip.io/`、`http://localtest.me/` 字符串校验通过（本机实测两者均解析到 127.0.0.1）；`http://0177.0.0.1/` 不是合法 IP 字面量被当作域名放行，glibc 会按八进制解析为 127.0.0.1（macOS 解析为 177.0.0.1）。
3. **无大小上限**：`response.text` 一次读完整个响应且不检查 Content-Type，指向大文件的链接会把整个文件读进后端内存（单进程后端影响所有用户）。
4. **无总时长上限**：Crawl4AI 15 秒、404 重试再 15 秒、本地 SDK 无超时、内置抓取 15 秒串联，最坏超过 45 秒才失败，前端“正在生成回复”长时间悬挂。
5. **日志含用户内容**：超时/失败日志记录了完整 URL，搜索服务同样记录了搜索词，违反 [聊天设计文档](../design/feature-chat.md) 规则 5 与 AGENTS 不变量 10。

## 根因与定位

- 入口：`backend/app/services/crawl_service.py`。
- `is_safe_public_url()` 只做字符串判断：不解析 DNS、不识别 IPv4-mapped IPv6、不拦截数字伪域名；`_crawl_via_builtin_fallback()` 开启自动重定向且每一跳都不再校验；`response.text` 无上限；`crawl_web_page()` 没有整体超时。
- 以上均为已确认原因。

## 修复与影响

1. **地址校验分两层**：`is_safe_public_url()` 仍是纯字符串检查（仅 HTTP(S)、拒绝 URL 内嵌凭据、`localhost`/`.local`/`.localhost`/`.internal`/`.home.arpa`、非公网 IP 字面量含 `::ffff:` 映射与 6to4、以及末段为纯数字或 `0x` 形式的数字伪域名）；新增 `assert_public_url()` 通过 `_resolve_host()` 解析域名，任一结果地址非全局可路由即拒绝，解析失败或 5 秒内未返回也拒绝。
2. **重定向逐跳校验**：内置抓取器改为 `follow_redirects=False`，手动最多跟随 5 跳，每一跳先过 `assert_public_url()`；超过跳数返回“重定向次数过多”。
3. **响应限制**：流式读取最多 `MAX_RESPONSE_BYTES`（2 MB）后截断；Content-Type 存在且非文本类（html/xhtml/plain/xml）时拒绝；按响应头 charset、`<meta charset>`、UTF-8 顺序解码，`gb2312`/`gbk` 统一按 `gb18030` 解码。
4. **整体超时**：`crawl_web_page()` 用 `asyncio.timeout(CRAWL_TOTAL_TIMEOUT_SECONDS = 30)` 包住全部提取阶段，超时统一返回“访问网页超时”。
5. **日志脱敏**：抓取与搜索日志只记录异常类型、状态码、字节数或关键词长度，不再记录 URL 与搜索词。
6. **调用方**：`agent_service.fetch_web_content` 不变；`crawl_web_page()` 在任何请求前先执行 `assert_public_url()`，因此配置了 Crawl4AI 远端服务时初始 URL 同样受检。
7. **已知限制**（已写入聊天设计文档“Known gaps”）：校验与实际连接之间的 DNS 重绑定未阻断（连接未固定到已校验的 IP）；Crawl4AI 远端服务自行跟随重定向，无法逐跳校验。

## 验证

1. `tests/test_crawl_service.py` 新增/更新：
   - `test_is_safe_public_url`：新增 169.254.169.254、`[::ffff:127.0.0.1]`、`[::1]`、`0.0.0.0`、`0177.0.0.1`、`2130706433`、`0x7f.0.0.1`、`app.localhost`、URL 凭据用例；
   - `test_assert_public_url_rejects_hostnames_resolving_to_internal_addresses`：解析到 127.0.0.1 / 10.x / 混合公网+内网 / IPv4-mapped 均拒绝，解析失败报“无法解析”；
   - `test_crawl_follows_public_redirects_but_rejects_internal_targets`：公网→内网跳转在第一跳后终止且未发出第二个请求；公网→公网相对跳转正常读取；循环跳转报“重定向次数过多”；
   - `test_crawl_builtin_fallback_caps_body_and_rejects_binary_content`、`test_crawl_builtin_fallback_decodes_declared_charsets`、`test_crawl_total_timeout`、`test_extract_crawl_step_summary`；
   - 其余用例统一 patch `_resolve_host`，测试不触达真实 DNS。
2. `SCENEFLOW_PRIVATE_GENERATED_DIR=$tmp/media sh scripts/run_tests.sh test_searxng_service test_crawl_service test_agent_service test_chat_balance`：全部 PASS（首轮 `test_crawl_service` 因测试辅助函数写法与候选顺序回归失败，修正后 PASS）。
3. 全量后端套件（40 个文件）：除既有失败 `test_episode_migration`（BUG-20260920）与 `test_config_service`（`test_video_capabilities_are_normalized_and_stored`，日志不涉及本次模块）外全部 PASS。
4. 本机真实 DNS 抽查：`127.0.0.1.nip.io`、`localtest.me` 解析为 127.0.0.1 并被 `assert_public_url` 拒绝；`0177.0.0.1` 在 macOS 解析为 177.0.0.1，因此由数字伪域名规则在字符串层拒绝。
5. 未执行：未对真实站点或真实 Crawl4AI 服务做端到端；未做浏览器实测。

## 历史与关联

- 2026-09-21：commit `4b2249e` 引入 `fetch_web_content`。
- 2026-09-22：审查中复现并修复。相关：[BUG-20260922-chat-crawl4ai-markdown-shape](2026-09-22-chat-crawl4ai-markdown-shape.md)。
