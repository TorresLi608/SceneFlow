# BUG-20260910-chat-error-thinking-state：报错后思考区域仍然存在

- 首次记录：2026-09-10
- 最近更新：2026-09-10
- 状态：已修复，前端回归与本地模拟流浏览器验证通过
- 检索词：智能问答、思考框、模型思考、执行流程、agentSteps、onError、reasoning

## 现象与复现

在 `/chat` 发送消息，收到执行步骤或思考内容后让请求失败。页面出现错误提示，但执行流程仍保留运行状态，本轮未完成的“模型思考”也继续显示。预期报错后清除本轮思考区域，保留历史消息、已生成正文和下一条草稿。

## 根因与定位

- [use-chat-controller.ts](<../../frontend/src/app/(workspace)/chat/_components/use-chat-controller.ts>) 的 AI SDK `onError` 只设置错误文字，没有清理独立保存的 `agentSteps`。
- [后端聊天流](../../backend/app/api/v1/chat.py) 在异常时追加独立的 `runtime_error` 步骤，不会逐一结束先前的运行步骤；网络失败也可能收不到终止步骤。因此客户端必须在请求失败时结束临时展示。
- AI SDK 保留失败回复中的已接收片段；[chat-message-list.tsx](<../../frontend/src/app/(workspace)/chat/_components/chat-message-list.tsx>) 根据非空 `reasoning` 渲染思考框，单独更新错误提示不会移除它。

## 修复与影响

- 在统一的流错误回调中清空执行步骤，通过 [clearFailedReasoning](<../../frontend/src/app/(workspace)/chat/_components/chat-message-state.ts>) 仅移除最后一条助手消息的思考片段，保留正文、其他片段和历史消息。尚未收到助手消息时不改变消息列表。
- 发送流程外层异常同样清空临时步骤；正常回复和主动停止仍保留各自的完成／停止状态。
- `useChatController` 由 [ChatPanel](<../../frontend/src/app/(workspace)/chat/_components/chat-panel.tsx>) 唯一调用，其消息同时传给自定义消息列表与 assistant-ui composer；修复在状态入口完成，无需分别修改两个消费者。
- 行为约定更新在 [聊天设计](../design/feature-chat.md)。

## 验证

2026-09-10 实际执行：

```bash
cd frontend
node --no-warnings --experimental-strip-types --test src/lib/*.test.mts 'src/app/(workspace)/admin/users/_components/user-list.test.mts' 'src/app/(workspace)/chat/_components/chat-message-state.test.mts'
pnpm exec tsc --noEmit
pnpm lint
```

- 14 项前端检查通过，包含新增的失败思考清理回归：保留历史思考和部分正文，不修改原消息；HTTP 失败前没有助手消息时保持原列表。
- 类型检查通过。lint 退出码 0，只有原有 `src/hooks/use-unsaved-settings-check.ts:6` 的未使用 `Project` 类型警告。
- 浏览器通过临时本机代理加载真实前端组件，并使用内存中的模拟会话及受控 AI SDK 流。先收到思考与运行步骤，再触发流错误：两处思考区域消失，错误提示仍在，下一条草稿和焦点保留。随后正常回复及流开始前 HTTP 502 的场景也通过，历史思考未被清除。
- 相关后端检查在隔离数据库／媒体目录中通过：

```bash
cd backend
check_dir=$(mktemp -d /tmp/sceneflow-chat-check.XXXXXX)
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh test_chat_balance test_agent_service
```

未调用真实模型供应商；浏览器验证使用模拟流，不代表已复现用户的具体供应商故障。

## 历史与关联

- 2026-09-10：根据用户报告和源码确认状态清理缺失，完成修复与上述验证。
- 修复已包含在当前本地提交 [`fda218c`](https://github.com/TorresLi608/SceneFlow/commit/fda218c2b1f53b9551cb4fd1ceec70614c0e49b0)；未验证远端推送状态。
- 同次处理：[发送后的输入框焦点与草稿](2026-09-10-chat-composer-draft-focus.md)。
