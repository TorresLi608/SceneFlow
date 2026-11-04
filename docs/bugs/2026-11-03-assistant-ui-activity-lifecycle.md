# BUG-20261103-assistant-ui-activity-lifecycle：Activity 恢复时 assistant-ui 重复清理资源

- 首次记录：2026-11-03
- 最近更新：2026-11-03
- 状态：已验证；最小旧版复现、新版对照及实际 Next 菜单切换通过
- 检索词：Tried to unmount a fiber that is already unmounted、AssistantRuntimeProvider、useResources、tap、Activity、remount

## 现象与复现

用户在 workspace 的聊天面板反馈运行时错误，代码帧指向 `assistant-composer.tsx` 的 `AssistantRuntimeProvider`。出错时使用 Next.js 16.2.3/Turbopack、React 19.2.4、assistant-ui react 0.14.24、tap 0.9.3。

已独立复现的最小场景：Activity 内的 memo 子组件调用 `useResources([withKey("x", swapped ? Second() : First())])`，其中 First/Second 是不同的 `resource` hook。可见时替换 hook → 隐藏 → 恢复，tap 0.9.3 抛出相同的重复卸载错误。单纯切换不替换资源的输入框未稳定复现，不能用它代替该场景。

## 根因与定位

异常来自 `@assistant-ui/tap/src/core/ResourceFiber.ts::unmountResourceFiber`，不是 React 自身的 fiber 错误。旧版 `useResources` 在处理 `next.remount` 后未将 pending 标记归一，Activity 的 effect 恢复再次执行旧的 remount 分支，试图清理已在隐藏时清理过的资源。

官方 tap 0.9.24 的 `useResources` 在提交后将 `state.next` 设为 `"skip"`，对已存在但断开的资源重新 commit，并通过 `useHostLifecycle` 管理资源释放。其发布包包含 `src/__tests__/react/activity.test.tsx` 的 hook 替换及隐藏恢复用例。

受影响入口：[assistant-composer.tsx](../../frontend/src/app/(workspace)/chat/_components/assistant-composer.tsx) → `AssistantRuntimeProvider` → assistant-ui store/tap；面板由 [ActivityView](../../frontend/src/components/ui/activity.tsx) 管理可见性。

## 修复与影响

更新 [frontend/package.json](../../frontend/package.json) 和 pnpm 锁文件，使用官方配套组合：react 0.15.32、core 0.3.32、store 0.3.22、tap 0.9.24、react-streamdown 0.3.21（这里的 react 指 `@assistant-ui/react`；应用 React 仍为 19.2.4）。react-streamdown 同步升级以满足其 peer 范围。保留 Activity 和现有请求控制器结构，不修改 node_modules、不吞掉清理错误。

仅更新 tap 曾引出旧 core 的另一项独立缺陷，详见 [运行时快照循环](2026-11-03-assistant-ui-runtime-snapshot.md)。长期约定见 [聊天设计](../design/feature-chat.md#session-instances-and-workspace-activity)。

## 验证

- `/private/tmp/sceneflow-activity-check/resource-swap.tsx`：esbuild 编译同一 React 19.2.4 案例，分别绑定官方 tap 0.9.3 tarball 和安装的 0.9.24。旧版执行“Swap resource → Toggle Activity → Toggle Activity”后页面显示两条 `Tried to unmount...`；新版同条件显示 `second` 并保持可操作。临时静态页由本机 4183 端口提供。
- 实际 Chrome 中运行的 Next.js 16.2.3/Turbopack 应用：更新配套依赖并刷新后，填写未发送草稿，聊天 → 图片 → 聊天共四轮，草稿保持、可继续输入，验证时间段内无新增重复卸载/快照循环错误。测试草稿随后清理，不发送消息。
- `cd frontend && pnpm exec tsc --noEmit`：通过。
- `cd frontend && pnpm lint`：通过。
- `cd frontend && node --no-warnings --experimental-strip-types --test src/lib/*.test.mts 'src/app/(workspace)/admin/users/_components/user-list.test.mts' 'src/app/(workspace)/chat/_components/chat-message-state.test.mts'`：25/25 通过。
- 未执行生产构建；未调用付费模型/真实生成接口，未修改本地数据库或生成文件；未穷举所有资源组合。此前隔离面板验证范围的修订见 [workspace 记录](2026-11-03-workspace-page-state-reset.md#2026-11-03后续-assistant-ui-兼容性回归)。
