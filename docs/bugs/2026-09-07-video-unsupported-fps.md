# BUG-20260907-video-unsupported-fps：视频表单发送模型不支持的 FPS

- 首次记录：2026-09-07
- 最近更新：2026-10-21
- 状态：已修复；参数序列化、视频回归和类型检查通过，未调用真实付费模型
- 检索词：Doubao、Seedance 2.0、Gemini、Veo、Developer API、`selected model does not support fps=24`、`/api/bff/videos/generate`、`selectedFps`
- [返回 Bug 索引](README.md)

## 现象与复现

独立视频生成页选择声明 `videoCapabilities.fps: []` 的模型后，界面不显示 FPS 控件，但提交仍携带 `fps: 24`，后端返回 `selected model does not support fps=24`。用户使用的是 Seedance 2.0 系列。

[官方教程](https://docs.volcengine.com/docs/82379/2291680?lang=zh) 的请求示例配置比例、时长等参数，没有 FPS 入参。固定的输出帧率不能当作可配置的请求参数。

## 根因与定位

[video-generation-panel.tsx](../../frontend/src/app/(workspace)/videos/_components/video-generation-panel.tsx) 的 `selectedFps` 在模型允许列表为空时使用 `?? 24` 回退，随后 `generate` 无条件把这个值放入请求。控件是否显示与请求值选择使用了不同逻辑。

[video-generation-actions.ts](../../frontend/src/actions/video-generation-actions.ts) 按原样发送表单请求；[video_service.py](../../backend/app/services/video_service.py) 的 `resolve_video_options` 正确拒绝显式传入的非法 FPS。项目批量视频路径已有 `supported_video_defaults`，不是本次错误的入口。

## 修复与影响

移除表单的硬编码 `24` 回退。支持 FPS 的模型仍选择允许值；不支持时得到 `undefined`，JSON 序列化不产生 `fps` 字段。历史记录和预览元数据也不再填入虚构的 24 FPS。

保留后端对显式非法 FPS 的拒绝，不把不支持的参数伪装成支持。在 [test_video_service.py](../../backend/tests/test_video_service.py) 中补充“选项解析为无 FPS 后，豆包请求体不含 fps”的断言。

## 验证

- `cd frontend` 后执行 `pnpm exec tsc --noEmit`：通过。
- `pnpm lint`：0 错误；有一个既有警告，位于未修改的 `use-unsaved-settings-check.ts`，为未使用的 `Project` 导入。
- 用临时 Node 校验读取生产组件的 `selectedFps` 表达式并检查 JSON 序列化：空允许列表不产生 FPS 字段；允许 `[30]` 时回退为 30；合法的 60 保留。通过。
- `test_video_service`：通过，包含新增的豆包请求体断言。

实际执行的后端命令：

```bash
cd backend
validation_dir=$(mktemp -d /private/tmp/sceneflow-media-tests.XXXXXX)
SCENEFLOW_PRIVATE_GENERATED_DIR="$validation_dir/media" sh scripts/run_tests.sh test_video_service test_config_service
```

其中 `test_config_service` 的既有 `test_video_capabilities_are_normalized_and_stored` 断言失败：期望字典缺少 `supportsFirstFrame`、`supportsLastFrame`、`supportsStartEndFrames`，其余已断言字段无差异。该测试及后端配置实现未被本次修改，不能将这次运行报告为整个配置测试通过。

真实页面已确认当前模型不显示 FPS 控件。模拟浏览器请求验证因 Chrome 扩展面板阻止自动化而未完成；不将其记为通过。没有调用真实收费生成接口。

### 2026-10-21 实际验证

- `cd backend; check_dir=$(mktemp -d /private/tmp/sceneflow-gemini-check.XXXXXX); SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh test_gemini_video test_video_service test_config_service test_project_production`：四项全部通过。测试运行器为每项创建临时数据库，未使用本地真实数据库或媒体目录。
- `cd frontend; pnpm exec tsc --noEmit && pnpm lint`：均通过，无警告。
- `git diff --check`：通过。
- 官方 SDK 测试使用真实序列化器和 HTTP MockTransport；中转测试覆盖 `/v1/videos`、404 后的旧任务路由、轮询、同源内容下载、跨源结果 URL 不携带网关 Key、任务失败/缺少 ID/HTTP 500/超时不重复提交。没有使用真实 Google、Sub API 或 New API 付费账号联调，也未执行浏览器交互验证。

## 历史与关联

- 2026-10-21：新增 Gemini 视频模型管理与中转调用时，核对已安装 Google Gen AI SDK 确认 Developer API 拒绝非空 `fps`，而原 Gemini 默认能力为 `[24]`，适配器也直接传入。现新增 Veo 目录及前后端 Gemini 默认能力均声明 `fps: []`；官方适配器省略该字段，旧配置中的 24 也不再发送。影响独立视频及项目视频共享调用；不改变 HTTP 选项解析对显式非法 FPS 的拒绝。`test_gemini_video` 使用真实 SDK 序列化及 MockTransport 校验带旧值 24 的调用、轮询和下载，验证记录见下方；调用方式见 [Backend reference](../../backend/README.md)。
- 2026-09-07：根据用户错误报告定位到前端默认值与能力列表不一致，修正并执行上述检查。
- 同次交付的另一问题：[生成编辑器重置](2026-09-07-generation-editor-reset.md)。它与 FPS 参数错误是不同根因。
- 长期规则见 [数据流](../architecture/data-flow.md#6-shots--video-clips)：独立视频表单也必须遵守模型能力，不能为不支持的选项填默认值。
