# BUG-20260914-request-unit-metering：按次配置被视频时长放大费用

- 首次记录：2026-09-14
- 最近更新：2026-09-14
- 状态：本地计费与配置专项回归通过；完整配置套件有既有失败
- 检索词：视频、按次、按秒、unitName、request、second、quantity、record_usage

## 现象与复现

视频生成调用把时长作为 `quantity` 传入计费。已有 API 允许保存 `unitName: "request"`，但原计费逻辑仍按时长乘单价：例如按次单价 0.2 的 6 秒视频被计算为 1.2，而不是 0.2（倍率为 1 时）。本次为模型管理增加按次/按秒选择时，从源码确认了这一问题。

## 根因与定位

[`record_usage`](../../backend/app/services/usage_service.py) 读取价格后直接使用调用方的 `quantity`，没有根据 `unit_name` 解析计费数量。两个视频入口都传时长：[`videos.py`](../../backend/app/api/v1/videos.py) 的独立生成，以及 [`generation_service.py`](../../backend/app/services/generation_service.py) 的 `scene_video` 路径（剧集和旧工作台共用）。已检索所有 `record_usage` 调用方；图片和音色传 1，文本调用默认传 0。

## 修复与影响

- 在共享 `record_usage` 读取保存的价格后，将 `request` 的计费量统一设为 1；`second` 保留调用方传入的时长。计算金额和使用记录写入同一个计费量。
- 模型表单增加按次/按秒选择，保存和详情标签使用实际单位，编辑时回填已有单位。新增表单默认按次，现有按秒配置保留。
- 延续 Decimal 计算、最后一次四舍五入到 micros、官方余额扣减、自定义配置只记成本和历史价格快照。
- 不改真实配置、余额或历史使用记录；秒价继续使用生成参数中的时长，未新增成品媒体时长探测。规则见 [计费设计](../design/feature-billing.md)。

## 验证

2026-09-14 实际执行：

- 在 `backend/` 执行 `SCENEFLOW_PRIVATE_GENERATED_DIR=/tmp/sceneflow-pricing-check-media sh scripts/run_tests.sh test_usage_service test_video_service test_project_production`：三项通过，runner 为每个文件使用临时数据库。
- 在临时 `DATABASE_URL` 和媒体目录下直接执行 `test_user_config_pricing_round_trip()`：通过，覆盖视频两种单位切换、不含单位的 PATCH 保留旧单位及价格精度。
- 新增 `test_video_pricing_units()`：覆盖 `video`/`scene_video`、两种单位、官方/个人配置、Decimal 取整、实际余额扣减和模型编辑后的历史快照。
- 前端资源搜索、预算和金额 Node 检查共 11 项通过；`pnpm exec tsc --noEmit` 通过；`pnpm lint` 无错误，保留 `use-unsaved-settings-check.ts` 原有未使用 `Project` 警告。
- 完整 `test_config_service.py` 在既有 `test_video_capabilities_are_normalized_and_stored` 的第 202 行失败，尚未执行到定价检查；另外执行 `git show HEAD:backend/tests/test_config_service.py` 取得的基线测试，复现相同断言失败。本次未修改该视频能力逻辑或断言。
- 未进行真实付费生成或写入用户的实际配置；模型表单的完整浏览器复验受浏览器会话可用性限制，未宣称通过。

## 历史与关联

- 2026-09-14：新增视频计价单位选择，同步修正共享按次计费量并补充回归。无提交或 PR 链接。
