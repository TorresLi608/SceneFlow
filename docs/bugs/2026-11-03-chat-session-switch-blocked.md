# BUG-20261103-chat-session-switch-blocked：问答进行中无法切换或新建会话

- 首次记录：2026-11-03
- 最近更新：2026-11-03
- 状态：已通过前端检查及隔离浏览器模拟验证；真实模型未调用
- 检索词：智能问答、切换会话、新建对话、回答生成中、isBusy、isSending、agentSteps、useChat、Chat 实例、chat-session-registry、chat-runtime-store、chat-runtime、runningSessionIds

## 现象与复现

- 用户反馈（2026-11-03）：“智能问答在问答过程中，不能对其他的问答进行切换和操作以及新增新问答。”
- 复现：会话 A 发送问题，回答流式输出期间：侧栏“新对话”按钮禁用；点击会话 B 能切换，但输入框仍禁用、执行流程面板显示的是 A 的步骤；再切回 A 时正在生成的回答消失，只剩刷新后的历史记录。同时切换到其他菜单再回来也会丢失（见 [BUG-20261103-workspace-page-state-reset](2026-11-03-workspace-page-state-reset.md)）。

## 根因与定位

- 已确认：[use-chat-controller.ts](../../frontend/src/app/(workspace)/chat/_components/use-chat-controller.ts) 只有一个 `useChat({ id: effectiveSessionId })`。`@ai-sdk/react` 在 `id` 变化时重建 `Chat` 实例，旧实例的流在后台继续但 UI 不再订阅；切回时又是一个新实例，只能从查询结果恢复已持久化的消息。
- 已确认：`isSending`、`agentSteps`、`errorMessage`、`stoppedRef` 都是控制器级状态而不是按会话；`isBusy = 创建中 || 删除中 || isSending || isStreaming` 同时禁用新建按钮和所有会话的发送。

## 修复与影响

- 新增 [chat-session-registry.ts](../../frontend/src/app/(workspace)/chat/_components/chat-session-registry.ts)：模块级 `Map<sessionId, Chat>`，共享一个 `DefaultChatTransport`（headers 每次请求从 user-store 读取 token，`prepareSendMessagesRequest` 逻辑不变）。`onData` / `onError` 写入对应会话的运行状态；`remove` 在删除会话时停止并移除实例；token 变化时 `clear`，避免换号后看到或继续推送上一账号的会话。服务端渲染不缓存实例。
- 新增 [store/chat-runtime-store.ts](../../frontend/src/store/chat-runtime-store.ts)（按会话的 `agentSteps` / `error` / `isSending` / `stopped`，内存态）与 [lib/chat-runtime.ts](../../frontend/src/lib/chat-runtime.ts) 纯函数（步骤合并、停止标记、运行中会话列表，附单测）。
- `use-chat-controller.ts` 改为 `useChat({ chat: registry.ensure(当前会话) })`：切换会话只是换订阅，A 的流继续跑，回到 A 能看到实时或已完成的回答，流结束后的常规查询失效再与持久化消息对齐。`isBusy` 只覆盖当前会话；新建会话流程先创建、选中、再向该会话自己的实例发送，乐观用户消息不会留在被丢弃的占位实例里；`stop` 作用于当前实例；运行中的会话拒绝删除。
- [chat-sidebar.tsx](../../frontend/src/app/(workspace)/chat/_components/chat-sidebar.tsx)：新建按钮只在创建请求进行中禁用；运行中的会话显示脉冲标记（`chat.sessionRunning`），其删除按钮禁用并提示（`chat.deleteRunningSession`）。[chat-panel.tsx](../../frontend/src/app/(workspace)/chat/_components/chat-panel.tsx) 传入 `isCreatingSession` 与 `runningSessionIds`。两组文案 zh/en 均已加入 `lib/i18n.ts`。
- 共享的消息转换函数移至 `chat-ui-messages.ts`，控制器与注册表共用。
- 已知限制：同一会话仍一次只允许一轮；运行中的会话要等结束后才能删除；实例在切换后不再重建，一个会话上次失败的错误提示会按会话保留直到下次发送。
- 长期规则：[feature-chat · One instance per session](../design/feature-chat.md#session-instances-and-workspace-activity)、[boundaries](../architecture/boundaries.md#layout-and-chat-composition)、[overview · State ownership](../architecture/overview.md#state-ownership)。

## 验证

- 2026-11-03 最终改造已通过类型检查、lint、23 个 Node 测试及隔离浏览器模拟验证；具体命令、覆盖场景和未验证范围见下方记录。
- 初版静态审查中发现的 TS2322 和 React Compiler 不可变性 lint 错误已在 Activity 改造中解决；初版未做浏览器验证。

## 2026-11-03：Activity 兼容及验证

- `ChatPanel` 将视图放入官方 Activity，但 `useChatController` 留在边界外，保持 query/mutation 和 AI SDK 订阅；隐藏的 composer/消息列表 effect 清理。共用浮层读取 Activity 可见性，离开后移除历史弹窗等 Portal。
- transport 的 `headers` 回调显式返回 `Record<string, string>`，解决审查中实际触发的 TS2322。
- 控制器读取 `useSearchParams`；显式 `?chat=A` 导航覆盖旧选择，无参数菜单地址恢复最近会话。URL 写入检查当前实际 pathname 并跳过相同参数，后台请求不会抢占其他菜单。
- `pnpm exec tsc --noEmit`、`pnpm lint`：通过；前端约定测试加聊天失败状态测试共 23/23 通过，完整命令见 [工作区记录](2026-11-03-workspace-page-state-reset.md)。
- 隔离浏览器使用实际 ChatPanel/controller/registry 和模拟 AI SDK SSE：A 发送后切 B 发送，两会话均显示运行标记且禁止删除；仍可新建 C。切到 usage 后完成 A/B 的流，再按 `?chat=A`、`?chat=B` 返回，分别显示完整 A/B 回复。浏览器后退到 `?chat=A` 后仍展示 A，未被旧选择 B 覆盖。
- 未调用真实模型/后端，未做完整 Next 路由器或生产构建验证；Activity/Portal 共同边界见 [工作区记录](2026-11-03-workspace-page-state-reset.md)。
