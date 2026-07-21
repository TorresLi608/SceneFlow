# SceneFlow AI 短剧 / 漫剧技术方案

> 版本：V0.1（评审稿）  
> 日期：2026-07-21  
> 原则：复用现有栈，先完成单机可恢复 MVP；不在首版引入分布式基础设施。

## 1. 技术结论

SceneFlow 已具备约一半的基础能力：项目/分镜、LLM 剧本处理、真实图片生成、独立文/图生视频、模型配置、用量计费、WebSocket 进度和 AI 对话。主要缺口不是更多模型，而是生产数据模型与可恢复编排：

- 角色/场景/风格资产和引用关系。
- 镜头级结构、版本和参数。
- 真实 TTS、字幕时间轴和媒体合成。
- 将现有视频生成服务接入项目镜头。
- 持久化任务、重试、取消、幂等和恢复。
- 项目级成本估算与质量门禁。

MVP 推荐继续使用 FastAPI + SQLite + Next.js，不先引入 Celery、Redis、Kafka、Temporal 或独立工作流平台。新增 SQLite 任务表和一个有租约的后台 worker，即可支撑当前单机部署；达到多实例或任务吞吐瓶颈后再换队列。

## 2. 当前实现基线（已从代码核实）

### 2.1 前端

- Next.js 16.2、React 19.2、TypeScript、Tailwind 4。
- React Query 负责服务端数据缓存，Zustand 负责用户和项目会话状态。
- assistant-ui + Vercel AI SDK 负责对话与流式消息。
- 已有 `/ai-script`、项目工作台、图片、视频、对话、模型配置、用量和管理页面。
- 项目工作台支持剧本优化/拆分、分镜编辑、拖拽排序、一键生成和 WebSocket 进度。

### 2.2 后端

- FastAPI + SQLite。
- LangChain 模型适配与 agent；对话具有上下文压缩、附件和流式输出。
- 图片支持 OpenAI/Gemini；独立视频支持豆包/Gemini 的文生视频与图生视频。
- 官方/个人模型配置、余额校验、用量日志和价格计算已存在。
- 生成文件写入服务器目录并通过 URL 返回。

### 2.3 当前缺陷

| 位置 | 当前行为 | 对短剧的影响 |
|---|---|---|
| `generation_service.run_generation` | 场景图真实生成，音频为模拟 URL | 无法真实配音和合成 |
| `run_video_generation` | 模拟进度和 `example.com` 视频 | 项目无法产出真实成片 |
| `asyncio.create_task` | 任务只在当前进程内存中 | 重启丢任务，无法可靠重试 |
| `projects/scenes` schema | 只有剧本、旁白、提示词、单图/单音频 | 无角色、镜头、版本、字幕和时间轴 |
| 固定图片提示模板 | 不引用角色/地点/风格资产 | 镜头间一致性差 |
| 场景卡 | 只改旁白和视觉提示 | 缺少镜头控制与资产版本选择 |

## 3. 目标架构

```text
Next.js 项目工作台
  ├─ 剧本/设定/分镜/配音/时间轴/导出
  ├─ React Query：持久化数据
  └─ WebSocket：任务增量事件
            │
FastAPI API ├─ 项目与资产 CRUD
            ├─ 任务创建/取消/重试
            ├─ 成本估算/余额校验
            └─ 导出与下载
            │
SQLite      ├─ 项目业务数据
            ├─ 资产与版本
            ├─ generation_jobs（持久化任务）
            └─ usage_logs（复用）
            │
Worker      ├─ LLM 结构化
            ├─ 图片/视频/TTS 适配器
            ├─ 字幕对齐
            └─ FFmpeg 合成
            │
文件存储    └─ generated/projects/{project_id}/...
```

首版 worker 可与 FastAPI 同一代码库、单独进程启动，也可先同进程启动一个后台循环。数据库任务租约确保进程退出后任务能被重新领取。

### 3.1 对标流程映射

用户补充的候选项目虽无法在当前环境打开核验，但其描述呈现了稳定的行业模块划分，可直接映射到 SceneFlow：

| 行业模块 | 候选项目/产品反复强调的能力 | SceneFlow 实现位置 |
|---|---|---|
| 小说解析/分集 | LumenX、Toonflow、ArcReel、商业 SaaS | 现有 LLM 路由 + 新结构化 schema |
| 编剧/分镜职责 | Multi-Agent 项目、ManjuForge | 一个可恢复结构化工作流，不创建多 Agent 团队 |
| 角色固定 | StoryDiffusion、NanoBanana/参考图类能力 | `characters` + reference asset + provider adapter |
| 多镜头生成 | SkyReels、ShotStream、可灵/Vidu/即梦 | `shots` + 并发 job + 现有视频服务 |
| 配音字幕 | Toonflow、ai_story、NarratoAI 类流程 | audio provider + subtitle cues |
| 自动剪辑 | ArcReel、MoneyPrinterTurbo、商业 SaaS | FFmpeg composition service |
| 批量生产 | ReelMate、MoodMax、工作室型产品 | 持久化 job、失败重试、成本与项目进度 |
| 分发变现 | 爱奇艺/掌阅/火山类平台 | 暂不实现，只保留审核/导出扩展点 |

## 4. 领域模型

保持现有 `projects`、`scenes` 兼容，增量增加真实需要的表。不要一开始建立泛化资产平台。

### 4.1 `projects` 增量字段

| 字段 | 说明 |
|---|---|
| `mode` | `comic` / `drama` |
| `aspect_ratio` | 默认 `9:16` |
| `width`, `height`, `fps` | 导出规格 |
| `target_duration_ms` | 目标时长 |
| `language` | 默认 `zh-CN` |
| `style_prompt` | 全局画风/摄影风格 |
| `negative_prompt` | 全局禁用内容 |
| `current_stage` | 当前生产阶段 |

### 4.2 `characters`

| 字段 | 说明 |
|---|---|
| `id`, `project_id`, `name`, `aliases` | 角色身份 |
| `description` | 年龄、外观、性格、服装等 |
| `voice_config_id` | 绑定声音配置 |
| `reference_asset_id` | 当前角色参考图 |
| `locked` | 是否锁定设定 |

### 4.3 `locations`

- `id`, `project_id`, `name`, `description`, `reference_asset_id`, `locked`。

### 4.4 `scenes` 增量

现有 `scenes` 保留为“场/段落”，增加：

- `location_id`、`time_of_day`、`summary`、`estimated_duration_ms`。

### 4.5 `shots`

每个场景包含多个镜头，是生成和重试的最小业务单元。

| 字段 | 说明 |
|---|---|
| `id`, `scene_id`, `order_num` | 顺序 |
| `shot_type` | 特写/近景/中景/全景等 |
| `camera_angle` | 平视/俯拍/仰拍等 |
| `camera_motion` | 固定/推/拉/摇/移等 |
| `duration_ms` | 目标时长 |
| `visual_prompt`, `negative_prompt` | 镜头提示 |
| `action`, `emotion` | 表演与情绪 |
| `dialogue`, `narration` | 台词与旁白 |
| `status` | 镜头生产状态 |
| `selected_image_asset_id` | 当前分镜图 |
| `selected_video_asset_id` | 当前视频片段 |

### 4.6 `shot_characters`

- `shot_id`, `character_id`, `role`, `appearance_override`。
- 只记录镜头出场角色，不把所有项目设定塞进提示词。

### 4.7 `assets`

统一记录生成/上传文件，不另为图片、音频、视频建三套重复表。

| 字段 | 说明 |
|---|---|
| `id`, `project_id`, `shot_id` | 所属范围 |
| `kind` | `image` / `video` / `audio` / `subtitle` / `export` |
| `purpose` | `character_ref`、`storyboard`、`shot_video`、`voice` 等 |
| `version` | 同一用途的候选版本 |
| `status`, `url`, `local_path` | 文件状态与位置 |
| `provider`, `model_name`, `config_source`, `config_id` | 生成来源 |
| `prompt`, `params_json` | 可复现参数 |
| `duration_ms`, `width`, `height` | 媒体信息 |
| `usage_log_id`, `error_message` | 成本与失败信息 |
| `selected` | 当前选择版本 |

### 4.8 `subtitle_cues`

- `project_id`, `shot_id`, `speaker_character_id`。
- `start_ms`, `end_ms`, `text`, `style_json`。

### 4.9 `timeline_items`

MVP 只需扁平时间轴：

- `track`: `visual` / `voice` / `bgm` / `sfx` / `subtitle`。
- `start_ms`, `duration_ms`, `asset_id`, `transition_json`, `volume`。

不做通用 NLE 数据结构；只支持本产品生成所需的单视觉轨、多音频轨和字幕轨。

### 4.10 `generation_jobs`

| 字段 | 说明 |
|---|---|
| `id`, `user_id`, `project_id`, `shot_id` | 所属对象 |
| `job_type` | `script_structure`、`image`、`video`、`tts`、`compose` 等 |
| `status` | `queued/running/succeeded/failed/canceled` |
| `input_json`, `result_json` | 任务输入/输出 |
| `attempt`, `max_attempts` | 重试控制 |
| `idempotency_key` | 防重复提交 |
| `lease_owner`, `lease_expires_at`, `heartbeat_at` | 崩溃恢复 |
| `progress`, `error_code`, `error_message` | 可观察性 |
| `created_at`, `started_at`, `finished_at` | 时间记录 |

## 5. 工作流编排

### 5.1 不使用复杂多智能体

剧本结构化属于确定的业务步骤，使用现有 LLM 路由 + 结构化 JSON 输出即可。LangGraph 只在需要条件分支、人工确认或恢复时使用；不为每个岗位创建 agent。

### 5.2 项目阶段

```text
draft
  → script_ready
  → bible_ready
  → storyboard_ready
  → preview_ready
  → audio_ready
  → render_ready
  → exporting
  → completed
```

阶段之间允许用户返回修改。修改角色参考图时，只标记引用该角色的下游镜头为 `stale`，不删除历史资产。

### 5.3 任务 DAG

```text
剧本结构化
  ├─ 角色/场景提取
  └─ 场景/镜头拆分
          ↓ 人工确认
角色参考图 ─┐
场景参考图 ─┼→ 分镜图（各镜头可并行）
风格设定 ───┘
          ↓ 人工确认
TTS（按台词并行） ──┐
镜头视频/漫剧运镜 ──┼→ 字幕时间轴 → 低清预览 → 高清导出
BGM/音效 ───────────┘
```

### 5.4 Worker 最小实现

1. API 在事务中写入 `generation_jobs(queued)` 和相关资产占位记录。
2. Worker 原子领取到期/未领取任务，写入租约。
3. 执行期间更新心跳和进度。
4. 成功时事务更新资产、任务和下游状态，并写用量。
5. 可重试错误按退避时间重新入队；参数/余额/内容安全错误直接失败。
6. 重启后租约到期的 `running` 任务可再次领取。

MVP 使用 SQLite 单 worker。`ponytail` 上限：当部署多实例、并发任务较高或 SQLite 写锁成为实测瓶颈时，再迁移 PostgreSQL + 专用队列/工作流系统。

## 6. 生成服务适配

### 6.1 模型能力接口

不要为每个厂商复制业务流程。现有 `app/llms` 保留文本模型，新增小而明确的媒体接口：

```python
generate_image(request) -> MediaResult
generate_video(request) -> MediaResult | ProviderTask
generate_speech(request) -> MediaResult
```

请求包含统一字段和 `provider_options`，只有供应商专属参数进入后者。

### 6.2 图片生成

复用现有 OpenAI/Gemini 图片能力，补充：

- 参考图片列表。
- 角色/场景/风格引用。
- seed（供应商支持时）。
- 输出数量与候选版本。
- 负面提示词。
- 图生图 strength/denoise（供应商支持时）。

第一版不承诺跨供应商完全一致的参数语义。

### 6.3 视频生成

直接复用现有 `video_service.generate_video`，把每个 `shot` 转成请求：

- 默认使用已选分镜图做图生视频，提高一致性。
- 没有分镜图时才允许文生视频。
- 供应商不支持目标时长时，按支持时长生成，再由 FFmpeg 裁剪/定格补齐。
- 低清草稿与高清成片使用不同任务和资产版本。
- 项目级 `generate-video` 不再生成一个模拟全片，而是批量创建镜头视频任务，最后合成。

### 6.4 TTS

将模型配置 `purpose` 扩展为 `audio`，复用官方/个人配置、加密、默认选择、余额和用量体系。

首版实现一个真实供应商即可，接口预留：

- `text`, `voice_id`, `language`。
- `speed`, `pitch`, `emotion`（供应商支持时）。
- 返回音频、时长和可选字词时间戳。

如果 TTS 不返回字词时间戳，MVP 可按标点/字符比例生成字幕时间，后续接 WhisperX 做精确对齐。

### 6.5 漫剧运镜

不调用视频大模型也能完成：

- FFmpeg zoompan 实现推拉。
- crop/translate 实现横移和纵移。
- 两张图之间使用淡入淡出/叠化。
- 根据语音时长确定图片持续时间。

这是 P0 默认路径；视频模型只用于用户主动升级的镜头。

## 7. 一致性方案

### 7.1 Prompt Bible

项目保存结构化设定，而非只保存一段长提示词：

- 视觉风格：媒介、色彩、光线、镜头语言。
- 角色：固定身份描述、服装、发型、年龄和参考图。
- 地点：建筑、陈设、时间和参考图。
- 镜头：只描述当前动作、构图和情绪。

最终提示词由服务端按固定顺序组合，避免每个页面自行拼接。

### 7.2 参考图优先

- 先为角色生成/上传设定图并锁定。
- 分镜图引用出场角色和场景参考图。
- 短剧镜头默认以选中分镜图作为首帧/参考图。
- 用户更换角色参考图时，下游镜头标记为过期，由用户决定是否重生成。

### 7.3 可插拔高级后端

若供应商参考图能力不足，再增加 ComfyUI HTTP 适配器，用 InstantID/PhotoMaker/PuLID/LoRA 等工作流。首版不把 ComfyUI 节点暴露到产品 UI，也不把它设为必需依赖。

## 8. 字幕、时间轴与合成

### 8.1 FFmpeg 合成步骤

1. 规范化所有视觉资产的分辨率、帧率、像素格式和音频采样率。
2. 漫剧镜头按目标时长生成视频片段；短剧镜头裁剪或补帧。
3. 按顺序 concat 镜头，应用简单转场。
4. 混合角色语音、旁白、BGM 和音效，做音量 ducking。
5. 通过 ASS/SRT 烧录字幕或输出外挂字幕。
6. 输出 H.264/AAC MP4 和封面图。

### 8.2 MVP 时间轴限制

- 单视觉主轨。
- 旁白/对白共用 voice 轨或按片段混合。
- 一个 BGM 轨、一个 SFX 轨、一个字幕轨。
- 支持裁剪、静帧延长、音量、淡入淡出和基础转场。
- 不实现任意多轨、关键帧曲线或专业调色。

## 9. API 设计

沿用 `/api/projects/{project_id}`，主要增加：

### 项目设定

- `PATCH /api/projects/{id}/production-settings`
- `POST /api/projects/{id}/structure`
- `GET/POST/PATCH /api/projects/{id}/characters`
- `GET/POST/PATCH /api/projects/{id}/locations`

### 镜头与资产

- `GET/POST/PATCH /api/projects/{id}/shots`
- `POST /api/projects/{id}/shots/{shot_id}/generate-image`
- `POST /api/projects/{id}/shots/{shot_id}/generate-video`
- `POST /api/projects/{id}/shots/{shot_id}/generate-audio`
- `POST /api/projects/{id}/shots/{shot_id}/assets/{asset_id}/select`

### 批量任务

- `POST /api/projects/{id}/jobs/storyboards`
- `POST /api/projects/{id}/jobs/audio`
- `POST /api/projects/{id}/jobs/videos`
- `POST /api/projects/{id}/jobs/preview`
- `POST /api/projects/{id}/jobs/export`
- `GET /api/projects/{id}/jobs`
- `POST /api/jobs/{job_id}/retry`
- `POST /api/jobs/{job_id}/cancel`

### 成本

- `POST /api/projects/{id}/estimate`
- `GET /api/projects/{id}/usage-summary`

WebSocket 继续使用项目频道，事件统一为：

- `JOB_UPDATE`
- `ASSET_UPDATE`
- `SHOT_UPDATE`
- `PROJECT_UPDATE`

## 10. 前端实现映射

### 10.1 复用

- 复用现有 workspace 布局、项目列表、设置弹窗、模型配置、用户状态和用量页面。
- 复用 `project-store` 的项目选择与 WebSocket 增量更新，但持久化实体由 React Query/API 作为事实来源。
- 复用现有分镜卡的编辑、排序、图片预览和状态 UI，扩展为镜头卡。
- 复用图片/视频独立页面的参数表单和结果展示组件；抽取共享组件时必须出现真实重复后再做。
- 复用对话面板作为项目 AI 导演助理。

### 10.2 新增页面状态

- 项目阶段页签：剧本、设定、分镜、配音、时间轴、导出。
- 镜头详情抽屉：参数、参考资产、候选版本、成本、错误和重试。
- 任务中心：只展示当前项目任务，不先做全站队列后台。
- 时间轴：先实现业务限定的轨道组件，不引入重型 NLE 编辑器。

## 11. 成本与余额

### 11.1 估算

根据选定模型价格和计划数量估算：

- LLM：预估输入/输出 token。
- 图片：镜头数 × 候选数 × 单图价格。
- 视频：镜头秒数 × 单位价格。
- TTS：字符数或音频秒数 × 单位价格。
- 估算显示区间，避免假精确。

### 11.2 扣费

- 任务创建时校验余额，不提前写最终用量。
- 每个真实供应商调用完成后继续复用 `record_usage`。
- 批量任务中余额不足时停止创建新供应商调用，保留已完成结果。
- 重试会产生新用量，UI 必须明确提示。

## 12. 安全与数据边界

- 所有项目、角色、镜头、资产和任务 API 校验 `user_id` 所有权。
- 文件路径由服务器生成，不接受客户端任意写入路径。
- 上传限制 MIME、扩展名、大小和像素/时长，避免媒体炸弹。
- 外部素材和模型输出视为不可信输入；FFmpeg 使用参数数组，不拼 shell 字符串。
- 私有资产使用现有签名下载思路；公开 `/generated` 只用于用户明确允许公开的内容。
- 保存供应商返回的任务 ID，但不保存明文 API key。
- 加入内容安全结果和人工复核状态；供应商拒绝应显示明确原因。

## 13. 可观察性与错误分类

### 错误码

- `INVALID_INPUT`
- `INSUFFICIENT_BALANCE`
- `CONTENT_REJECTED`
- `PROVIDER_RATE_LIMITED`
- `PROVIDER_FAILED`
- `PROVIDER_TIMEOUT`
- `MEDIA_INVALID`
- `COMPOSE_FAILED`
- `CANCELED`

### 日志字段

- `job_id`, `project_id`, `shot_id`, `user_id`。
- provider/model/config source。
- attempt、耗时、供应商任务 ID、错误码。
- 不记录 API key、完整私密剧本或上传文件正文。

## 14. 测试策略

遵循仓库当前无测试框架的可执行自检风格，首版至少增加：

1. 剧本结构 JSON 校验与无效模型输出回退。
2. 任务领取、租约过期恢复、幂等和取消。
3. 角色/镜头所有权和引用完整性。
4. 图片/视频/TTS 供应商适配器的 mock 响应。
5. 批量任务部分失败只重试失败镜头。
6. 余额不足在真实调用前停止。
7. FFmpeg 生成 2–3 个极短测试片段并合成，校验文件存在、时长和音轨。
8. WebSocket 事件能驱动前端任务/镜头状态更新。
9. 前端 lint、TypeScript 和关键状态 reducer 自检。

## 15. 实施顺序

### Phase A：真实漫剧闭环

1. 数据库迁移：项目设置、角色、地点、镜头、资产、任务。
2. 剧本结构化和设定/分镜 UI。
3. 持久化 job worker 与 WebSocket 事件。
4. 参考资产驱动的分镜图生成和版本选择。
5. 真实 TTS、字幕时间轴。
6. FFmpeg 漫剧预览/导出。
7. 项目成本估算和汇总。

### Phase B：镜头视频化

1. 将现有 `video_service` 接到 shot job。
2. 分镜图 → 图生视频。
3. 视频裁剪、补时长、版本选择。
4. 低清预览/高清导出。

### Phase C：一致性与连续剧

1. ComfyUI/高级参考控制适配（有实际需求再加）。
2. 唇形同步/表演驱动。
3. 多集 bible、连续性检查和团队审核。

## 16. 文件级开发建议

预计优先修改/新增的最小范围：

- `backend/app/core/database.py`：增量表和迁移。
- `backend/app/services/project_service.py`：项目设定与领域校验。
- `backend/app/services/generation_service.py`：拆分为任务入口，删除模拟音频/视频。
- `backend/app/services/video_service.py`：复用，不重写供应商调用。
- `backend/app/services/usage_service.py`：项目估算/汇总辅助函数。
- `backend/app/api/v1/projects.py`：镜头、资产和任务 API。
- `backend/app/core/realtime.py`：统一任务事件，无需更换协议。
- 新增一个 `job_service.py` 和一个 worker 入口即可；不建仓库级“工作流框架”。
- 前端在现有项目路由下增加阶段组件，避免新增平行应用。

## 17. 开发门禁

开始实现前必须确认：

- FFmpeg 可用性和部署方式。
- 首个 TTS 供应商及商用许可。
- 图片/视频供应商的参考图、时长、并发和内容安全限制。
- 所选开源模型/组件许可证及权重商用条款。
- 单机 SQLite worker 是否符合首发部署规模；若首发即多实例，应直接使用 PostgreSQL 和独立 worker。

## 18. 本轮刻意跳过

- 没有引入新的依赖或修改业务代码。
- 没有设计通用 DAG DSL、插件系统或多智能体团队。
- 没有把所有供应商参数强行抽象成完全一致。
- 没有实时核验易变化的价格、星数和 API 细节；这些属于开发启动前的短期核验任务。
