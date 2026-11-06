# BUG-20261106-image-history-preview-stale：切换历史记录时旧图残留

- 首次记录：2026-11-06
- 最近更新：2026-11-06
- 状态：前端检查、25 项测试及隔离浏览器回归通过
- 检索词：图片生成、历史记录、A 切 B、旧图残留、文图错位、next/image、onLoad、key、加载状态、乱序响应

## 现象与复现

在独立图片生成 `/images` 页先打开历史 A，再打开加载较慢的历史 B。提示词和参数立即变为 B，但预览继续显示 A 的像素，直到 B 下载完成才替换。用户反馈与源码行为吻合；本次不依赖真实账号或付费生成进行验证。

## 根因与定位

- [image-generation-panel.tsx](../../frontend/src/app/(workspace)/images/_components/image-generation-panel.tsx) 切换历史时同步更新 `imageUrl`、提示词和其他参数，但主预览复用同一个 `next/image` / DOM 图片节点，只更新 `src`。浏览器可能在新图片就绪前保留旧图片内容。
- 主预览未维护图片加载状态，顶部还直接显示 `Ready`。全屏预览同样没有图片加载与失败状态。
- 这与 [历史缩略图加载压力](2026-11-04-image-history-loading.md) 的根因不同：本问题发生在选中结果的原图预览，不涉及分页、缩略图和后端生成。

## 修复与影响

- 新增路由内 [image-result-preview.tsx](../../frontend/src/app/(workspace)/images/_components/image-result-preview.tsx)，供主预览和全屏预览使用；由当前显示 URL 作为 React key，让图片 DOM 和加载状态在切换时一起重建。旧节点卸载后的完成事件不会更新当前实例。
- 新图片在 `onLoad` 前不可见，同时显示有 `role=status` 的加载提示；`onError` 显示错误提示而非残留旧图或停在加载状态。加载完成后显示原图，保留 `unoptimized` 对 GIF 的支持。已缓存图片仍走 Next Image 的完成处理。
- 去掉仅凭 URL 存在就显示的 `Ready` 文案，保留清晰度标签；错误时仍可使用原有下载入口。新增提示均在 zh/en 字典中。
- 修改仅涉及前端选中结果预览，原图签名、历史分页、缩略图、下载、生成请求及数据库契约保持既有行为。

## 验证

- `cd frontend`：`pnpm exec tsc --noEmit`、`pnpm lint` 均通过。
- `cd frontend`：`node --no-warnings --experimental-strip-types --test src/lib/*.test.mts 'src/app/(workspace)/admin/users/_components/user-list.test.mts' 'src/app/(workspace)/chat/_components/chat-message-state.test.mts'`：25/25 通过。这是现有逻辑回归，图片切换本身通过下述浏览器检查验证。
- Playwright 临时 fixture 位于 `/private/tmp/sceneflow-history-switch-check/`，打包实际图片面板、实际 Next Image、React Compiler、React Query 和应用 CSS，历史/API/媒体使用模拟数据；本地服务和测试浏览器经沙箱授权启动。
- 主动暂停 B/C 图片响应：A 加载完后选 B，确认提示词变为 B、A 图片 DOM 已断开、新节点 `naturalWidth=0` 且不可见、加载状态可见；再选 C，放行迟到的 B，确认当前节点仍为 C 且保持加载状态；放行 C 后其图片正常显示。
- 主动请求不存在的图片，验证错误提示出现且旧图不会显示；再切回 A 能正常显示。暂停 GIF 响应并打开全屏，验证全屏同样有加载状态；放行后主预览和全屏都加载成功，GIF 格式标签仍正常。
- 验证桌面中文 1440×1000 加载状态、手机英文 390×844 错误状态，无页面横向溢出。截图 `b-loading.png`、`c-loaded.png`、`lightbox-loading.png`、`mobile-error-en.png` 在临时 fixture 内。浏览器仅出现两次预期的 `broken.png` 404，无额外应用错误。
- 后端和 API 未改，无需 schema/OpenAPI 变更；本次未重跑后端套件。
- `git diff --check` 通过，163 个本地 Markdown 链接目标存在性检查通过（检查器修正为支持路由路径中的括号）。
- 未调用真实生成服务，未操作真实历史记录或媒体。

## 历史与关联

- 2026-11-06：用户首次反馈切换历史的文图错位；查阅历史加载问题后确认为独立预览生命周期问题并单独建档。
