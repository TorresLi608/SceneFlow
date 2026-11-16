# 模块化短剧生产技能

2026-11-10：完成第一步的协议与骨架。2026-11-16：修正骨架评审发现的协议缺陷（见 [BUG-20261116-skills-contract-defects](../bugs/2026-11-16-skills-contract-defects.md)），下文已按修正后的行为描述。本文区分已实现的基础设施和后续迁移计划；现有 API、生产服务和聊天工具尚未切换到 Skills。

## 调用方向与责任

```text
SceneFlow API / job handler ── 鉴权、模型解析、余额检查 ──┐
SceneFlow Agent ── adapter.to_tool(host_run) ──────────┤
                                                    ▼
                                            BaseSkill.run(input, api_key)
                                                    │
                                       skill.py：模型 SDK / 纯算法
                                                    │
                                             SkillResult[Output]
                                                    ▼
                           host：用量计费、媒体存储、DB 写入、签名链接

未来 MCP Stdio / 独立 SDK ── 参数与凭据 ──▶ 同一个 BaseSkill.run
```

- 核心仅依赖标准库、Pydantic，以及后续各技能需要的提供商 SDK。禁止直接或间接导入 `app.core`、`app.models`、业务 services、FastAPI、SQLModel。导入与元数据查询不能初始化数据库、读取环境变量或启动任务。
- API 和服务保留项目/分集所有权、模型配置解析、余额门禁、项目锁、取消、保留策略、数据写入与签名媒体链接。Skill 不接收用户、项目、数据库 config ID、价格或存储目录。
- `adapter.py` 是可选 LangChain 边界，五个文件都委托给共享的 `tool_adapter.skill_tool`。`to_tool(host_run, model=…, host_inputs=…)` 接受已绑定上下文的异步函数，输入是相应 Input，输出是宿主序列化后的工具结果字符串。宿主完成模型解析、余额检查、Skill 调用、用量记录、存储，再调用现有 `artifact_service.tool_result`；当前 adapter 尚未绑定真实 SceneFlow runner。
- provider/model/base URL 是授权决定，不是 Agent 参数。带 `model` 字段的四个技能在 `to_tool` 时必须传入宿主已解析的 `ModelSettings`（缺失即报错）；它被绑定进调用并从工具 schema 中移除，Agent 既看不到也不能覆盖，传入即被拒绝。`host_inputs` 以同样方式绑定其他宿主字段，例如经 `reference_service` 所有权校验后解析出的参考媒体；未绑定的媒体字段仍会出现在 schema 中，接入真实 runner 时应一并绑定。不得让工具参数绕过官方计费或访问任意内部地址。
- Agent 传入非法参数时，工具返回脱敏的文本结果（`Invalid arguments: 字段路径: 错误类型; …`）供其自行修正；原始 `ValidationError` 含提示词与 URL，不会离开 adapter。
- `skill.py` 接收纯参数和独立的 `SecretStr` API Key，不读取环境变量。MCP 的环境读取、SDK 的凭据获取均留在调用入口。密钥不进入 Input、Output、元数据、Agent 参数或持久化任务 payload。

## 已落地的文件

`backend/app/skills/` 的顶层为 `__init__.py`、`base.py`、`registry.py`、`tool_adapter.py`（共享的 LangChain 绑定，导入时不加载 LangChain）。五个子目录均只包含四个核心源文件：`schema.py`、`skill.py`、`adapter.py`、`__init__.py`。`mcp_server.py` 和对外 README 在第四步实现。

- `BaseSkill[InputT, OutputT].run()`：验证输入，调用异步 `execute()`，再验证结果；Python 支持 schema 实例或字典。`execute()` 用 `self.success(data, usage=…, warnings=…)` / `self.failure(code, message, data=…)` 构造结果，它们会选对 `SkillResult[Output]` 的参数化；裸 `SkillResult(...)` 只能表示不带 data 的错误，带 data 时会给出明确报错。
- `SkillRegistry.register/get/list_metadata()`：显式注册、拒绝重名、输出输入与结果 JSON Schema（结果 schema 按序列化形态生成，Decimal 为字符串）。名称必须匹配 `^[a-z][a-z0-9_]{0,63}$`，缺少 schema 声明的类注册时报 `TypeError`。默认只查找/列出 `implemented=True` 的技能；未知名称和未实现的技能都抛 `SkillUnavailableError`（`LookupError` 子类）。`create_registry()` 注册全部五个规划条目，当前它们都是 `implemented=False`，默认可调用列表为空。
- 查询规划条目时显式传 `implemented_only=False`。骨架执行返回 `NOT_IMPLEMENTED`，不产生媒体、不调用模型、不写入数据。
- `to_tool()` 采用安装版本支持的 `StructuredTool` JSON schema（已去掉宿主绑定字段及其不再被引用的 `$defs`），执行时用 Pydantic 验证；兼容 snake_case Python 参数与 camelCase JSON 参数。导入核心与 adapter 模块时不加载 LangChain，只有调用 `to_tool()` 时加载。

## 公共协议

| 类型 | 协议与语义 |
|---|---|
| `SkillModel` | 拒绝未知字段，去除字符串首尾空白；Python 字段为 snake_case，JSON 使用 `model_dump(mode="json", by_alias=True)` 或 `model_dump_json(by_alias=True)` 输出 camelCase。独立于导入了 ORM 常量的业务 `CamelModel`。 |
| `ModelSettings` | `provider`、模型 ID `model`、可选 `baseUrl`、`timeoutSeconds`；不包括凭据、配置行 ID、价格或账号状态。`baseUrl` 与媒体 URL 一样拒绝内嵌登录凭据（`https://user:key@host`）。 |
| `MediaArtifact` | `mediaType` 与 `data` / `url` 二选一，可带名称、时长、尺寸。Python `data` 是原始 bytes，JSON 为 URL-safe base64；不是现有 API 的 `data:image/...` 字符串。入口负责格式转换。URL 为 HTTP(S)，不允许 URL 登录凭据。 |
| `SkillUsage` | 提供商/模型，输入、输出、缓存读写 token，以及 Decimal `quantity` 和 `unit`（两者必须同时给出或同时省略）。JSON Decimal 为字符串；`null` 表示未报告，`0` 表示报告了零。无价格计算或余额扣减。 |
| `SkillResult[Output]` | `status: success/error`、`data`、`error`、`usage[]`、`warnings[]`。成功必须有 data 且无 error；失败必须有 error，可保留符合 Output 的部分结果和已发生的用量。 |
| `SkillError` | 稳定 `code`、经过脱敏的 `message`、`retryable`，以及 `details[]`：`字段路径: 错误类型` 形式的条目，只说明哪里不对，不含出错的值。不携带完整提供商响应、脚本或凭据。 |

毫秒、尺寸、FPS 等整数拒绝布尔值。输入校验失败返回脱敏的 `INVALID_INPUT`，`details` 列出至多 12 个字段路径与 Pydantic 错误类型；跨字段规则（`value_error`）附带本包校验器自己的固定说明，因此校验器的报错文案不得拼入输入值。跨字段规则只在各字段单独合法后才执行，所以一次返回里不会同时出现两类错误。可预期模型失败由实现抛出 `SkillExecutionError`（可 pickle / copy，空 code 或 message 回退为固定文案）或返回失败结果。输出协议缺陷与未预期异常继续传播，由宿主记录安全诊断并转换为 HTTP/Tool/MCP 错误。取消继续传播。核心没有隐式重试，`retryable` 只是说明，并非再次付费调用的授权。

`MediaArtifact` URL 校验只保证语法，不进行网络访问或 SSRF 防护；网络下载与 provider base URL 的允许范围须由宿主/具体提供商实现约束。核心返回的临时 URL 不能直接存入 SceneFlow 的生成媒体 path；宿主下载保存相对路径，响应时签名。日志也不能打印携带媒体或脚本的输入输出。

## 五个技能的 Input / Output

| 技能 | 输入 | 输出 |
|---|---|---|
| `script_breakdown` | 模型、单集 script、language/style/detailLevel、image/video target、纯角色/场景/道具设定、existingShots。已有分镜用宽松的 `ExistingShotSpec`：画面提示词可空、时长可为 0（未定）、可不指定场景，与现有分镜行一致。输入同样验证重复 key 与悬空引用；`target: video` 必须带已有分镜。 | characters、scenes、props、按制作顺序排列的 shots。每镜头包含 visualPrompt、videoPrompt、cameraMove、transition、durationMs，以及文档内 scene/character/prop key。验证重复 key、镜头内重复引用与悬空引用。 |
| `image_generation` | 模型、prompt、image/character_views/storyboard_frame purpose、有序 references、views、aspectRatio/resolution、可选 width+height、PNG/GIF 选项 | 有序 images，每项含 media 和可选 view；source 标注文生图/图生图。定妆 views 必须显式给出。保留现有 GIF 字段的合法范围，不在骨架中声称支持某个模型。 |
| `video_generation` | 模型、prompt、cameraMove、durationMs、可选画幅/分辨率/FPS/声音；独立 firstFrame/lastFrame 和有序图片/视频/音频参考 | video 媒体，可携带实际时长/尺寸。firstFrame 与 lastFrame 是两个独立槽位，可只给其一（与现有 `video_service` 一致）；不自动补入分镜锚点。FPS 默认为空，入口省略不支持的参数。 |
| `voice_design` | 模型、design/clone/select/synthesize 模式；描述与试听文本、参考音频、provider voice 或有 key 的台词列表；每句可覆盖 voice | provider voice（含独立 targetModel）、可选 previewAudio、按输入顺序的台词音频 clips（lineKey 不得重复）。验证设计、克隆与合成所需参数；属于其他模式的字段会被拒绝而不是忽略：参考音频只用于 clone，provider voice 只用于 select / synthesize，台词只用于 synthesize。 |
| `storyboard_composer` | title、尺寸/FPS、有序 shots；每镜头画面、源裁切起点、时长、转场说明、音频与字幕 cue | 带版本的便携工程数据：timeline、总时长、尺寸/FPS。镜头连续排列；cue 时间相对镜头，timeline startMs 是绝对工程时间。验证 cue 范围、重复 key、总时长和连续性。源时长上限只约束视频素材；静态图整镜保持，动图（GIF）循环播放。音频 cue 不得长于已知的素材时长。FPS 为整数，与应用内视频能力一致；同一镜头的字幕允许重叠。 |

key 是调用方文档内的引用，Skill 不查询或生成数据库实体 ID。列表顺序就是编排顺序，不引入项目级 order_num。针对既有镜头的 video breakdown 要在第三步保留 key 并原位生成运动字段；替换镜头及 `replaceAll/applied` 确认仍由现有业务层决定。

composer 只编排工程元数据。第一版 timeline 连续无重叠，transition 是交给渲染器解释的说明；实际转场时长、混音、烧录字幕与 MP4 渲染不在骨架中实现。媒体 URL/字节如何保存由调用方决定。

## 分阶段接入与验证计划

| 阶段 | 工作与完成条件 |
|---|---|
| 1，当前 | 基类、公共协议、五套 schema、显式 registry、四文件目录、可选 adapter。离线验证 schema、元数据、导入隔离、结果/错误/取消、adapter 实际调用；真实生成未实现。 |
| 2 | 抽取 image/video 的底层 SDK 调用至纯技能，旧模型/服务入口保留兼容委托。接入 `api/v1/images.py`、`videos.py` 和 `agent_service.create_chat_tools` 的上下文 runner，并覆盖项目/队列调用者。验证 PNG/GIF、参考图、首尾帧、能力/FPS/时长、计费与存储；provider 测试使用模拟网络。 |
| 3 | 抽取结构化剧本调用和 Qwen 设计；数据库 bible/context 与写入留在 breakdown/voice 服务。音色 clone/provider TTS 是新增能力，需实际适配与测试，不能用当前本地试听流程冒充。项目不因此自动启用逐镜头 TTS。 |
| 4 | 实现 composer 算法、FastMCP Stdio 入口、环境凭据绑定、独立 SDK 打包与 README；验证 MCP 初始化/工具枚举/调用、无提供商 Key 的错误、干净环境安装与离线集成。随后提供可选的真实供应商验收案例，明确实际执行情况。 |

源代码确认的抽取障碍：`llms/router.py` 导入数据库计费模块 `usage_service`；`video_service.py` 导入业务 `config_service`，后者依赖数据库与 router；`breakdown_service.py`、`voice_service.py`、`export_service.py` 本身拥有数据库/权限职责。因此不能在新的 `skill.py` 中直接包装这些模块，必须迁移纯调用与算法，保留业务外壳。`qwen_voice_service.py` 设计调用已有纯参数边界；`tts_service.py` 当前只支持本地试听和输出路径，不是远程台词批量 TTS。

可灵、Runway 尚无当前项目适配；Wan 通过 Qwen/DashScope 视频服务已有实现。协议容纳提供商名称，不意味着所有提供商都已可用。后续实现需要明确支持矩阵，不能遇到不支持的选项后静默丢弃。

MCP 计划使用标准 `mcp.server.fastmcp.FastMCP` 和 `transport="stdio"`，仅在入口读取提供商环境变量。stdout 专供协议，诊断写 stderr；不导入 `app.main`，不启动 HTTP、数据库或 worker。最终为独立核心和 Agent/MCP 可选依赖分别打包，避免外部开发者安装完整业务后端。当前仅支持通过 `backend` 的 Python 路径导入骨架，不声称已经交付独立安装包或可用 MCP Server。

## 本轮离线验证

```bash
cd backend
check_dir=$(mktemp -d /tmp/sceneflow-skills-check.XXXXXX)
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh test_skills
```

`test_skills.py` 在全新子进程阻断 `app.skills` 以外的全部应用模块以及 HTTP 框架、ORM、LangChain/MCP 导入，仍可加载全部骨架、共享绑定与五个 adapter 模块；另验证非法输入、媒体 JSON 字节往返、引用/时间协议、成功/失败/部分结果、脱敏错误明细、注册重复/命名/未实现门禁、取消传播，以及五个 adapter 的 snake_case/camelCase 实际异步调用、宿主绑定字段不可见且不可覆盖。只使用本地伪数据，没有真实模型调用。

2026-11-10 本轮实际执行：上述临时媒体目录下 `sh scripts/run_tests.sh test_skills test_images test_video_service test_agent_service` 四项全部通过；`frontend` 下 `pnpm exec tsc --noEmit` 与 `pnpm lint` 均退出 0；`git diff --check` 通过。未进行真实供应商生成、MCP 通信或独立 SDK 安装测试，这些能力仍待后续步骤实现。本轮没有修改 HTTP/数据库 schema，因此未生成 Alembic revision 或重新生成 OpenAPI。

2026-11-16 修正后实际执行：临时媒体目录下 `sh scripts/run_tests.sh` 跑全部 50 个后端自检文件，49 个通过；唯一失败的 `test_episode_migration` 报 `NoSuchTableError: scenes`，与已登记的 [旧库迁移问题](../bugs/2026-09-20-episode-migration-test-scenes.md) 现象一致，本轮未改动迁移，也未在干净工作区复跑对照。未进行真实供应商生成、MCP 通信或独立 SDK 安装测试。本轮没有修改 HTTP/数据库 schema。
