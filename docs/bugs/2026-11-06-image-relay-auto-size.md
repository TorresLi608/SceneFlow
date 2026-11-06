# BUG-20261106-image-relay-auto-size：图片中转拒绝自动尺寸

- 首次记录：2026-11-06
- 最近更新：2026-11-06
- 状态：本地复现与修复验证通过；真实中转待重试
- 检索词：图片生成、GIF、GPT Image 2.6、New API、new_api_error、invalid_request、size must use the exact widthxheight format、size=auto、1024x1024

## 现象与复现

用户在图片生成页收到上游 400，安全摘录为 `size must use the exact widthxheight format`，错误类型 `new_api_error`、代码 `invalid_request`。用户未明确本次输出格式；GIF 和自动比例 PNG 都受影响。未保存用户提示词、模型密钥或完整上游响应。

使用真实 OpenAI Python SDK 和 `httpx.MockTransport`，让模拟 New API 对 JSON 文生图或 multipart 图生图中的 `size=auto` 返回上述 400。修复前执行 `test_images` 实际失败并出现同样的错误；未访问真实中转。

## 根因与定位

- [router.py](../../backend/app/llms/router.py) 的 `generate_image` / `edit_image` 为 GIF 固定传 `auto`，PNG 自动比例也会经 `_openai_image_size` 原样透传；未区分官方和兼容中转对尺寸的限制。
- [images.py](../../backend/app/api/v1/images.py) 的 GIF 路径固定自动比例，所以前端选择其他比例也不能避开该请求形态。
- [官方指南](https://developers.openai.com/api/docs/guides/image-generation#generate-animated-gif-output)允许 GIF 的 `auto` 或正整数 `WIDTHxHEIGHT`（边长为 16 的倍数）；不能据此推断中转也支持 `auto`。本会话已读取官方正文，新增功能最初的模拟中转接受所有尺寸，未复现真实中转的这项限制。
- 共享调用方：独立图片、项目封面、角色/道具设定、旧版分镜生成、storyboard/tone 流程、聊天图片工具及模型校验。原生 Gemini/Qwen/Grok 分支在兼容 Images 分支前返回，不受本次尺寸转换影响。

## 修复与影响

- `_openai_image_size` 增加可选 `base_url`，通过解析后的主机名区分 `api.openai.com`；官方与未显式传地址的旧调用保留 `auto`，其他兼容端点将自动尺寸转换为 `1024x1024`。
- 两个共享 Images 入口均传入当前地址，覆盖 GIF 与 PNG、文生图与参考图编辑；PNG 显式尺寸/比例映射保留。转换发生在首次请求前，不增加失败后的自动重试或重复付费调用。
- 图片面板 zh/en 提示说明官方自动选帧尺寸、中转使用 1024×1024。历史的 `ratio=auto` 仍表示编辑器选项；中转实际发送方形尺寸。GIF 原文件、历史、参考图卡片逻辑保持既有行为。
- 更新 [后端参考](../../backend/README.md#images--appapiv1imagespy)、[数据流](../architecture/data-flow.md)和 [实现快照](../plans/current-sprint.md)。无数据库变更。

## 验证

- 修复前：临时媒体目录下 `sh scripts/run_tests.sh test_images` 失败，模拟中转返回同样的尺寸格式 400，已独立复现。
- 修复后：`cd backend`，设置临时 `SCENEFLOW_PRIVATE_GENERATED_DIR`，执行 `sh scripts/run_tests.sh test_images test_generation_records test_storyboard_api test_project_cover test_media_service`：5/5 通过。runner 为每个文件分配临时数据库。
- 真实 SDK + mock transport 覆盖 Sunburst/Flare GIF、2.6/旧模型 PNG、官方和中转地址、JSON 生成和 multipart 编辑；模拟中转继续拒绝 `auto`，修复后单次请求即通过。补充显式像素尺寸及比例映射保留的场景后，独立复跑 `test_images` 通过，共覆盖 24 组实际 SDK 请求组合。
- `cd frontend` 执行 `pnpm exec tsc --noEmit`、`pnpm lint`：均通过。仅更新 zh/en 提示语，未修改 React 布局或交互，未重新运行浏览器回归。
- 使用临时数据库、媒体目录和 `SCENEFLOW_WORKER_ENABLED=0` 重新生成 OpenAPI，修正 GIF 尺寸说明；未变更请求字段或数据库 schema。
- `git diff --check` 通过，涉及文档的 109 个本地 Markdown 链接目标存在性检查通过。
- 未进行付费生成或真实中转调用；本地回归不证明供应商账号、GIF 透传能力及全部动画像素预算可用。

## 历史与关联

- 2026-11-06：在 GPT Image 2.6/GIF 功能交付后的同一会话收到首次真实中转限制反馈，建立本问题记录；与图片历史缩略图加载问题根因不同。
