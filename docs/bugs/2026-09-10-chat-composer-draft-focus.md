# BUG-20260910-chat-composer-draft-focus：发送后无法继续编辑且焦点恢复过晚

- 首次记录：2026-09-10
- 最近更新：2026-09-10
- 状态：已修复，类型检查与本地模拟流浏览器验证通过
- 检索词：智能问答、输入框、焦点、草稿、禁用发送、isSendDisabled、isSending、assistant-composer

## 现象与复现

在 `/chat` 点击发送，上一条回复仍在生成时尝试编辑下一条消息。输入框被整体禁用，无法继续输入，发送按钮点击后的焦点也要等整轮请求结束才恢复。预期发送后立即聚焦输入框，允许编辑下一条草稿，但当前请求结束前禁止再次发送。

## 根因与定位

- [ChatPanel](<../../frontend/src/app/(workspace)/chat/_components/chat-panel.tsx>) 将 `isBusy` 作为 [AssistantComposer](<../../frontend/src/app/(workspace)/chat/_components/assistant-composer.tsx>) 的整体 `disabled`，同时禁用 runtime、文本框和附件编辑。输入能力与发送能力混为一体。
- composer 在 `await onSend()` 后的 `finally` 才聚焦；[控制器](<../../frontend/src/app/(workspace)/chat/_components/use-chat-controller.ts>) 的发送 Promise 包含会话创建、完整回复和查询刷新，焦点恢复因此过晚。
- 原 `isBusy` 只覆盖流状态及显式的新建／删除会话操作，没有覆盖首次发送自动创建会话的等待阶段。解除输入禁用后，该阶段也需要禁止提交下一条草稿。

## 修复与影响

- 将唯一调用方的参数改为 `sendDisabled`，传给现有 assistant-ui `isSendDisabled`。输入框和附件编辑保持可用；发送按钮及 Enter 提交沿用库的发送限制，生成时仍显示停止按钮。
- `handleNew` 开始发送时立即聚焦文本框，不再等回复完成后聚焦。下一条草稿仍由 assistant-ui 管理，不会随上一条回复结束而清空。
- 控制器增加覆盖完整发送 Promise 的 `isSending`，并在 `finally` 释放。自动创建会话、流式回复及刷新期间均属于忙碌状态。
- 保持 AI SDK 管理消息与流、assistant-ui 管理 composer 的边界，见 [聊天设计](../design/feature-chat.md)。

## 验证

2026-09-10 实际执行的类型检查、14 项前端检查及两项相关后端检查均通过；完整命令见同次 [错误状态记录的验证部分](2026-09-10-chat-error-thinking-state.md#验证)。`pnpm lint` 退出码 0，只有已有的未使用 `Project` 类型警告。

使用真实页面组件和临时本机模拟 API，浏览器实际验证：

1. 暂缓首次会话创建响应：点击发送后焦点立即回到文本框，输入下一条草稿成功，发送按钮禁用，Enter 不提交。
2. 放行会话创建并保持回复流开启：草稿和焦点保留，仍可输入；再次按 Enter 后流请求计数仍为 1。
3. 模拟流错误：草稿保留，发送恢复；从草稿继续发送成功。
4. 正常回复结束：期间输入的下一条草稿仍在，发送恢复；Enter 可正常开始下一轮。
5. 主动停止：草稿保留，执行流程显示“已停止”，发送恢复。
6. 流开始前 HTTP 502：错误提示出现，草稿和发送时获得的焦点保留。

未单独验证真实供应商、移动端软键盘及附件读取期间的交互；没有新增 DOM 测试框架或依赖。

## 历史与关联

- 2026-09-10：根据用户要求分离编辑和发送限制，完成源码核对与上述验证。
- 同次处理：[报错后的思考区域](2026-09-10-chat-error-thinking-state.md)。
