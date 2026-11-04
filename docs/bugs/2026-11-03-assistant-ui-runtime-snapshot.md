# BUG-20261103-assistant-ui-runtime-snapshot：assistant-ui 线程快照不缓存导致循环

- 首次记录：2026-11-03
- 最近更新：2026-11-03
- 状态：已验证；前端检查、25 项测试及实际 Next 菜单切换通过
- 检索词：The result of getSnapshot should be cached to avoid an infinite loop、Maximum update depth exceeded、AssistantRuntimeProvider、ThreadListRuntimeImpl、LazyMemoizeSubject

## 现象与复现

排查 [Activity 重复卸载](2026-11-03-assistant-ui-activity-lifecycle.md) 时，先将 tap 从 0.9.3 更新到 0.9.24，而 assistant-ui core 仍为 0.2.19。随后用户反馈 `AssistantRuntimeProvider` 出现快照缓存警告，实际页面继续产生 Maximum update depth 错误，输入也会触发循环。

该依赖组合在隔离的真实 ChatPanel 模拟页也出现同一循环；不是用户业务请求或模型响应造成的。

## 根因与定位

实际 Next 错误面板展开调用链：tap `useSyncExternalStore` → core `useSubscribable` → `useThreadListClient` → `RuntimeAdapter` → `AssistantRuntimeProvider`。

core 0.2.19 的 `ThreadListRuntimeImpl` 通过 `LazyMemoizeSubject` 实现 `getState()`，但 `subscribe()` 直接连 core，绕过了该 subject。subject 因此一直认为未连接，每次读取都创建新的线程列表对象。tap 0.9.24 增加了快照一致性检查和 commit 后的变化检查，将这个既有缺陷暴露为警告及循环。只提升 Provider 或缓存调用方的 props 不能修复库内快照契约。

官方 core 0.3.32 让 subscribe 经由 `_stateBinding`，并在未连接时通过浅比较复用不变快照、重新连接时标记为待刷新。核对了 0.2.23，仍包含旧逻辑，因此最终更新完整的官方兼容依赖组合。

## 修复与影响

- [frontend/package.json](../../frontend/package.json)：`@assistant-ui/react` 从 `^0.14.24` 到 `^0.15.32`；`@assistant-ui/react-streamdown` 从 `^0.3.5` 到 `^0.3.21`，满足配套 peer 范围。pnpm 锁定 core 0.3.32、store 0.3.22、tap 0.9.24 及其依赖。
- [assistant-runtime.test.mts](../../frontend/src/lib/assistant-runtime.test.mts)：通过公共 `useExternalStoreRuntime` 和 React 服务端渲染创建实际 runtime，验证线程列表/线程/composer 在无订阅、订阅中、取消订阅及重新订阅时的快照引用稳定性，并验证草稿修改会更新状态且不被取消订阅清空。该测试验证快照契约，不代替浏览器 Activity 测试。
- 保留 AI SDK 消息所有权、assistant-ui 输入/附件所有权和 Activity 边界；未添加业务层快照包装或屏蔽警告。更新了 [聊天设计](../design/feature-chat.md)、[代码地图](../architecture/code-map.md) 及 [当前状态](../plans/current-sprint.md)。

## 验证

- 旧组合在实际 Next.js 16.2.3/Turbopack 页面和隔离模拟页确认循环；展开调用链确认了具体 `useThreadListClient` 来源。
- 新组合的实际 Next 页面刷新后输入草稿、聊天 → 图片 → 聊天四轮，草稿保留并可编辑；从本次刷新后的验证时段筛选 console，无新增相关错误。没有通过修改应用业务代码规避 Activity。
- `cd frontend && pnpm exec tsc --noEmit`：通过。
- `cd frontend && pnpm lint`：通过。
- `cd frontend && node --no-warnings --experimental-strip-types --test src/lib/*.test.mts 'src/app/(workspace)/admin/users/_components/user-list.test.mts' 'src/app/(workspace)/chat/_components/chat-message-state.test.mts'`：25/25 通过，含新增 2 项 runtime 回归。
- 更新过程中用过的纯空数组测试 fixture 在类型检查中推导为 never，现显式指定 `ExternalThreadMessage`，最终检查通过。
- 未执行生产构建、未调用真实聊天/生成接口、未写入测试聊天或新增用户数据。浏览器结果只覆盖已执行路径；模型调用、附件解析和所有历史消息格式没有全量回放。
