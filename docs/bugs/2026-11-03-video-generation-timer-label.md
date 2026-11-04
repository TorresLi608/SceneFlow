# BUG-20261103-video-generation-timer-label：视频生成计时显示翻译键

- 首次记录：2026-11-03
- 最近更新：2026-11-03
- 状态：前端检查及隔离浏览器模拟验证通过
- 检索词：视频生成、计时、i18n、videos.generatingVideoWithSeconds、videos.generatingWithSeconds

## 现象与复现

视频生成期间应显示已用秒数，实际显示 `videos.generatingVideoWithSeconds`，无法观察计时。Activity 改造的隔离浏览器验证中复现。

## 根因与定位

`videos/_components/video-generation-panel.tsx` 请求不存在的翻译键；`lib/i18n.ts` 的 zh/en 实际都定义为 `videos.generatingWithSeconds`。已搜索旧键，无其他调用方。

## 修复与影响

仅将面板调用改为既有键，不增加文案。Activity 计时恢复另见 [工作区记录](2026-11-03-workspace-page-state-reset.md)。

## 验证

- 隔离浏览器使用实际视频面板和模拟接口：生成中切到 usage 后返回，显示“正在生成视频 172s”，没有从零重新计时。
- `cd frontend && pnpm exec tsc --noEmit`、`pnpm lint`、约定 Node 测试及聊天状态测试共 23/23：通过，完整命令见工作区记录。
- 未调用真实视频模型。
