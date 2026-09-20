# BUG-20260918-chat-image-tool-result-display：智能问答生成图片只在执行流程里显示链接

- 首次记录：2026-09-18
- 最近更新：2026-09-18
- 状态：已修复且通过前后端回归与浏览器实测验证
- 检索词：智能问答、生成图片、generate_image、执行流程、agent_step、artifact、Markdown 图片、工具失败、ToolException、handle_tool_error、Streamdown img、Lightbox 预览、模型 URL 幻觉、artifactBffUrl 本地下载

## 现象与复现

页面 `/chat`。
1. 让助手生成一张图片后，初次修复后出现新现象：
   - 界面上**明明图片已经渲染显示出来了，但上方仍然出现黄色的警告框**：“图片加载失败，请尝试直接打开链接”。
   - 查看数据库（`chat_messages` 表）发现正文中同时并排存在两张相同标题的图片 Markdown，其中第一段的 JWT 签名 URL 存在单字符错乱导致 403 触发错误条，第二段是正常大图。
2. 缺乏直接点击全屏预览与交互能力，且点击“下载原图”时被浏览器当成跨域 inline 资源而直接在新窗口打开网页，未能直接触发本地文件下载。

## 根因与定位

1. **模型输出时的 Token 级字符幻觉**：
   - `AGENT_SYSTEM_PROMPT` 提示词中原本包含 `After a successful tool call, include the exact Markdown link...`，诱使模型尝试在回复中手抄几百字符的 Base64 签名 URL。
   - 大模型在生成长随机 Base64 字符串时极易在某个 Token 产生错别字（如将 `\u6d77` 误抄为非法字符 `\u6$77`）。
   - 错误的签名导致第一张图片加载 403 触发 `onError`。
2. **后端兜底补齐二次追加**：
   - `_missing_tool_outcomes` 采用全文精确比对 `block not in answer`；模型写错字符导致工具的合法 Markdown 判定为未包含，后端又在末尾追加了一次合法图片，造成正文并存坏图与好图。
3. **下载未能直接保存到本地**：
   - 原始图片 URL 指向后端 `8080` 端口直链，且后端带有 `Content-Disposition: inline`。跨域或直接 `<a>` 打开时浏览器忽略 `download` 属性而在新标签页打开。必须经由前端同源的 `artifactBffUrl` 获取 Blob 并构造 `blob:` 链接触发下载。
4. **骨架屏挂起（曾短暂发生）**：
   - `<img>` 在未加载时曾被设为 `hidden`（`display: none`），导致带有懒加载的浏览器内核挂起网络请求，触发卡在预览态。现改为绝对定位占位 + DOM 持续保持可见加载。

## 修复与影响

- `backend/app/services/agent_service.py`：
  - 更新 `AGENT_SYSTEM_PROMPT`：明确指示模型生成图片后系统会自动挂载，严禁模型在正文中手抄长 URL 或图片 Markdown 标签；
  - 实现 `_reconcile_tool_artifacts`：基于产物标题与有效 URL 智能判重，若正文中包含模型手抄的破损图片标签，则就地纠正替换为合法标准产物 Markdown，彻底避免重复追加与坏链。
- `frontend/src/app/(workspace)/chat/_components/chat-markdown-image.tsx`：
  - 全新独立组件：支持微光骨架加载占位与平滑渐变展示；
  - 点击卡片直接唤起沉浸式全屏 Lightbox 模态框（深色影院模式、居中大图、滚轮与按钮缩放、重置、ESC 关闭）；
  - 下载原图使用 `artifactBffUrl` 走同源 BFF 代理拉取 Blob 并通过 `blob:` 链接直接触发本地保存，支持下载中的 `Loader2` 状态反馈；
  - 规范化弹窗 Header：移除多余的外链/分享按钮与手写 X，右侧留出安全间距避让系统自带的优雅关闭按钮；
  - 加载失败展示精致微卡片，支持一键重试与直接打开链接。
- `frontend/src/app/(workspace)/chat/_components/chat-message-list.tsx`：
  - 接入 `ChatMarkdownImage`；
  - 增加 `sanitizeChatMessageContent` 对消息内可能残留的同名重复/破损图片做安全清洗。
- `frontend/src/lib/i18n.ts`：
  - 补充 `chat.previewImage`、`chat.downloadImage`、`chat.copyLink`、`chat.linkCopied`、`chat.retryLoad`、`chat.zoomIn`、`chat.zoomOut`、`chat.resetZoom` 中英双语文案。

## 验证

- `backend` 回归：`SCENEFLOW_PRIVATE_GENERATED_DIR=$(mktemp -d)/media sh scripts/run_tests.sh test_agent_service test_artifact_service test_chat_balance test_generation_retention test_generation_records test_images test_video_service test_admin_users test_database test_voice_design_api` 全通过（包括针对模型手抄坏链智能替换的单测 `test_image_tool_reconciles_broken_model_copied_url_without_duplicate`）。
- `frontend` 类型与规范：`pnpm exec tsc --noEmit && pnpm lint` 全绿通过（0 error）。
- 前端单元测试：`node --no-warnings --experimental-strip-types --test src/lib/*.test.mts 'src/app/(workspace)/admin/users/_components/user-list.test.mts'` 14/14 全通过。
- 浏览器现场实测：
  - 打开 `/chat`，历史会话与新生成图片的重复黄色警告条已彻底消失；
  - 点击图片卡片流畅打开全屏沉浸式 Lightbox 弹窗，右上角关闭按钮单一且居右，多余分享已移除；
  - 缩放控制台正常工作；
  - 点击“下载原图”，浏览器正确触发本地保存文件，不再跳出新标签页。
