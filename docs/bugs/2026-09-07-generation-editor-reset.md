# BUG-20260907-generation-editor-reset：生成页面无法退出历史编辑状态

- 首次记录：2026-09-07
- 最近更新：2026-09-07
- 状态：已修复；本地表单和历史保留验证通过，文件选择自动验证受限
- 检索词：重置、图片生成、视频生成、音色生成、历史记录、预览、React key
- [返回 Bug 索引](README.md)

## 现象与复现

图片/视频生成页选择历史记录后，提示词和结果预览被填入，但没有恢复新建编辑状态的入口，只能刷新页面。音色页也缺少统一重置入口，而且未选择音色时会自动回退到第一条已保存音色。

复现：打开生成页，选择一条历史记录，修改提示词或参数，尝试返回空白编辑。音色页另需覆盖已有保存音色时的空选择状态。

## 根因与定位

三个面板各自持有表单、参考素材、文件输入、预览和 mutation 等临时状态，没有统一的新建/重置边界。音色的 `effectiveSavedVoiceId` 还把空选择解析成列表首项。

对应入口：

- [video-generation-panel.tsx](../../frontend/src/app/(workspace)/videos/_components/video-generation-panel.tsx)
- [image-generation-panel.tsx](../../frontend/src/app/(workspace)/images/_components/image-generation-panel.tsx)
- [voice-generation-panel.tsx](../../frontend/src/app/(workspace)/audio/_components/voice-generation-panel.tsx)

## 修复与影响

每个面板保留一个轻量入口组件，以递增的 React `key` 重新挂载内部编辑器。新增“重置”按钮，恢复初始参数和默认模型选择，清空输入、参考素材、预览、错误及临时编辑状态；原生文件输入也随编辑器重新创建。

图片/视频历史仍保存在各自的 localStorage 中（最近 20 条），重置重新读取，不删除。保存音色仍由后端和 React Query 管理。移除音色空选择自动回退到首项的行为，使重置后的预览保持为空。

生成/提示词优化进行中禁用重置，音色保存/删除期间同样禁用。按钮文字和说明写入 [i18n.ts](../../frontend/src/lib/i18n.ts) 的中英文词典；未增加依赖或通用表单框架。

## 验证

- 实际视频页：选择历史记录、添加本地参考图链接后重置，提示词/参考选择/预览清空，原有 2 条历史保留；没有提交生成请求。
- 实际图片页：选择历史记录后重置，提示词和预览清空，原有 5 条历史保留。
- 实际音色页：填写名称、描述、试听文本后重置，三项清空且生成按钮禁用。当前账号没有保存音色，因此没有将真实历史音色选择记为已实测。
- 临时 Node 检查生产组件的 `effectiveSavedVoiceId` 表达式：即使保存列表非空，空选择/已失效选择仍保持为空，合法选择保持选中。通过。
- `cd frontend` 后运行 `pnpm exec tsc --noEmit`：通过；`pnpm lint` 为 0 错误、1 个既有未使用导入警告。

文件选择自动验证被 Chrome 扩展的文件 URL 访问权限拒绝；之后扩展面板也阻止了浏览器自动化继续。未将本地文件上传/重选、进行中状态或模拟接口检查标记为通过。所有实际页面验证均未调用收费生成，也未删除历史或保存音色。

## 历史与关联

- 2026-09-07：用户报告视频历史编辑必须刷新，并要求图片/音频一起补齐；三个面板统一增加重置行为。
- 同次交付的参数问题：[模型不支持 FPS](2026-09-07-video-unsupported-fps.md)。
- 状态所有权见 [架构概览](../architecture/overview.md#state-ownership)，页面入口见 [代码地图](../architecture/code-map.md)。
