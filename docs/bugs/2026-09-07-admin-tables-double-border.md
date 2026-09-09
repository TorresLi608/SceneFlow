# BUG-20260907-admin-tables-double-border：管理后台表格双层边框与圆角不一致

- 首次记录：2026-09-07
- 最近更新：2026-09-07
- 状态：已验证
- 检索词：管理后台、Table、border、border-radius、admin/users、admin/usage-logs、admin/error-logs、admin/invitation-codes、admin/redemption-codes、双边框

## 现象与复现
- 影响页面：
  - `http://localhost:4000/admin/users`
  - `http://localhost:4000/admin/usage-logs`
  - `http://localhost:4000/admin/error-logs`
  - `http://localhost:4000/admin/invitation-codes`
  - `http://localhost:4000/admin/redemption-codes`
- 现象：表格外层存在两个重叠的边框（双 border），且外层边框与内层边框的 `border-radius` 不一致（例如外层是 `rounded-lg` 或无圆角，内层是 `rounded-2xl`），导致四角特别是左上角和左下角出现明显的边框错位和重影。
- 复现步骤：登录管理员账号进入上述任一管理后台菜单，观察表格外框轮廓。

## 根因与定位
- 在先前的重构（commit `7a91bcdac396fbdd895b905cacb4068ede15506a`）中，基础组件 `frontend/src/components/ui/table.tsx` 内的 `Table` 已经自带了封装好的卡片式滚动容器：
  `<div data-slot="table-container" className="relative w-full overflow-x-auto rounded-2xl border border-border/80 bg-card/60 shadow-xs backdrop-blur-md dark:border-white/10">`
- 但是 5 个管理后台页面在调用 `<Table>` 时，外层依然保留了历史旧代码中的外层包装容器：
  - `admin-users-manager.tsx`: `<div className="overflow-hidden rounded-lg border">`
  - `admin/usage-logs/page.tsx`: `<div className="overflow-hidden rounded-lg border">`
  - `admin/error-logs/page.tsx`: `<div className="overflow-hidden border">`
  - `invitation-code-manager.tsx`: `<div className="overflow-hidden rounded-2xl border border-border/80 bg-card/60 shadow-xs backdrop-blur-md">`
  - `redemption-code-manager.tsx`: `<div className="overflow-hidden rounded-lg border">`
- 导致每个页面中边框与圆角被嵌套了两层，外层和内层的圆角弧度不匹配，形成了难看的双边框重影。

## 修复与影响
1. `frontend/src/components/ui/table.tsx`：为 `Table` 组件增加可选的 `containerClassName` 属性，方便按需透传容器样式。
2. 移除 5 个管理页面中包裹在 `<Table>` 外层的冗余 `div` 边框容器：
   - `frontend/src/app/(workspace)/admin/users/_components/admin-users-manager.tsx`
   - `frontend/src/app/(workspace)/admin/usage-logs/page.tsx`
   - `frontend/src/app/(workspace)/admin/error-logs/page.tsx`
   - `frontend/src/app/(workspace)/admin/invitation-codes/_components/invitation-code-manager.tsx`
   - `frontend/src/app/(workspace)/admin/redemption-codes/_components/redemption-code-manager.tsx`
3. 影响范围：仅影响这 5 个管理页面的表格外围展示层，使表格恢复统一的精致单层边框与 `rounded-2xl` 圆角，不影响任何业务逻辑、事件响应或数据请求。

## 验证
1. 静态检查：
   - `pnpm exec tsc --noEmit`：通过，无错误。
   - `pnpm lint`：通过，无相关报错。
   - `node --no-warnings --experimental-strip-types --test src/lib/*.test.mts 'src/app/(workspace)/admin/users/_components/user-list.test.mts'`：10 个测试全部通过。
2. 浏览器实际视觉核验：
   - 通过浏览器实际访问 `admin/users`、`admin/usage-logs`、`admin/error-logs`、`admin/invitation-codes`、`admin/redemption-codes` 并截屏比对。
   - 双边框重叠与圆角不一致问题彻底消失，表格外边框全部统一为细腻干净的单层边框，与毛玻璃背景和圆角和谐一致。

## 历史与关联
- 2026-09-07：首次记录并完成修复与多页面视觉回归验证。
