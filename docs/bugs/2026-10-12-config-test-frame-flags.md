# BUG-20261012-config-test-frame-flags：配置测试的首尾帧标志断言过期

- 首次记录：2026-10-12
- 最近更新：2026-10-12
- 状态：已验证
- 检索词：test_config_service、test_video_capabilities_are_normalized_and_stored、supportsFirstFrame、supportsLastFrame、supportsStartEndFrames、normalize_video_capabilities、AssertionError、第 202 行

## 现象与复现

`backend/tests/test_config_service.py::test_video_capabilities_are_normalized_and_stored` 在第 202 行的字典全等断言失败，整个 `test_config_service` 在隔离运行器中报 `FAIL`。因为该文件用 `__main__` 顺序调用用例，排在它后面的所有用例（定价、来源切换、旧表合并、官方默认优先级、视频能力目录等）都不会执行。

这是一个既有失败：自 2026-09-07 起，[不支持的 FPS 参数](2026-09-07-video-unsupported-fps.md)、[按次计费量](2026-09-14-request-unit-metering.md)、[同轮搜索缓存串味](2026-09-22-chat-web-search-turn-cache.md)、[网页正文提取 SSRF 与资源上限](2026-09-22-chat-fetch-web-content-ssrf.md) 四份记录都把它标注为"既有失败、与本次改动无关"，但没有建立独立问题或修复。

最小复现（在 2026-10-12 的 `HEAD`，即 `cbd5cf0`，`git stash` 掉工作区改动后执行）：

```bash
cd backend
check_dir=$(mktemp -d)
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh test_config_service
# FAIL  test_config_service
# AssertionError at tests/test_config_service.py:202 (assert video_capabilities(config) == {...})
```

## 根因与定位

- `app/services/config_service.py::normalize_video_capabilities` 自提交 `25ce0ed`（2026-08-31，"add support for first and last frame references to scene video generation configs"）起在返回值中追加了 `supportsStartEndFrames`、`supportsFirstFrame`、`supportsLastFrame` 三个键。
- 测试的期望字典停留在没有这三个键的版本，其余已断言字段没有差异（与 2026-09-07 记录的观察一致）。
- 用例使用的 `wan2.7-t2v` 不在 `VIDEO_MODEL_CAPABILITIES` 目录中，走 `default_video_capabilities` 的 Qwen 回退分支，该分支不声明首尾帧，因此三个标志经 `flag(...)` 归一化后都是 `False`。

已确认原因，不是应用逻辑缺陷，而是测试期望未随能力契约同步。

## 修复与影响

- 只改了测试：`backend/tests/test_config_service.py` 的期望字典补齐 `supportsStartEndFrames: False`、`supportsFirstFrame: False`、`supportsLastFrame: False`，并加注释说明该模型走回退分支。
- 没有修改 `config_service.py` 或任何调用方；首尾帧能力的长期规则仍见 [数据流](../architecture/data-flow.md) 与 [后端参考](../../backend/README.md#providers-and-model-configuration)。
- 影响：`test_config_service` 文件后半部分的用例重新进入执行；同一天为 Grok 渠道新增的三个配置用例也依赖这次修复才能跑到。

## 验证

实际执行（2026-10-12）：

1. `HEAD` 复现：按上文命令在 `git stash` 后运行，`FAIL`，堆栈停在第 202 行同一断言。
2. 修复后全量后端套件：

```bash
cd backend
check_dir=$(mktemp -d)
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh $(rg --files tests -g 'test_*.py' | sed 's#^tests/##; s#\.py$##')
```

结果：40 个文件中 39 个 `PASS`（含 `test_config_service`），1 个 `FAIL` 为既有的 `test_episode_migration`（`NoSuchTableError: scenes`，见 [BUG-20260920](2026-09-20-episode-migration-test-scenes.md)），与本次改动无关。

未执行项：无。本次没有调用真实供应商接口。

## 历史与关联

- 2026-08-31：`25ce0ed` 引入首尾帧标志，测试期望未更新（根据 `git log -S'supportsLastFrame'` 定位，测试文件在该提交后没有同步改动）。
- 2026-09-07 至 2026-09-22：四份记录把该失败标注为既有问题但未处理，见上文链接。
- 2026-10-12：随 Grok 渠道功能一起修复测试期望并复跑全量套件；Grok 本身是功能开发，不建立 Bug 记录。
