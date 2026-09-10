# BUG-20260910-mobile-responsive-layout：移动端布局与操作区适配

- 首次记录：2026-09-10
- 最近更新：2026-09-10
- 状态：浏览器视口回归及前端检查通过，真机交互待验证
- 检索词：移动端、响应式、320px、横向溢出、侧栏、聊天历史、分镜详情、素材弹窗、英文按钮、dvh、iOS

## 现象与复现

在手机宽度打开工作区，常驻侧栏和生成页多栏布局挤占编辑区；部分操作依赖鼠标悬停。展开分镜详情或素材弹窗后，固定列宽、不可换行的操作区和高度约束会挤压或裁切内容。

收尾检查在 320px 英文界面确认了图片页参考图按钮、角色合并按钮、拆解操作区及分镜详情标题栏溢出。768px 平板上的角色状态输入框只有约 81px 宽。

复测入口：`/chat`、`/images`、`/videos`、`/audio`、`/ai-script`、`/profile`、`/usage`、管理页，以及项目七个子页面、分镜编辑页和旧版工作台。打开手机导航、聊天历史、模型配置表单、素材管理和媒体预览，并展开分镜详情与拆解设置。

## 根因与定位

- [工作区布局](../../frontend/src/app/(workspace)/_components/workspace-shell.tsx)、[项目布局](../../frontend/src/app/projects/[projectId]/(workbench)/layout.tsx)、[旧版编辑器](../../frontend/src/app/projects/[projectId]/_components/workbench-editor.tsx) 分别管理导航，原有固定宽度和 `h-screen` 未统一考虑窄屏与动态视口。
- 三个独立生成面板的滚动策略按桌面并列栏设计；改为上下排列后，需要由外层滚动并保留预览高度。
- [素材管理](../../frontend/src/app/projects/[projectId]/_components/project-asset-manager.tsx) 同时服务项目页面和分镜弹窗，移动端表单不能沿用桌面列内收缩策略。
- [分镜行](../../frontend/src/app/projects/[projectId]/episode/[episodeId]/_components/shot-row.tsx)、[拆解面板](../../frontend/src/app/projects/[projectId]/episode/[episodeId]/_components/breakdown-panel.tsx) 和参考图按钮区缺少换行约束。角色及道具共用的 [MergeButton](../../frontend/src/app/projects/[projectId]/(workbench)/_components/project-cover-field.tsx) 继承了按钮的单行文本样式。
- 角色状态和道具编辑器在 `md` 就显示固定 240px 预览栏，叠加项目侧栏后，平板的表单空间不足。

## 修复与影响

- 工作区和旧版工作台在手机上通过 Dialog 打开导航；聊天历史单独打开，选择会话后关闭；项目导航在手机上横向滚动。桌面折叠侧栏保留链接的可访问名称，Tooltip 直接绑定实际链接或按钮。
- 全屏工作区使用动态视口高度和安全区；窄屏输入框、原生下拉框与提示词编辑器使用 16px 字号。新增文案提供中英两种翻译。
- 生成页在窄屏上纵向排列并滚动；素材表单和列表在窄屏上保留自身高度。弹窗、浮层、预览和表格由各自容器处理滚动。
- 操作按钮和分镜详情标题允许换行；长合并按钮在共享组件内换行，覆盖角色及道具两个调用方。角色状态和道具预览改为 `lg` 起并排，768px 下角色状态输入框实测从约 81px 增至 209px。
- 分镜预览操作支持无悬停设备和键盘焦点；旧版排序手柄设置 `touch-none`。参考素材的单行元信息保留行内图标，避免图标独占一行后裁掉文字。

长期约定见 [响应式布局](../conventions/README.md#responsive-frontend-layouts)。本次未改变生成请求、计费、数据保存和媒体历史的业务流程。

## 验证

2026-09-10 在当前工作区实际执行：

```bash
cd frontend
pnpm exec tsc --noEmit
pnpm lint
node --no-warnings --experimental-strip-types --test src/lib/*.test.mts 'src/app/(workspace)/admin/users/_components/user-list.test.mts'
```

- 类型检查退出码 0。
- lint 退出码 0：0 errors，1 条既有 warning（`src/hooks/use-unsaved-settings-check.ts:6` 的未使用 `Project` 类型）。
- 现有前端检查 13 项全部通过。
- `git diff --check` 通过。

通过浏览器调整视口、测量页面/容器宽度，并抽查截图与交互：

| 视口 | 实测范围 | 结果 |
|---|---|---|
| 320 × 740 | 中文工作区及六个管理页；中英文登录注册；英文聊天、生成页、项目七个子页、展开的分镜详情/拆解设置、旧版工作台 | 最终复测未发现横向溢出；宽表格保留独立滚动 |
| 320 × 740 | 主导航、聊天历史、模型配置表单、素材管理、共享媒体预览 | 可打开和关闭；素材弹窗内容可纵向滚动，预览完整显示 |
| 390 × 844 | 中文项目七个子页和展开的分镜详情 | 未发现横向溢出 |
| 768 × 1024 | 英文分镜编辑、角色、道具、音色、素材页；项目侧栏折叠后切回手机 | 未发现横向溢出；手机导航文字仍显示 |
| 1280 × 800 | 英文图片/视频/音色、模型管理、分镜编辑、聊天折叠导航和素材弹窗 | 未发现横向溢出；桌面布局及导航正常 |

检查包含主导航跳转后关闭、聊天历史开关、Dialog 的 Escape 关闭，以及两类侧栏折叠/展开；测试结束恢复中文与原侧栏展开状态。仅操作界面和读取现有数据，未提交生成、删除或保存业务表单。

仍未验证：iOS/Android 真机键盘、安全区与触摸拖拽；当前浏览器没有独立图片/视频历史，未用真实历史结果打开这两种专用预览弹窗。共享媒体预览已用现有项目图片验证。未运行后端、迁移或生产构建检查，本次没有相关业务或依赖变更。

## 历史与关联

- 2026-09-10：延续此前中断的移动端适配，补齐英文窄屏、平板表单和折叠导航检查，完成当前工作区的验证与记录。未创建提交或 PR。
