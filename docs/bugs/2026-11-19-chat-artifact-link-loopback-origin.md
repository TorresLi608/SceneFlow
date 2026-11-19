# BUG-20261119-chat-artifact-link-loopback-origin：线上智能问答的文档下载链接指向 127.0.0.1

- 首次记录：2026-11-19
- 最近更新：2026-11-19
- 状态：已修改待验证
- 检索词：智能问答、generate_pdf、generate_docx、PDF、Word、下载链接、127.0.0.1:8080、SCENEFLOW_PUBLIC_BASE_URL、PUBLIC_BASE_URL、artifact_service、/api/chat/artifacts、artifactBffUrl、rewriteArtifactLinks、线上部署、下载不了

## 现象与复现

页面 `/chat`，线上部署环境（用户反馈，2026-11-19）。

1. 让助手生成 PDF 或 Word 文档。
2. 回复正文里的下载链接形如 `http://127.0.0.1:8080/api/chat/artifacts/<签名 token>`。
3. 预期点击后下载文件；实际链接指向访问者自己电脑的回环地址，无法下载。

本次未在线上环境复现，现象来自用户提供的链接（token 不入档）；链接来源由源码核对确认。

## 根因与定位

已确认（源码核对）：

1. `backend/app/core/config.py` 的 `PUBLIC_BASE_URL` 读取 `SCENEFLOW_PUBLIC_BASE_URL`，未设置时默认 `http://127.0.0.1:8080`；`backend/app/services/artifact_service.py` 的 `_signed_url` 把它拼成每个签名链接的来源。`docker-compose.yml` 不设置该变量，只有 `backend/.env` 里写了才会生效，线上漏配时所有签名链接都指向回环地址。
2. 聊天正文中的图片/文档 Markdown 由后端 `agent_service` 生成并随消息落库（`chat_messages`），因此链接来源被固化在历史消息里，事后改环境变量也不会修正旧消息。
3. 其他页面（图片/视频/音色面板、分集编辑器、项目资源）展示前都经 `frontend/src/lib/artifact-url.ts` 的 `artifactBffUrl` 改写成同源 `/api/bff/chat/artifacts/<token>`，所以漏配时不受影响。智能问答正文是 Streamdown 渲染的 Markdown：`<img>` 的 `src` 和文档 `<a>` 的 `href` 都直接使用落库的绝对地址，只有图片卡片的“下载原图”按钮走了 `artifactBffUrl`。文档链接因此是漏配时唯一完全不可用的入口。

未验证的假设：线上环境确实没有设置 `SCENEFLOW_PUBLIC_BASE_URL`（从链接来源推断，未查看线上配置）。

## 修复与影响

- `frontend/src/lib/artifact-url.ts`：新增 `rewriteArtifactLinks(text, origin)`，把文本中 `http(s)://<任意主机>/api/chat/artifacts/` 前缀改写为 `<页面 origin>/api/bff/chat/artifacts/`。保留绝对地址，Streamdown 的链接加固与确认弹窗行为与原链接一致；`origin` 为空（服务端渲染）时原样返回。
- `frontend/src/app/(workspace)/chat/_components/chat-message-list.tsx`：`MessageContent` 渲染前、`handleCopy` 复制前都经 `withReachableArtifactLinks` 改写。影响：聊天正文的文档链接、图片 `src`、图片卡片“复制链接”和整条消息复制，现在都指向当前站点；历史消息无需迁移，渲染时生效。
- 下载走 `frontend/next.config.ts` 的 `/api/bff/:path*` 兜底代理到后端 `/api/chat/artifacts/<token>`；token 不变，后端的 `Content-Disposition`（文档为 attachment）原样透传。
- 后端未改动。签名链接仍是不记名凭据（AGENTS.md 不变量 10），改写不改变其权限或有效期。

仍存在的限制：

- `SCENEFLOW_PUBLIC_BASE_URL` 仍应在线上配置为浏览器可访问的后端地址：后端接口响应里的签名链接（未经 `artifactBffUrl` 的调用方、直接调用 API 的客户端、从响应里复制的地址）仍以它为来源。
- 改写只识别主机后直接跟 `/api/chat/artifacts/` 的地址；`SCENEFLOW_PUBLIC_BASE_URL` 带路径前缀的部署不会被改写（这类部署的链接本身可达）。
- 落库链接的 30 天有效期不变，过期后的历史消息链接仍会失效。

## 验证

- `node --no-warnings --experimental-strip-types --test src/lib/artifact-url.test.mts`：**未执行**。新增了 `rewriteArtifactLinks` 用例，但本次会话的命令执行通道在修改后持续不可用。
- `pnpm exec tsc --noEmit`、`pnpm lint`：**未执行**，原因同上。
- 浏览器实测（生成文档后点击下载）与线上环境验证：**未执行**。

## 历史与关联

- 2026-11-19：首次记录并修改前端；未提交。
- 相关：[BUG-20260918-chat-image-tool-result-display](2026-09-18-chat-image-tool-result-display.md)（图片卡片下载改走 `artifactBffUrl`，当时未覆盖正文链接）。
- 配置说明：[本地环境与部署变量](../reference/local-setup.md)。
