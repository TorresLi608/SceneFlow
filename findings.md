# Findings & Decisions

## Session 2026-08-07: 当日修改日志归档

### Requirements

- 保留现有规划历史，不覆盖旧日志。
- 以 Git 当日提交、当前未提交差异和本次会话记录为依据，归档今天的全部修改。
- 详细修改清单和验证结果写入 `progress.md`。

### Initial Findings

- 项目根目录已存在 `task_plan.md`、`findings.md`、`progress.md`，本次采用追加方式记录。
- 本次日志任务不修改业务逻辑；仅更新持久化规划与进度文档。

### Git Inventory

- 2026-08-07 共发现 6 个已提交修改：
  - `9546f17`：生成产物安全存储、签名访问 URL、模型列表获取与可输入下拉组件。
  - `18f197b`：忽略前端构建缓存。
  - `593cffb`：模型 API Key 解密返显/明密文切换、许可证与免责声明。
  - `924ad5c`：管理中心及个人中心统一全局 Toast 提示。
  - `689e950`：超级管理员不扣余额、OpenAI 兼容流式用量统计。
  - `227b677`：使用日志增加模型配置名称、分页，并调整 Popover/Toast 层级。
- 当前未提交业务修改包括：
  - 智能问答首条用户问题自动更新会话标题，后续问题不覆盖。
  - 模型新增/编辑保存取消远程可用性校验，仅保留本地 API Key 完整性检查。
  - `ModelSeriesCombobox` 增加稳定外层容器，避免 Popover 锚点/输入区域重挂载引发抖动。
  - 根 `package.json` 版本调整为 `0.0.5`（并存在文件末尾换行待核对）。
- 本次日志归档新增/更新 `task_plan.md`、`findings.md`、`progress.md`。

### Detailed Findings

- 安全与隐私：
  - `backend/*.db`、`backend/generated/`、`backend/private_generated/` 和前端构建缓存加入忽略规则。
  - 图片、视频、音频和 Agent 产物统一写入权限受限的私有目录，文件权限为 `0600`、目录权限为 `0700`，不再公开挂载 `/generated`。
  - 生成产物通过带过期签名的 URL 访问；SQLite 文件初始化后限制为 `0600`。
  - WebSocket JWT 从 URL 查询参数迁移到 `Sec-WebSocket-Protocol`，并强化项目不存在/越权拒绝。
  - Base URL 拒绝 localhost、私网 IP 和带账号密码的 URL，降低 SSRF 风险。
  - 后端文档确认用户密码使用 bcrypt 哈希，模型 API Key 使用 AES-GCM 加密。
- 模型管理：
  - 新增基于 Base URL/API Key 的模型列表发现接口；支持 OpenAI 兼容、Gemini `/openai` 和 Anthropic 模型列表。
  - 新增 shadcn 风格 `Input + Popover` 模型系列组件，允许手工输入或下拉选择；后续修复聚焦/输入抖动、选项过滤导致列表不可见和弹层层级问题。
  - 编辑配置可按权限解密返显 API Key，默认密码态，并支持眼睛按钮切换明文/密文。
  - 当前未提交修改进一步取消新增/编辑保存时的远程模型可用性校验；主动“获取模型列表”和显式校验接口仍保留。
- 智能问答与模型调用：
  - 推理内容与最终答案分离，兼容 reasoning/thinking 内容块并支持思考过程展示。
  - OpenAI 兼容流式模型启用 usage 回传，修复输入/输出 Token 统计为 0 的问题。
  - 当前未提交修改以第一条成功保存的用户问题更新会话标题，空白归一化、最多 80 字符，后续问题不覆盖。
- 用量与计费：
  - 超级管理员官方配置调用仍统计费用和 Token，但余额不扣减。
  - 使用日志关联模型配置名称；管理员表和个人表增加“模型名称”列。
  - 个人使用日志增加每页 10 条分页，筛选变化时回到第 1 页。
- 交互与品牌：
  - 管理中心用户、邀请码、兑换码、模型管理及个人中心保存/失败反馈统一为全局 Toast。
  - Toast 层级提高到 `z-[100]`，Popover 定位层设为 `z-50`，避免被对话框遮罩遮挡。
  - 中英文副标题统一为“AI工作台”/“AI Workspace”。
- 协议：
  - 新增中英双语非商用源码可用协议；非盈利用途可按协议使用，商用须联系作者书面授权。
  - 新增免责声明，覆盖 AI 输出、内容合规、第三方服务、凭据/数据安全和责任限制。

### Repository Privacy Verification

- `backend/sceneflow.db`、`backend/generated/`、`backend/private_generated/` 当前均未被 Git 跟踪。
- `git log --all` 与 `git rev-list --objects --all` 已找不到上述数据库或生成目录对象，当前可达 Git 历史已清理。
- 本地 `main` 与 `origin/main` 同步在 `227b677`；当前仓库没有标签需要额外核对。
- `.gitignore` 的 `backend/*.db` 只影响尚未跟踪的文件；已经提交过的文件即使匹配规则仍会继续显示改动，必须先从 Git 索引/历史中移除。当前目标文件已完成移除。

### Precision Audit and Decision

- 审计发现额度余额与单次费用已经使用 SQLite 整数 `micros`，因此 6 位小数范围内的加减本身是精确的。
- 原精度缺口位于价格链路：模型价格在前端经 `Number()` 转换、后端经 Python `float`、SQLite 经 `REAL` 后，高精度小数会在费用计算前丢位。
- 采用以下兼容方案：
  - 前端安装常用开源库 `decimal.js@10.6.0`，金额格式化不再依赖 JavaScript 浮点数。
  - 价格表单保持字符串并直接提交，移除保存时的 `Number()` 转换。
  - 后端使用标准库 `Decimal` 校验和计算；金额、费用、价格 API 统一返回十进制字符串。
  - `model_configs`、`usage_logs` 新增 `pricing_json` 精确快照；旧 `REAL` 列保留以兼容现有数据库和旧记录。
  - 应用启动时自动为旧数据库添加新字段，不需要手工迁移；旧记录回退读取原字段，新写入记录优先读取精确快照。
- 显示与输入调整：
  - 余额、历史花费、兑换额度和使用费用统一显示 6 位小数。
  - 兑换码额度允许输入最小 `0.000001`；模型价格输入使用 `step="any"`，支持更多小数位。
- 边界说明：额度固定精确到 6 位小数，超过 6 位的兑换金额由后端 `ROUND_HALF_UP` 归入最小微单位；模型价格本身可保留更多小数位。

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

## 2026-07-21 AI 漫剧 / 短剧开发启动

### Requirements

- 按已确认的产品/技术文档开始实际开发。
- 前后端都需要形成可运行纵向切片。
- 具体模型允许后续配置；当前应补齐可配置的模型用途和接入边界。
- 保留当前工作区已有未提交代码和本地数据库。

### Initial Scope

- 本轮优先实现项目生产设置与持久化生成任务基础，不假装完成尚未接供应商的 TTS/视频合成。
- 后续生成能力统一通过 generation job 接入，避免继续使用不可恢复的裸 `asyncio.create_task`。

### Baseline Findings

- 当前业务代码工作树已干净，只有本次 planning 文档修改；之前观察到的统一 `model_configs` 等修改已成为当前基线，不再是冲突中的未提交改动。
- 前端 pnpm workspace 没有额外 package，命令应继续在 `frontend/` 下执行。
- 本轮新增 UI 仍属于现有 Client Component 边界，不需要新增额外 `'use client'` 文件边界。
- 后端 `init_db` 已采用 `CREATE TABLE IF NOT EXISTS` + 列级 `ALTER TABLE` 兼容迁移，适合继续增量扩展项目字段与 job 表。
- 项目创建/更新/序列化均集中，生产设置可在现有 create/patch 接口落地，无需另建 controller 层。
- 当前项目图片和项目视频仍由裸 `asyncio.create_task` 启动；首个 job 基础应先新增 API/服务并用于新业务任务，避免在同一切片立即重写已工作的生成路径。
- 后端测试为自动扫描所有 `test_*.py` 的 assert 自检，新增测试文件会自动进入全量 runner。
- 前端项目类型/actions/store 都集中且规模可控，DR-01 只需扩展这三处并增加一个路由私有设置组件。
- 当前工作台存在一处重复 `setStatusMessage` 调用，但与本需求无关且无行为风险，本轮不顺手扩散修复。
- 生产设置 UI 放在现有脚本卡顶部即可形成最小纵向切片，不需要现在实现完整六阶段导航。

### Issues Encountered

| Issue | Resolution |
|---|---|
| 技术文档大型补丁上下文不匹配 | 改为小范围修订现有矛盾，再单独追加需求追踪和开发章节。 |
| React lint 禁止在 effect 中同步重置表单 state | 由父组件按项目 ID 设置 `key`，项目切换时自然重建表单。 |
| 工作台 mutation 区域缺少一个闭合 `});` | 精确恢复闭合符后通过 ESLint 与 TypeScript 检查。 |

### First-slice Results

- 项目现在拥有可持久化的生产约束，后续脚本拆解、分镜、图片、视频和导出可以读取同一份参数。
- generation job 已具备数据库和服务基础，但尚无 worker processor；因此当前只宣称任务基础完成，不宣称 AI 短剧全流水线已经可运行。
- 供应商和具体模型没有硬编码，保持用户后续通过统一模型管理配置的路径。

### TTS Slice Results

- 复用 `model_configs` 的 `audio` purpose，不新增语音专用配置表。
- 免费默认能力使用 Edge-TTS；部署环境网络不可用时回退 macOS `say` 或 Linux `espeak-ng`。
- OpenAI TTS 使用兼容 HTTP 接口，模型名和 Base URL 均由现有模型管理配置。
- Edge-TTS 已作为默认免费 TTS；当前受限网络环境的真实调用触发了预期的系统语音回退，独立异步调用测试覆盖 Edge 输出分支。

### Documentation Sync Findings

- 技术文档 V0.2 仍把真实 TTS、audio purpose 和 generation jobs 全部写成缺口，与当前代码不一致，已升级为 V0.3 开发同步版。
- DR-01 已完成；DR-06 为后端任务基础完成、worker/UI 待完成；DR-07 为基础真实 TTS 完成、角色绑定/字幕待完成。
- 产品文档已增加当前可用能力，避免把 Edge-TTS 继续列为开发前未决供应商。

### Code Audit Findings

- LangGraph 已由 LangChain 安装，适合 LLM 决策与人工中断，不适合替代持久化媒体 job/worker。
- 修复图片生成缺配置时错误回退到文本模型、job 幂等键跨项目冲突、OpenAI TTS 输出字段、Linux 系统音色、真实音频时长和前后端时长校验不一致。
- 生产设置现在在后端合并已有值并校验画幅/宽高；创建时只传画幅会自动采用对应默认分辨率。
- 未采用 GPL `mutagen` 作为项目依赖，复用已部署的 FFprobe 读取媒体时长。

## 2026-07-21 模型配置与管理端修复发现

### 模型配置表与来源切换

- `user_configs` 与 `official_model_configs` 保存的是同一种模型配置，主要差异只是来源和所有者；双表会让编辑时的来源切换变成跨表迁移。
- 双表结构同时扩大了默认配置、聊天会话、用量记录和删除约束的分支数量，是“非官方改官方必须重新创建”的根因。
- 合并后的 `model_configs` 通过 `source=user|official` 和可空 `user_id` 表达归属，可以在同一记录上切换来源并保留 ID/API Key。
- 旧数据库迁移不能只复制配置本身，还必须重映射用户默认官方模型、会话 `config_id`/`official_config_id` 等引用；迁移使用事务和外键检查验证。

### 邀请码与兑换码字段

- 邀请码已有可用于表示使用时间的数据，兑换码也已有兑换时间；本次真正缺失的持久化审计字段是“创建人”。
- 新增 `created_by_user_id` 后，生成邀请码或兑换码时记录当前管理员，列表 API 通过关联用户返回 `createdBy`。
- 历史记录在创建时没有保存操作者，无法可靠回填；界面显示 `—` 是正确的数据语义。

### 图片单价编辑与保存

- 单价输入使用数字 state 并在每次输入时立即 `Number(...)`，清空输入会立即变成 `0`，所以用户无法删除初始值后正常输入。
- 编辑态应保留原始字符串，提交时才做数字转换和校验；这样同时支持空态、整数和小数输入。
- 保存返回 500 的直接原因不是用户提供的 `unitPrice: 5` 参数，而是配置更新无条件执行供应商模型验证。
- 对仅价格、描述、启用状态等非连接字段的修改，外部模型验证没有必要，并可能因第三方接口不可达或响应慢造成请求挂起/500。
- 新逻辑仅在 provider、base URL、API Key、模型系列等连接字段真正变化，或配置首次设为默认时验证。
- 使用用户提供的完整参数在真实数据库副本更新配置 ID `5` 成功，得到 `unitPrice=5.0`、`unitName=image`，说明当前代码路径已修复。

### Runtime Finding

- 当前监听 `8080` 的 PID `58712` 是修改前启动的旧后端进程，没有热加载到最新代码；继续向它发送 PATCH 仍会等待并最终在前端表现为 500。
- 由于 sandbox 不允许终止该进程，且升级审批服务返回 404，不能由当前会话代为重启。
- 需要在原后端终端按 `Ctrl+C`，然后执行 `npm run dev:backend`，再重新保存模型配置。

## 2026-07-21 编排文档结论

- 当前最合理的是 LangGraph + generation jobs/worker 混合架构，不使用单一工具强行覆盖全部流程。
- LangGraph 第一条流程应只覆盖“剧本结构化 → 校验 → 人工确认 → 保存角色/地点/镜头”。
- 图片、TTS、视频和 FFmpeg 通过数据库 job 执行；WebSocket 仅通知，不作为状态事实源。
- 中断恢复依赖 checkpoint 和 job lease；业务回滚依赖资产版本指针与下游 stale 标记。
- 已生成独立文档 `AI_SHORT_DRAMA_ORCHESTRATION.md`，作为后续 worker 和首个 LangGraph 实现依据。
