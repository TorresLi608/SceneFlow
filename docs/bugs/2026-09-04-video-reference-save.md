# BUG-20260904-video-reference-save：视频提示词参考素材保存

- 首次记录：2026-09-04，来源提交 `bff016f`
- 最近更新：2026-09-07
- 状态：部分修复，保存校验仍有源码可见缺口；本次未重现界面或运行回归
- 检索词：视频提示词、`@素材`、`videoReferences`、保存失败、`validate_video_reference_counts`
- 原报告：根目录 `BUGFIX_video_reference_save.md`，已于 `afa10d8` 删除
- [返回 Bug 索引](README.md)

## 现象与复现

历史报告描述：剧集编辑器的视频提示词中引用素材后，点击保存报错。涉及 [shot-row.tsx](../../frontend/src/app/projects/[projectId]/episode/[episodeId]/_components/shot-row.tsx) 与 `PATCH /api/projects/:projectId/scenes/:sceneId`。

重新验证时应分别覆盖：单个合法引用、多媒体混合引用、超出模型上限和不可用引用。原报告给出了这些预期行为，但没有记录实际执行结果；不能据此认定当前保存流程已通过验证。

## 根因与定位

历史提交可确认的参数问题位于 [projects.py](../../backend/app/api/v1/projects.py) 的 `update_project_scene`：旧调用 `validate_video_reference_counts(resolved, caps)` 与 [video_service.py](../../backend/app/services/video_service.py) 的四参数签名不符。引用数据由 [reference_service.py](../../backend/app/services/reference_service.py) 解析。

`bff016f` 将调用改为能力配置与图片/视频/音频数量四个参数，同时移除了分支内的重复导入。该修改能证明调用形状被修正，不能单独证明旧报告中的界面故障已消失。

## 修复与影响

当前代码保留了上述四参数调用，但获取能力时仍调用 `models.active_video_config` / `models.video_capabilities`；它们并不是当前 `ModelRouter` 的方法，且该分支捕获一般异常后跳过校验。因此，**“保存能成功”不等于“保存时正确限制了引用数量”**。

后续修复需要核对项目优先的模型配置解析、保存入口和生成入口的共享校验，而不是仅修改单个参数或界面提示。当前缺口也列在 [backlog](../plans/backlog.md) 的保存引用预算项中。本次只归档历史，没有修改业务代码。

## 验证

本次证据是 `bff016f` 的代码差异和当前源码检查；没有执行浏览器复现或以下测试。

相关回归入口：[test_video_service.py](../../backend/tests/test_video_service.py)、[test_config_service.py](../../backend/tests/test_config_service.py)、[test_prompt_prefixes.py](../../backend/tests/test_prompt_prefixes.py)。这些文件的存在不能替代保存接口的具体断言；修复时应验证合法选择可保存、超限和跨项目引用被拒绝。

建议复核命令（**未执行**）：

```bash
cd backend
check_dir=$(mktemp -d)
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh test_video_service test_config_service test_prompt_prefixes
```

## 历史与关联

- 2026-09-04：`bff016f` 修改调用参数并加入根目录报告。
- 2026-09-05：`afa10d8` 以过时文档为由删除报告。
- 2026-09-07：从 Git 历史归档到本文件，去掉“应该正常工作”即验证通过的歧义，补充当前配置解析缺口。

在仓库根目录可查看原始证据：

```bash
git show bff016f:BUGFIX_video_reference_save.md
git show bff016f -- backend/app/api/v1/projects.py
```

相关规则：[引用数据流](../architecture/data-flow.md#4-references-prefix-prompts-and-asset-library)、[边界与模型解析](../architecture/boundaries.md)、[测试约定](../conventions/testing.md)。
