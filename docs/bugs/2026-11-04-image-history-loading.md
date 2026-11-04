# BUG-20261104-image-history-loading：图片历史原图加载压力

- 首次记录：2026-11-04
- 最近更新：2026-11-04
- 状态：后端五组自检、前端类型检查/lint、25 项现有测试及隔离浏览器回归通过；真实部署延迟未实测
- 检索词：图片生成、历史记录、页面缓存、其他接口变慢、thumbnailUrl、WebP、IntersectionObserver、nextCursor、分页

## 现象与复现

用户反馈：加入页面状态缓存后，切到图片生成页时，如果历史图片较多，页面加载慢，并影响其他接口响应。复现入口是 `/images` 的历史列表。该性能反馈未在用户真实数据和部署上进行计时复现。

## 根因与定位

- 源码确认：历史列表把原图 URL 交给 `next/image`，显示尺寸为 44×44，使用 `unoptimized`，因此下载的仍是完整原图。已有默认 `loading="lazy"`，但由浏览器决定预加载距离，没有按该内部滚动列表显式限制挂载。
- 原 `GET /api/images/history` 一次返回最新 50 条，没有后续分页。媒体通过 Next fallback rewrite 转发到 FastAPI 签名文件接口；共享带宽、连接或服务端资源竞争是可能原因，尚未实测确认具体瓶颈。
- 页面状态缓存修复本身见 [菜单切换状态记录](2026-11-03-workspace-page-state-reset.md)，本次保留其 Activity/controller 所有权。

## 修复与影响

- `image_thumbnail_service.py`：Pillow 按 EXIF 方向转正、居中裁剪为 128×128 WebP，质量 75，保留透明度；原图不修改。缩略图使用原图派生路径 `.thumb.webp`，原子写入、权限 0600；失败只记录异常类型并保留原图。
- `images.persist_image` 在进入写事务前编码，生成路由通过 `asyncio.to_thread` 执行处理/存储，避免在事件循环压图。
- `generation_record_json` 返回 `thumbnailUrl`，只有派生文件存在时才签名。视频或旧图为 null；按用户追加要求不提供或运行旧图补齐。
- `generation_record_service.list_image_history_page` 按创建时间和 ID 降序返回 20 条（可选 1–50），`nextCursor` 为不透明位置。相同时间有 ID 作为排序依据，删除游标记录不影响继续分页；列表始终按用户和 kind 过滤。
- 图片面板使用 React Query infinite query；成功生成插入首页、删除更新所有页，保留后续游标。仅当前菜单启用历史查询；滚动到底加载后续页，进入失败状态后停止滚动触发的连续翻页，提供按钮重试及键盘入口。
- `image-history-thumbnail.tsx` 用历史滚动容器作为 IntersectionObserver root，额外预取 80px；仅可见菜单挂载范围内的小图，移出范围后卸载，低请求优先级，失败显示占位。旧图显示占位，仍可点击查看原图；大图预览和下载使用原 URL。
- 手动删除和保留期清理共享 `generation_record_paths`，清理原图和派生文件；不扩展到项目媒体。
- 契约和长期流程见 [后端参考](../../backend/README.md#images--appapiv1imagespy)、[数据流](../architecture/data-flow.md)、[代码地图](../architecture/code-map.md)。未变更数据库 schema 或增加依赖。

## 验证

- `cd backend`，使用临时媒体目录运行 `SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh test_generation_records test_images test_generation_retention test_artifact_service test_video_service`：5/5 通过；runner 为每个文件分配临时数据库。
- 新增/扩展回归：编码发生在写事务外、处理在线程中；真实 WebP 尺寸/类型/权限/体积；EXIF 和透明度；坏图和缩略图存储失败保留原文件；签名文件响应及缓存头；跨账号列表/删除隔离；手动删除和保留期同时清理派生文件；55 条历史跨页、相同/空时间、游标记录删除和新增、无重复遗漏、非法参数（含 JSON 孤立代理字符）、列表不压缩旧图。
- `cd frontend && pnpm exec tsc --noEmit`：通过。
- `cd frontend && pnpm lint`：通过。
- `cd frontend && node --no-warnings --experimental-strip-types --test src/lib/*.test.mts 'src/app/(workspace)/admin/users/_components/user-list.test.mts' 'src/app/(workspace)/chat/_components/chat-message-state.test.mts'`：25/25 通过。
- 最终 `tsc --noEmit` 和 lint 在缩略图改为随滚动移入/移出挂载后再次通过；增加游标字符校验、缩略图存储失败场景后 `test_generation_records` 独立复跑通过。
- 已按约定设置临时数据库、媒体路径及 `SCENEFLOW_WORKER_ENABLED=0`，使用 `.venv/bin/python scripts/regen_api_spec.py` 重新生成 OpenAPI；diff 包含图片分页参数及缩略图/游标说明。
- Playwright 隔离回归：临时 fixture 位于 `/private/tmp/sceneflow-history-check/`，使用实际图片面板、实际 `next/image`、React Compiler、React Query 和已有 CSS，HTTP adapter/媒体为模拟数据。55 条记录（含两条无缩略图旧记录），初次仅一页 20 条、附近图片挂载数大于 0 且少于 10，未请求原图；滚动下一页故意失败后保留首页并可重试，恢复到 40 条，再取最后 15 条终止；页面隐藏后即使派发滚动事件，历史与缩略图请求数均未增加；旧记录选择能打开原图；删除和隐藏期间生成成功后列表数量正确、游标保持、结果回填；中文及英文切换、1440×1000 桌面和 390×844 手机宽度无面板横向溢出。截图位于临时 fixture 的 `output/playwright/`。
- 隔离 fixture 初次缺少 Next 注入的 `process.env`，以及验证脚本误选外层表单滚动容器、统计区改变布局，均已修正后完整重跑通过；这些失败不是产品通过记录。最终页面无新增应用错误，初次缺少 favicon 的 404 在 fixture 中消除。
- `git diff --check` 通过；涉及文档的 218 个本地 Markdown 链接目标存在性检查通过。
- 未操作真实数据库或生成文件，未调用付费模型；尚未量化真实部署下其他接口的延迟改善。

## 历史与关联

- 2026-11-04：用户批准缩略图方案，随后明确只处理新图，再追加同时实现可视区域加载及历史分页。旧图补齐不在本次范围。
