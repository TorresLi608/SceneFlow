# BUG-20261103-workspace-page-state-reset：切换菜单后生成页面状态丢失

- 首次记录：2026-11-03
- 最近更新：2026-11-03
- 状态：已通过前端检查及隔离浏览器模拟验证；真实生成未调用
- 检索词：菜单切换、页面缓存、生成中、视频生成、图片生成、音色设计、keep-alive、KeepAlivePages、keep-alive-routes、display: none、unmount、cacheComponents、Activity

## 现象与复现

- 用户反馈（2026-11-03）：“上一秒还在生成视频，然后切换到其他菜单，再回来生成中的视频就变成新的页面了，需要重新生成，其他的菜单也类似。”
- 影响页面：`/videos`、`/images`、`/audio`，以及 `/chat`（问答部分另见 [BUG-20261103-chat-session-switch-blocked](2026-11-03-chat-session-switch-blocked.md)）。
- 复现：在 `/videos` 填写提示词并点击生成 → 生成中点击侧栏任意其他菜单 → 再点回 `/videos`。预期回到生成中的页面并最终看到结果；实际表单、计时、生成中状态和预览全部回到初始值。后端请求并未取消，结果最终只出现在历史列表里。

## 根因与定位

- 已确认：Next.js App Router 在路由切换时卸载上一路由的页面组件。`videos/page.tsx` 等直接渲染 `VideoGenerationPanel`，提示词、参数、`generateMutation`、`elapsedSeconds` 计时、`requestController` 等全部是组件内 `useState`/`useRef`，组件一卸载就丢失；axios 请求继续执行，但 `onSuccess` 更新的是已经卸载的组件。
- 已核对备选方案：Next 16.2.3 的 `cacheComponents: true` 会用 React `<Activity>` 保留最近访问的路由（见 `node_modules/next/dist/docs/01-app/02-guides/preserving-ui-state.md`），但它同时切换 ppr/useCache/dynamicIO 渲染模型、只保留约 3 个路由、且隐藏时卸载 effect（轮询和计时暂停）。未全局启用；先提升到共享 layout，后按下方历史记录改为各面板视图使用官方 Activity。

## 修复与影响

- 新增 [lib/keep-alive-routes.ts](../../frontend/src/lib/keep-alive-routes.ts)：常驻路由 `/chat`、`/images`、`/audio`、`/videos` 的匹配与访问记录纯函数，附单测。
- 新增 [(workspace)/_components/keep-alive-pages.tsx](../../frontend/src/app/(workspace)/_components/keep-alive-pages.tsx)：由 `WorkspaceShell` 渲染，首次访问时挂载对应 controller；各面板用 [components/ui/activity.tsx](../../frontend/src/components/ui/activity.tsx) 的官方 `<Activity>` 隐藏视图。保留 DOM/草稿/滚动位置并清理隐藏 UI 的 effect；请求相关的 query/mutation hooks 保留在边界外，防止丢失 pending mutation 的状态更新。删除原手写显隐/滚动 Map。
- `chat/page.tsx`、`images/page.tsx`、`audio/page.tsx`、`videos/page.tsx` 改为只占 URL、返回 `null`；原页面内容移至各路由的 `_components/chat-surface.tsx`、`image-surface.tsx`、`audio-surface.tsx`、`video-surface.tsx`。每个 surface 仍自行发起 `userConfigs` 查询，宿主本身不取数，符合“在需要数据的表面取数”的约定。
- [workspace-shell.tsx](../../frontend/src/app/(workspace)/_components/workspace-shell.tsx) 的内容区同时渲染 `<KeepAlivePages />` 与 `{children}`；非常驻路由（usage、profile、admin/*）仍走 `children`。
- 聊天控制器只在 `/chat` 为当前路径时同步 `?chat=` 参数，避免常驻的聊天页把参数写进其他菜单的 URL。
- 已知限制：离开 `(workspace)` 布局（进入 `/projects/*` 工作台或退出登录）仍会卸载这些 surface；非生成类菜单不做常驻。
- 长期规则：[boundaries · Layout and chat composition](../architecture/boundaries.md#layout-and-chat-composition)、[overview · State ownership](../architecture/overview.md#state-ownership)、[code map](../architecture/code-map.md)、[AGENTS.md](../../AGENTS.md#ownership-to-preserve)。

## 验证

- 2026-11-03 最终改造已通过类型检查、lint、23 个 Node 测试及隔离浏览器模拟验证；具体命令、覆盖场景和未验证范围见下方记录。
- 初版静态审查中发现的 TS2322 和 React Compiler 不可变性 lint 错误已在 Activity 改造中解决；初版未做浏览器验证。

## 2026-11-03：改用官方 Activity

- 用户要求评估后直接改造；保持四个菜单按需挂载，不开启全局 `cacheComponents`、不引入第三方 KeepAlive 库。
- 源码确认 TanStack Query 5.101.2 的 `MutationObserver.onUnsubscribe` 移除 observer，而 `onSubscribe` 不重新连接原 mutation；因此把整个请求面板放入 Activity 会让 pending 状态失去更新。现保留编辑器/controller 的 query/mutation hooks，在其返回的视图层放 Activity，而非新造任务队列/状态库。
- Activity 不会自动暂停媒体，也无法隐藏位于视图 DOM 根之外的 Portal。`ActivityView` 的 layout cleanup 暂停内联 audio/video，并调用面板关闭预览/历史弹窗；可见性 Context 让共用 Dialog/Select/Popover/Tooltip 根在隐藏时卸载，默认值 `true` 保持其他调用方的行为。
- 图片/视频计时器仅在菜单可见且 mutation pending 时运行，重新显示后从 `submittedAt` 计算真实已用时间（隔离浏览器返回后实际显示视频已用 172s，未从零重启）；视频 `autoPlay` 由 `active` 限制，后台完成不会自动出声。视频计时翻译键另见 [计时文案记录](2026-11-03-video-generation-timer-label.md)。
- 聊天 URL 显式参数由 `useSearchParams` 同步回选择状态；无参数菜单入口恢复最近会话，后台回调不会把用户拉回 `/chat`。相关类型错误也已修复。

### 实际验证

- `cd frontend && pnpm exec tsc --noEmit`：通过。
- `cd frontend && pnpm lint`：通过。
- `cd frontend && node --no-warnings --experimental-strip-types --test src/lib/*.test.mts 'src/app/(workspace)/admin/users/_components/user-list.test.mts' 'src/app/(workspace)/chat/_components/chat-message-state.test.mts'`：23/23 通过。
- 隔离浏览器页使用实际 `KeepAlivePages`、四个面板、React 19.2.4 和 React Query 5.101.2，替换 Next 导航/动态导入和 HTTP/SSE 接口为本地模拟；`StrictMode` 开启。临时 fixture 位于 `/private/tmp/sceneflow-activity-check/`，用 esbuild 编译，`python3 -m http.server 4183 --bind 127.0.0.1 --directory /private/tmp/sceneflow-activity-check` 提供页面。
- 已实际通过：图片/视频/音色隐藏期间完成后恢复结果与表单；隐藏期间失败后恢复错误且可再次操作；视频后台完成时 `paused=true`、`autoplay=false`；音频从播放切页后 `paused=true`；图片预览 Dialog 和语言 Select 在浏览器后退后移除；草稿保留，滚动位置隐藏前后均为 100px。
- 聊天跨会话并发、创建 C、后台完成和 URL 历史验证见 [会话记录](2026-11-03-chat-session-switch-blocked.md)。
- 未连接真实后端、未调用付费模型、未改动本地数据库或生成文件；模拟导航不覆盖完整 Next 开发/生产路由器，刷新/离开工作区布局仍会重置页面本地状态。

## 2026-11-03：后续 assistant-ui 兼容性回归

- 用户随后反馈 `AssistantRuntimeProvider` 报 `Tried to unmount a fiber that is already unmounted`。旧版隔离面板测试没有覆盖资源 hook 替换后再隐藏/恢复；此前的通过记录不能证明该场景可用。
- 最小资源替换案例现已在 tap 0.9.3 复现相同错误，在 0.9.24 同条件恢复正常；见 [生命周期记录](2026-11-03-assistant-ui-activity-lifecycle.md)。仅更新 tap 又暴露 core 0.2.19 的快照缓存缺陷，改用官方配套版本后修复；见 [快照记录](2026-11-03-assistant-ui-runtime-snapshot.md)。
- 最终依赖组合在实际 Next.js 16.2.3/Turbopack 页面完成聊天 → 图片 → 聊天共四轮切换；输入草稿保留，回到聊天后可继续编辑，检查期间无新增重复卸载/快照循环错误。未发送真实聊天、未调用生成接口。
- 最终类型检查、lint 和 25 个 Node 测试结果见上述两条记录；Activity/controller 的结构与请求所有权保持原方案。
