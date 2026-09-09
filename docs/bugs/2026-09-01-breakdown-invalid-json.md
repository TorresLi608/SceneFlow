# BUG-20260901-breakdown-invalid-json：分镜拆解 JSON 响应兼容

- 首次记录：2026-09-01，来源提交 `e72111f`
- 最近更新：2026-09-07
- 状态：历史修复，兼容解析和回归样例已存在；本次仅核对源码，未重新运行验证
- 检索词：`BREAKDOWN_INVALID_JSON`、`502`、分镜拆解、JSON 对象、裸数组、转义、截断
- 原记录：`docs/reference/known-errors.md` 中的 `BREAKDOWN_INVALID_JSON` 条目
- [返回 Bug 索引](README.md)

## 现象与复现

`POST /api/projects/:projectId/episodes/:episodeId/breakdown` 可能返回 `502 failed to break down script: response did not contain a JSON object`。

触发条件是模型/兼容网关返回的结构与预期对象不同，例如 Markdown 包裹的 JSON、裸镜头数组、一次或两次转义的文本，或只含部分完整镜头的截断数组。可用现有测试中的合成输入复现格式差异，不需要真实付费模型或用户脚本。

## 根因与定位

严格按单一完整 JSON 对象读取响应，无法覆盖这些网关格式。共同解析入口是 [router.py](../../backend/app/llms/router.py) 的 `_json_breakdown_payload`，转义候选文本由 `_json_text_candidates` 生成；[episodes.py](../../backend/app/api/v1/episodes.py) 调用拆解并转成 HTTP 错误。

诊断分类由 [error_log_service.py](../../backend/app/services/error_log_service.py) 负责：拆解 502 且错误文本包含 `json object` 时记录 `BREAKDOWN_INVALID_JSON`。这不是允许记录完整模型输出的理由。

## 修复与影响

当前解析实现扫描 JSON 值，接受带 `shots`/`scenes` 的对象或裸数组，并尝试最多两层转义解码。数组被截断时，只恢复已经完整的镜头对象，不猜测未完成镜头，也不做任意 JSON 修复。没有可接受的数据时仍应报错。

修复点在共享解析器，覆盖经 `ModelRouter.breakdown_script` 进入的拆解调用。历史记录和当前实现都不能保证任意格式错误被修复；复发时先对照具体输入结构，再决定是否扩展兼容范围。

## 验证

已有回归入口：

- [test_agent_service.py](../../backend/tests/test_agent_service.py)：包裹/尾随文本、裸数组、单层/双层转义、台词引号及截断数组恢复。
- [test_breakdown_api.py](../../backend/tests/test_breakdown_api.py)：`test_breakdown_failure_records_a_redacted_error_with_request_id` 验证失败诊断和请求 ID。

建议复核命令（**本次归档未执行，不记为通过**）：

```bash
cd backend
check_dir=$(mktemp -d)
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh test_agent_service test_breakdown_api
```

## 历史与关联

- 2026-09-01：`e72111f` 加入已知错误记录、脱敏诊断及兼容解析相关实现。
- 2026-09-07：将旧条目迁入统一 Bug 目录，核对解析器及现有测试入口；未重跑测试，也未重现生产故障。
- 相关约定：[错误处理](../conventions/error-handling.md)、[日志隐私](../conventions/logging.md)。诊断先查本记录，再在有权限时使用管理员错误日志按请求 ID/错误码查现场。
