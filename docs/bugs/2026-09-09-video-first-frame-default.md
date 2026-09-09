# BUG-20260909-video-first-frame-default：生成分镜图后视频默认填充首帧

- 首次记录：2026-09-09
- 最近更新：2026-09-09
- 状态：已修复，类型检查和现有回归通过；浏览器交互未验证
- 检索词：首帧、分镜图、视频提示词、`videoFirstFrame`、`shot-row`
- [返回 Bug 索引](README.md)

## 现象与复现

生成分镜图后打开剧集镜头编辑器，支持首帧的视频模型会自动把当前镜头分镜图显示为视频首帧。预期是首帧保持未选择，除非用户手动选择或已有保存选择。

## 根因与定位

`frontend/src/app/projects/[projectId]/episode/[episodeId]/_components/shot-row.tsx` 的 `effectiveFirstFrame` 在没有保存值时用 `scene.image.url` 推导首帧。保存和单镜生成视频都使用这个推导值，因此分镜图生成后会被带入视频请求。

## 修复与影响

删除自动推导及 `firstFrameTouched`；首帧下拉框、脏状态和保存请求只使用 `videoFirstFrame` 的保存值或本地手动选择。唯一调用方为剧集 `page.tsx`，单镜生成通过 `saveBeforeGenerate` 保存编辑内容，批量生成仍读取后端已保存配置。

后端 `projects.py::_scene_payloads` 只解析已保存首帧，`generation_service.py::_render_scene_video` 将其传给 provider；分镜图生成仅更新图片状态/路径，不设置首帧。上述后端逻辑未改动，仅同步相关注释。已有首帧不自动清除，手动选择和显式清空继续保留。旧镜头的 `defaultVideoReferencePaths` 仍可能将分镜图作为普通参考图，和本次首帧槽位不同；见[视频数据流](../architecture/data-flow.md#6-shots--video-clips)。

## 验证

- `git diff --check`：通过。
- `cd frontend` 后执行 `pnpm exec tsc --noEmit`：通过。
- `pnpm lint`：0 错误，1 个既有警告（`src/hooks/use-unsaved-settings-check.ts` 未使用的 `Project` 导入）。
- `node --no-warnings --experimental-strip-types --test src/lib/*.test.mts 'src/app/(workspace)/admin/users/_components/user-list.test.mts'`：11 项通过；这些纯模块检查不覆盖首帧 UI 交互。
- 以下后端隔离检查通过，覆盖保存首帧、无关编辑保留首帧和显式清空；使用临时数据库和媒体目录：

```bash
cd backend
validation_dir=$(mktemp -d /private/tmp/sceneflow-first-frame.XXXXXX)
SCENEFLOW_PRIVATE_GENERATED_DIR="$validation_dir/media" sh scripts/run_tests.sh test_projects_api
```

未进行浏览器交互或真实付费生成验证；未新增 UI 测试框架。

## 历史与关联

2026-09-09：移除分镜图到视频首帧的默认填充，并同步数据流文档。
