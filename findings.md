# Findings & Decisions

## Session 2026-07-21: Admin User Role Selection

- User creation now accepts only `user` or `superAdmin`; omitted role defaults to `user`.
- The management form exposes a role select defaulting to ordinary user and resets to that default after success.
- Regression checks cover the default role, super-admin creation, and rejection of unknown roles.

## Session 2026-07-21: Admin All Usage Records

- Added a super-admin-only paginated usage-log endpoint joining `usage_logs` with `users`.
- Username search uses a parameterized SQLite `LIKE '%term%'` match.
- Reused the existing usage serializer, table, money formatter, pagination, and permission patterns.
- Added `/admin/usage-logs` with username search, clear filter, model/source/token/cost columns, and pagination.
- Backend self-check covers fuzzy username matching and page boundaries.

## Session 2026-07-21: Balance Enforcement and Usage Audit

### Requirements

- Audit today's frontend/backend changes and self-test the business flow.
- Ordinary users using official model configurations must be blocked when balance is insufficient and receive a clear message.
- Personal model configurations remain usable without balance, but usage and estimated cost must still be recorded.
- Usage logs need an all/official/personal source filter, defaulting to all.
- Redeeming a code must refresh globally consumed balance data without introducing a state machine unless the existing store genuinely needs one.
- New users default to level 1.
- List status filters must have an obvious clear/reset path.
- Fix unreasonable design discovered in scope and record changes for future handoff.
- Reorganize the backend so tests and service modules have clear homes, following common FastAPI/open-source conventions without a cosmetic full rewrite.

### Initial Decisions

| Decision | Rationale |
|----------|-----------|
| Reuse the existing Zustand user store and React Query `me` cache | Balance is server-owned account data; a new state machine would duplicate existing state and add synchronization risk. |
| Enforce official-model balance on the backend before provider calls | The backend is the trust boundary and prevents bypass from any client. |
| Keep personal-model cost as usage accounting only | Matches the requirement: record estimated cost without deducting or blocking personal configuration usage. |
| Add the smallest focused regression checks | Money and authorization paths require executable coverage; avoid a new test framework. |
| Treat personal usage as token/quantity accounting, not currency estimation | Personal configs define no pricing. Inventing a monetary price would be misleading; source, tokens, quantity, and duration remain visible and filterable. |
| Reorganize tests and services only | These are real existing categories; moving every root module into invented layers would create churn without improving the current product. |

### Research Findings

- Existing planning files predate this session; this session is appended instead of overwriting them.
- `findings.md` was missing from the current workspace even though older logs referenced it, so it was recreated for this audit.
- Current `record_usage` deducts official cost only after the provider call and clamps balance at zero; there is no preflight guard, so a zero-balance ordinary user can currently call an official model.
- Personal configurations already record source, provider, model, duration, tokens, cache tokens, quantity, and unit metadata. Their monetary `costMicros` is zero because personal configurations have no pricing fields; they are counted but not billed.
- Official execution is resolved through two paths: shared helpers in `config_service.py` for image/video/project flows, and separate chat-session resolution in `chat_service.py`. A fix must cover both paths.
- Actual provider cost is only known after completion. The requested no-balance rule therefore maps to a preflight `balance_micros > 0`; final official cost remains deducted after usage is known.
- `MAX(0, balance-cost)` prevents negative stored balances but does not reserve credit across concurrent calls. Reservation is deferred unless concurrent overspend becomes a measured problem.
- Frontend redemption already updates both the global Zustand user and React Query `me` cache immediately. Adding a state machine would duplicate working state ownership, so no state-machine change is needed.
- The app's custom HTTPException handler returns `response.data.error`, so the current insufficient-balance message is already readable. `resolveRequestError` now also accepts FastAPI's default `detail` shape for robustness in tests or deployments without the custom handler.
- Usage API currently filters only by feature and days. Source is already stored as `official` or `user`, so adding a SQL condition and one query parameter is sufficient.
- Admin user creation currently relies on the backend default and does not show/send a level. The form should expose level with state initialized/reset to 1.
- User, invitation, redemption, and usage filter UIs include an `all` option but no one-click reset. Add a reset button only when filters differ from defaults (or search is non-empty).
- The balance guard should be a small shared `require_model_balance(conn, user_id, config)` policy in `usage_service.py`, invoked immediately before actual provider work. It no-ops for personal configs and super admins, and raises HTTP 402 for ordinary users with `balance_micros <= 0` on official configs.
- Chat must run the guard inside `begin_chat_turn` before persisting the user's message; otherwise rejected requests would leave orphan user messages.
- Project parsing may mutate project status during preparation, so the exact guard placement must be before status changes or must restore state on rejection.
- Direct image/video, project parse/optimize/background image generation, chat text, and agent image tools are the provider-call boundaries requiring coverage.
- The backend root currently mixes 10 `test_*.py` files, eight `*_service.py` modules, infrastructure, API routers, and utilities.
- A focused structure is sufficient: move tests to `backend/tests/` and actual service modules to `backend/services/`; keep core runtime/infrastructure stable to avoid a high-risk package rewrite.
- No plugin subsystem exists in this backend, so creating a `plugins/` directory would be speculative and is intentionally skipped.
- Backend files were reorganized into `services/`, `lib/`, and `tests/`; a stdlib `tests/run_all.py` preserves the existing executable-assert test style without adding pytest.
- Post-move import scan found no stale flat service/lib imports. The full backend runner, Python compile check, frontend lint, and TypeScript check all pass after the reorganization.
- UI review confirmed reset controls appear only when active, creation level visibly defaults to 1, and usage source defaults to all.
- Broader filter audit found two remaining list pages without reset: model management and AI project list. The AI project page also had a nonfunctional “advanced filters” button; replace it with a real reset action instead of preserving dead UI.
- Final balance-call scan confirms the shared guard covers direct images/videos, project parse/optimize/generation, chat turns, agent image tools, and per-scene background generation.
- Added a chat-level regression check proving official zero-balance rejection occurs before saving the user message, while a personal configuration at zero balance still saves and proceeds.
- Added explicit checks for the insufficient-balance message and new-user default level 1.
- Final verification passes for all backend self-checks, backend app import, Python compilation, frontend lint, TypeScript, whitespace, and stale-import scan.
- A new state machine was not added: redemption already updates Zustand and React Query synchronously, which is the smaller correct global-state design.
- Personal model usage remains unbilled but fully logged by source/tokens/quantity/duration. Monetary estimation remains zero until personal configs have an explicit pricing model.
- Production build was not repeated because the repository log already records the environment's Google Fonts network failure; lint/type-check and app import cover the code changes without retrying a known external failure.

### Resources

- `backend/usage_service.py`
- `backend/routers/users.py`
- `frontend/src/store/user-store.ts`
- `frontend/src/app/(workspace)/usage/page.tsx`

### Issues Encountered

| Issue | Resolution |
|-------|------------|
| First findings update patch used section order different from the newly created file | Re-read the file and applied a targeted patch against its actual structure. |
| Architecture findings patch again assumed a different section position | Re-read the current file and patched each actual section independently. |
| Base UI Select `items` does not accept primitive arrays | Use explicit `{ value, label }` option objects. |

## 2026-07-21 AI 短剧 / 漫剧调研

### Requirements

- 调研当前有代表性的开源 AI 短剧/漫剧项目及商业产品。
- 总结其业务流程与从剧本到成片的生成流程。
- 结合 SceneFlow 当前技术栈形成产品文档与技术文档。
- 识别现有功能缺口并给出子功能补全方案。
- 本轮不开发，等待用户确认文档后再实施。

### Initial Findings

- 仓库已有长期规划文件，不能覆盖历史；本次以追加会话方式记录。
- 已知栈为 FastAPI + SQLite + LangChain/LangGraph，前端为 Next.js 16 + React 19 + TypeScript + Tailwind + assistant-ui。
- 需要重新从代码核实当前图像、视频、对话和 AI 剧本实际链路，不能只依赖旧交接文档。
- 当前工作区在本次调研前已有 `backend/sceneflow.db` 修改；本轮不触碰数据库文件。
- 根脚本使用 pnpm 10 / Node 22；前端为 Next.js 16.2、React 19.2、TypeScript 5、Tailwind 4、React Query、Zustand、assistant-ui 与 Vercel AI SDK。
- 后端依赖包括 FastAPI、LangChain/LangGraph 相关适配、OpenAI、Google GenAI、Anthropic、SQLite 持久化及文档生成组件。
- 后端 README 仍有“生成模拟/旧路径”等可能过时表述，最终技术文档必须以当前代码为准。
- 前端 `AGENTS.md` 要求若后续开发 Next.js 功能，先读取仓库 `node_modules/next/dist/docs/` 对应版本文档；本轮仅写设计文档，无需按实现 API 展开。
- 当前主要业务文件集中在 `project_service.py`、`generation_service.py`、`video_service.py`、`chat_service.py`、项目/图片/视频/对话 API 与对应前端页面。
- 独立视频生成链路是真实实现：支持豆包与 Gemini，包含任务创建/轮询、文本生视频与参考图生视频、结果落盘和用量记录。
- AI 项目“一键生成”并非完整短剧流水线：分镜图可调用真实图片模型，但场景音频仍返回 `example.com` 模拟地址，项目级成片视频也仍是模拟进度与模拟 URL。
- 当前项目数据已包含剧本、场景顺序、旁白、视觉提示、场景图、场景音频、项目视频状态/进度/URL，适合在现有实体上增量扩展，而不是另起全新项目体系。
- 对话已使用 LangChain `create_agent`，带图片/PDF/Word 工具；上下文压缩、附件解析、流式 UI 和会话持久化可复用于“AI 编剧/导演助理”。
- 当前没有发现角色库、场景库、角色一致性锚点、镜头级运动/机位、配音角色映射、字幕时间轴、剪辑合成、任务队列/恢复、版本管理与人工审核实体。
- 当前 AI 项目用户流程已具备：创建项目 → 输入/优化剧本 → LLM 拆分分镜 → 编辑旁白和视觉提示词 → 拖拽排序 → 一键生成场景图/模拟音频 → 模拟项目视频。
- `projects` 表只有项目级剧本和视频字段；`scenes` 表只有顺序、旁白、视觉提示、单张图和单段音频字段。短剧生产所需的角色、地点、镜头、资产版本、语音、字幕、片段、合成与任务记录均需增量建模。
- 当前后台异步方式是进程内 `asyncio.create_task` + WebSocket 广播；服务重启会丢失任务，且没有持久化队列、重试、取消、幂等或断点续跑。
- 当前场景图提示词是固定英文模板，并未注入角色设定、画风 bible、参考图、前后镜头或负面提示，因此无法保证漫剧角色/场景一致性。
- 项目 `generate-video` 虽会校验视频模型和余额，但实际没有调用已存在的 `video_service.generate_video`；这是最直接的复用点，可把独立图/文生视频能力接入镜头生产。
- 现有场景卡只支持编辑旁白和视觉提示、查看图片与音频状态；缺少逐镜头重生成、参考图选择、镜头运动参数、配音试听、字幕校正、时长裁剪和版本对比。
- 现有用量日志已支持 feature、模型来源、耗时、token、数量和成本，可自然扩展出“项目预算估算/实际成本/单镜头重试成本”，无需另建计费系统。

### Research Resources

- 待补：开源项目仓库、官方文档、商业产品官方页面与可信行业材料。
- 本地：`backend/README.md`、`backend/requirements.txt`、`frontend/package.json`、`frontend/README.md`、`frontend/AGENTS.md`。
- 本地代码：`backend/app/services/{project_service,generation_service,video_service,chat_service,agent_service}.py`、`backend/app/api/v1/{projects,images,videos,chat}.py`、`frontend/src/app/(workspace)/{ai-script,images,videos,chat}`。

### Research Notes

- GitHub 泛关键词搜索（`AI short video`、`AI comic story video`）噪声很高，热门结果被 awesome list、代理集合等无关仓库占据，不适合作为候选筛选依据。
- 后续改用已知垂直项目的仓库元数据、README、发布活跃度和许可证逐项核验，并把“完整工作流项目”与“关键技术组件”分开评价。

### Issues Encountered

| Issue | Resolution |
|---|---|
| GitHub 泛搜索返回大量无关高星仓库 | 停止扩大泛查询，改为核验垂直候选项目和官方页面。 |
| GitHub API DNS 失败，升级审批服务又因其自身 404 拒绝 | 改用只读浏览器采集公开资料。 |
| 浏览器策略明确禁止访问 GitHub | 不绕过限制；开源项目改用项目官网、Hugging Face、论文/官方文档等允许来源，GitHub 链接仅作为已知入口列出并标记未实时核验。 |
| 浏览器策略同样禁止 Bing 与部分产品官网 | 停止外部浏览；文档不写实时星数/价格等易变数据，使用可审计的能力框架并把开发前复核列为门禁。 |

### Documentation Decision

- 交付两份根目录 Markdown：`AI_SHORT_DRAMA_PRODUCT.md` 与 `AI_SHORT_DRAMA_TECHNICAL.md`，避免为本次评审新增目录或更多辅助文档。
- “热门”按行业知名度、工作流代表性和与 SceneFlow 的可借鉴性评价，不伪造当前星数、用户数或价格。
- 产品对标分三层：端到端创作产品、自动短视频开源项目、角色/视频/语音/合成开源组件；三者不能混为同一成熟度。

### User-provided Candidate Set

- 全链路开源候选：LumenX、Toonflow、ArcReel、CineGen-AI、Open-AI-Micro-Drama-Generator、ai_story。
- 一致性/视频技术候选：SkyReels-V3、StoryDiffusion、ShotStream。
- 剧本引擎候选：ManjuForge。
- 国内商业候选：ReelMate、即梦、可灵、纳逗 Pro、Vidu、PopReels、TwoDrama、Panqu、SkyReels、MoodMax、Star AI、火山剧创 Agent、小云雀、漫小芽、漫聚星球。
- 海外商业候选：DomoAI、Runway、Pika、Sora。
- 用户描述中反复出现的共同链路：小说/IP 导入 → 自动分集/剧本分析 → 角色与场景资产 → 分镜 → 图/视频生成 → 配音字幕 → FFmpeg/时间线合成 → 发布/分发。
- 商业产品的主要差异并不在“能否生成”，而在 IP/素材来源、角色一致性、批量任务、人工返工成本、成片合成、团队协作和分发变现。
- GitHub/Gitee/商业官网即使由用户明确提供，当前浏览策略仍拒绝访问；所有许可证、版本、收费和具体宣传能力保持“待核验”，不作为已证实结论。

### Final Recommendation

- 产品先交付“AI 漫剧完整闭环”，再把关键镜头升级为 AI 视频；不要一开始追求全自动长篇真人短剧。
- 当前最值得复用的能力：LLM 剧本/对话、真实图片生成、独立文/图生视频、项目/分镜工作台、WebSocket、模型配置、余额和用量。
- 当前必须补齐：角色/场景/风格设定、镜头实体、资产版本、真实 TTS、字幕、FFmpeg 合成、持久化任务和成本估算。
- 最小可靠架构继续使用 FastAPI + SQLite + Next.js，增加有租约的 SQLite job worker；多实例/高吞吐后再迁移专用队列。
- Multi-Agent、通用 DAG、节点编辑器、LoRA 训练平台和专业 NLE 均不进入 MVP。
- 两份交付文档已通过 `git diff --check`，结构检查无异常。

## 2026-07-21 可执行开发技术方案

### Requirements

- 基于当前 SceneFlow 代码，而不是抽象绿地架构。
- 前端、后端、数据表、API、任务编排都要覆盖。
- 每项开发内容必须落到明确需求点和验收条件。
- 本轮继续产出方案，不修改 AI 短剧/漫剧业务代码。

### Initial Findings

- 现有技术文档已有架构、数据模型、API 和阶段建议，但缺少统一需求编号、前后端逐项追踪、具体路由/组件和每阶段 Definition of Done。
- 当前工作区已有用户未提交的后台模型配置、数据库、用量和管理 UI 修改；必须保留并复核，不能假设上一轮读取的代码仍完全一致。

### Current-code Findings

- 当前未提交修改正在把 `user_configs` 与 `official_model_configs` 合并为统一 `model_configs(source=user|official)`；短剧方案必须基于统一表扩展 `audio` 等 purpose，不能再按旧双表设计。
- 统一模型配置修改同时涉及 admin/settings API、serializer、usage、测试和前端模型管理；这是用户现有工作，方案只描述兼容点，不覆盖或重写。
- 项目领域仍保持旧结构：`Project → Scene`，前端类型和 Zustand store 只认识场景图片/音频与项目视频，没有角色、地点、镜头、资产版本和 job。
- 前端项目 action 已集中在 `frontend/src/actions/projects-actions.ts`，后续新增接口应沿用 action → BFF → FastAPI 路径。
- `project-store` 当前复制整份项目/场景数据并处理 WebSocket 增量；扩展到大量资产和任务后，应缩小为当前选择/轻量实时状态，持久化详情由 React Query 负责，避免双事实源继续膨胀。
- `video_service.py` 已经是可复用的真实文/图生视频供应商实现；项目短剧开发不应重写视频调用。
- 当前 `config_service.validate_config_fields` 仍只允许 `general/script/image/video`，`audio` 尚未实现；TTS 需求必须覆盖后端校验、供应商验证、前端 purpose 选项、序列化、定价单位和回归测试。
- 统一 `model_configs` 已包含定价字段和 official/user source 约束，足够承载 TTS/音频模型，不需要新增独立语音配置表；角色只需引用 `voice_config_id`。
- 项目列表 `/ai-script` 当前用 Zustand 中的全部项目做本地搜索/过滤并创建项目；首版可继续，项目规模增大后再做服务端分页，当前不扩范围。
- 项目详情集中在 `workbench-editor.tsx`，页面已经过大。新增阶段工作台时应让路由页负责查询/阶段导航，各阶段组件放在项目路由 `_components`，不要继续把所有功能堆入该文件。
- 当前 `SceneCard` 是镜头卡演进的直接起点，但 `Scene` 实际代表 LLM 拆出的单镜头。MVP 可先将表/类型语义迁移为 `shots`，保留旧 scene API 兼容层；若一开始同时引入“场”和“镜头”两级 UI，会扩大迁移成本。

### Scope Simplification

- 第一开发阶段把现有 `scenes` 视为镜头并增量扩字段，不立即增加真正的 `scenes → shots` 两级结构。
- 等出现一场多镜、场景级复用/调度的真实需求，再引入场实体或把旧表迁移为 shots；这比首版同时维护两级结构更符合当前代码。

### Integration Findings

- 项目 WebSocket 创建、事件解析和全部 mutation/query 目前集中在 `workbench-editor.tsx`；开发第一阶段应先抽一个项目控制器 hook，把连接与事件 reducer 移出页面，否则新增 JOB/ASSET 事件会继续放大单文件复杂度。
- BFF 项目没有独立显式 route 文件，actions 通过现有统一 BFF/HTTP 层访问；方案无需为每个新 API 建手写重复代理，沿用当前通用转发约定。
- 后端已有 `test_video_service.py`、`test_images.py`、`test_config_service.py`、`test_database.py` 和统一 `tests/run_all.py`；新增功能应继续用小型 assert 自检，并增加项目/job/compose 三类测试即可。
- 当前前端只有用户列表的 Node 逻辑测试。镜头/job 状态 reducer 是最值得新增的一个前端自检，不需要引入完整测试框架。

### Final Development-plan Decisions

- 技术方案升级为 V0.2，增加 DR-01 至 DR-12 需求编号、代码追踪矩阵、前端方案、后端方案、Stage 0–6 和最终 DoD。
- Stage 0 明确先完成用户正在进行的统一 `model_configs` 改造，AI 短剧功能不与其并行重写同一区域。
- MVP 保留现有 `/ai-script` 与 `/projects/[projectId]`，使用阶段查询参数，不先重构路由。
- MVP 将当前 `scenes` 直接演进为镜头；真正的一场多镜模型延期。
- 前端先拆项目控制器 hook，React Query 作为持久化事实源，Zustand 缩小职责。
- 后端只新增 job/audio/compose 三个服务和一个 worker，复用 project/generation/video/usage/realtime。
- 文档最终为 822 行；`git diff --check` 通过，旧 shot 路径/字段扫描无残留。

### Issues Encountered

| Issue | Resolution |
|---|---|
| 技术文档大型补丁上下文不匹配 | 改为小范围修订现有矛盾，再单独追加需求追踪和开发章节。 |
