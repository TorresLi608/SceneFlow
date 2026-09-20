# BUG-20260920-unauthorized-projects-redirect：未登录访问 projects 工作台菜单未重定向到登录页

- 首次记录：2026-09-20
- 最近更新：2026-09-20
- 状态：已修复，类型检查、Lint 与单测通过
- 检索词：未登录、跳转登录、AuthGuard、projects、workbench、redirect、401、路由守卫

## 现象与复现
在未登录状态（即 localStorage 中无有效 token）下直接访问 `frontend/src/app/projects` 内部的各菜单（如 `/projects/[projectId]/info`、`characters`、`props`、`voices`、`assets`、`episodes`、`videos` 以及 `/projects/[projectId]/episode/[episodeId]` 等）时，页面不会跳转到登录页面，而是直接尝试挂载组件并请求项目接口，触发大量 401 失败并在界面产生未授权错误或异常空白；而访问 `(workspace)` 下的菜单（如 `/chat`、`/images`）能够正常拦截并跳转至 `/login`。

## 根因与定位
1. **鉴权守卫分散且覆盖缺失**：
   - 之前仅在 `frontend/src/app/(workspace)/_components/workspace-shell.tsx` 和单页编辑器 `workbench-editor.tsx` 内部手写了 `useEffect` 检查；
   - `frontend/src/app/projects/[projectId]/(workbench)/layout.tsx`（覆盖 7 个工作台子菜单）与 `frontend/src/app/projects/[projectId]/episode/[episodeId]/page.tsx`（分集分镜编辑器）完全没有接入任何登录状态检查和跳转逻辑。
2. **缺乏全局统一的客户端路由守卫**：
   - SceneFlow 的 Token 采用客户端 Zustand + `localStorage` 持久化，服务端 Next.js Middleware 无法直接读取客户端 `localStorage`；
   - 未在顶层 Provider 链中建立统一的 Client `AuthGuard`，导致新路由和 `(workspace)` 组外的路由必须逐一重复手写拦截逻辑，容易发生遗漏。

## 修复与影响
1. **新建全局统一鉴权守卫**：
   - 在 `frontend/src/lib/auth-guard-utils.ts` 中集中管理公开路由白名单（`["/login", "/register"]`）、`isPublicRoute`、`buildLoginRedirectUrl` 与 `resolveSafeRedirectUrl`（严格校验站内相对路径，防止开放重定向漏洞）；
   - 在 `frontend/src/providers/auth-guard.tsx` 中实现 `AuthGuard` 组件，在 Zustand 存储尚未完成水合（`!hydrated`）时展示统一的初始化加载状态，并在无 token 或 token 失效（`meQuery.isError`）时阻断受保护页面挂载并重定向至 `/login?redirect=...`；
   - 在 `frontend/src/app/layout.tsx` 中将 `<AuthGuard>` 包裹在 `QueryProvider` 内部，统一覆盖全站所有页面路由。
2. **支持登录后回跳原页面**：
   - 在 `frontend/src/app/login/page.tsx` 中，登录成功后使用 `resolveSafeRedirectUrl` 解析 `redirect` 参数并安全回跳，优化未登录访问直接跳转后的使用体验。
3. **消除冗余重复逻辑**：
   - 清理 `WorkspaceShell` 和 `WorkbenchEditor` 内部重复冗余的鉴权重定向判断，复用全局 `AuthGuard` 的统一保障。

## 验证
1. 执行自动化单测与静态检查：
   ```bash
   cd frontend
   pnpm exec tsc --noEmit
   pnpm lint
   node --no-warnings --experimental-strip-types --test src/lib/*.test.mts 'src/app/(workspace)/admin/users/_components/user-list.test.mts'
   ```
   结果：17 项测试全部通过（含新增的白名单判断、重定向 URL 构造、防开放重定向单测），TypeScript 与 ESLint 检查 0 错误通过。

## 历史与关联
- 2026-09-20：首次排查并建立全局统一的 Client `AuthGuard` 机制，彻底解决 `projects` 菜单及未来新页面免手写鉴权的问题。
