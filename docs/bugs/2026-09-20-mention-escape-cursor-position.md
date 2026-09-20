# BUG-20260920-mention-escape-cursor-position：MentionTextarea 按 Esc 后光标跳至输入框开头

- 首次记录：2026-09-20
- 最近更新：2026-09-20
- 状态：已验证
- 检索词：MentionTextarea、PromptArea、Combobox、Escape、Esc、光标位置、cursorPosition、finalFocus、FloatingFocusManager

## 现象与复现

- **影响的页面/组件**：剧集编辑器分镜列表行（[shot-row.tsx](file:///Users/torresli/Documents/other/SceneFlow/frontend/src/app/projects/[projectId]/episode/[episodeId]/_components/shot-row.tsx)）以及提示词前缀管理（[prompt-prefix-list.tsx](file:///Users/torresli/Documents/other/SceneFlow/frontend/src/app/projects/[projectId]/episode/[episodeId]/_components/prompt-prefix-list.tsx)）中的 [mention-textarea.tsx](file:///Users/torresli/Documents/other/SceneFlow/frontend/src/app/projects/[projectId]/episode/[episodeId]/_components/mention-textarea.tsx)。
- **触发条件**：用户在输入框内键入 `@` 调出素材引用下拉菜单，随后按下 `Esc` 键或点击关闭按钮取消选择。
- **实际表现**：下拉列表关闭后焦点回到输入框，但光标跳回到了整个输入框的最开头位置（offset 0）。
- **预期表现**：光标停留在触发 `@` 时的当前位置不变，用户可无缝继续输入。

## 根因与定位

1. **触发机制**：`PromptArea` 配置了 `triggers` 为 `@` 且 `mode: "launch"`。键入 `@` 时 `openMention` 记录了当时的字符偏移量 `context.cursorPosition`、编辑器 DOM 节点 `editor` 及选区 `range`，随后弹出 Base UI `Combobox`。
2. **失焦与回焦行为**：进入 Combobox 后焦点转移至搜索框；关闭浮层时，Base UI 的 `FloatingFocusManager` 在微任务中通过 `finalFocus` 调用了 `mention.editor.focus({ preventScroll: true })`。
3. **浏览器默认选区表现**：原生 `contenteditable` 容器元素直接调用 `.focus()` 且未指定选区时，浏览器默认将光标折叠至容器首个子节点起始位置（offset 0）。
4. **缺乏光标还原逻辑**：原代码在取消/关闭 Combobox 时没有调用任何选区或光标还原逻辑。

## 修复与影响

- **代码修改**：
  1. 在 [mention-textarea.tsx](file:///Users/torresli/Documents/other/SceneFlow/frontend/src/app/projects/[projectId]/episode/[episodeId]/_components/mention-textarea.tsx) 中引入 `promptAreaRef = useRef<PromptAreaHandle>(null)` 并绑定至 `<PromptArea ref={promptAreaRef} />`。
  2. 使用 `activeMentionRef` 缓存最新激活的 mention 上下文数据。
  3. 实现 `restoreCursor` 与 `closeMentionAndRestore`：先调用 `editor.focus()`，优先通过 `promptAreaRef.current.setCursorPosition(context.cursorPosition)` 精确还原光标偏移量，回退使用保存的 DOM Range；并在同步、`queueMicrotask`、`requestAnimationFrame` 多周期中执行，防止被 Base UI 微任务聚焦覆盖。
  4. 严格隔离“取消选择”与“选择素材”两种场景：通过 `isSelectingRef` 守卫，在 `onValueChange` 选中素材时插入 chip 并让光标停留在素材之后；仅在用户按 `Escape` 键或点击关闭按钮取消时才执行 `restoreCursor` 还原到 `@` 之前的位置。
- **涉及调用方**：所有使用 `MentionTextarea` 的输入场景（分镜生图提示词、视频提示词、前缀提示词）。
- **限制与边界**：外部点击（outside press）正常让出焦点至用户点击的目标，不抢夺焦点。

## 验证

- `pnpm exec tsc --noEmit`：通过，退出码 0，无类型错误。
- `pnpm lint`：通过，退出码 0，0 错误。
- `node --no-warnings --experimental-strip-types --test src/lib/*.test.mts 'src/app/(workspace)/admin/users/_components/user-list.test.mts'`：14 项测试全部通过。

## 历史与关联

- 2026-09-20：首次创建并完成修复验证。随后对选择素材与取消操作进行严格解耦隔离，确保选中素材后光标自动保持在参考素材之后。
