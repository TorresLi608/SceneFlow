# BUG-20260908-export-video-audio-missing：合并导出视频丢失音频

- 首次记录：2026-09-08
- 最近更新：2026-09-08
- 状态：正常路径已验证；探测失败处理和精确同步仍有验证缺口
- 检索词：视频导出、合并导出、音频丢失、concat_videos、export_service、无声音、FFmpeg、a=0
- [返回 Bug 索引](README.md)

## 现象与复现
在剧集管理 / 视频管理中，勾选分镜视频并执行「合并导出」后，导出的完整 MP4 文件没有任何声音，单个视频中的原生音频（由视频模型生成的对白/音效/配乐）未被合并导出。通过 `ffprobe` 检查历史导出的 MP4 文件，确认仅包含 `video` 流，完全缺少 `audio` 流。

## 根因与定位
在 [media_service.py](../../backend/app/services/media_service.py) 的 `concat_videos` 函数中：
FFmpeg 拼接滤镜链被硬编码为：
```python
"-filter_complex", f"{chains}{inputs}concat=n={len(parts)}:v=1:a=0[out]",
"-map", "[out]",
```
1. 参数 `a=0` 明确告知 FFmpeg 每个分段输出 0 个音频流；
2. `-map "[out]"` 仅映射了视频流，导致所有视频片段的原生音频轨在导出时被强制丢弃。

## 修复与影响
修改 [media_service.py](../../backend/app/services/media_service.py)：
1. 新增 `_probe_video_audio_and_duration` 辅助函数：利用 `ffprobe` 解析每个片段是否包含音频流及容器时长，缺少容器时长时尝试流时长；
2. 在 `concat_videos` 中：
   - 若任何输入片段包含音频（`any_audio` 为 True）：
     - 对包含音频的片段：通过 `[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo,aresample=async=1,apad,atrim=0:{duration}[a{i}]` 进行重采样并补齐/裁剪至探测时长；精确音画同步仍需单独验证；
     - 对无音频的片段（如纯静音视频）：通过 `anullsrc=channel_layout=stereo:sample_rate=44100,atrim=0:{duration}[a{i}]` 自动生成与画面等长的静音轨填充；
     - 组合 `concat=n=N:v=1:a=1[vout][aout]` 并同时映射 `[vout]` 与 `[aout]`，使用 `-c:a aac -b:a 192k` 编码输出高质量音频。
   - 若所有片段均无音频：保持原有只合并视频轨（`v=1:a=0`）的精简输出逻辑。
3. 单元测试更新：在 [test_exports_api.py](../../backend/tests/test_exports_api.py) 中扩展 `_clip` 支持生成带音轨的测试视频，并新增 `test_merging_clips_with_audio_preserves_audio_stream` 测试用例，检查带音轨和静音片段混合导出后存在 AAC 音频流。

当前限制：ffprobe 不可用、探测失败或解析异常时返回 `(False, 0.0)`，调用方按无音频处理，可能静默丢弃原音轨；混合序列中缺少时长的静音片段使用 5 秒补齐。现有测试没有覆盖这些分支，也没有断言静音段时长或多片段精确同步。上述限制已同步到 [Backlog](../plans/backlog.md)。

## 验证
1. 执行测试：
   ```bash
   cd backend
   check_dir=$(mktemp -d)
   SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh test_exports_api test_media_service
   ```
   输出：
   ```
   PASS  test_exports_api
   PASS  test_media_service
   ```
2. 前端类型检查：`pnpm exec tsc --noEmit` 通过。

## 2026-09-08 文档核对与复验

本轮使用独立的临时数据库和媒体目录重新执行以下命令，两个测试文件均通过：

```bash
cd backend
audit_export_dir=$(mktemp -d)
SCENEFLOW_PRIVATE_GENERATED_DIR="$audit_export_dir/media" sh scripts/run_tests.sh test_exports_api test_media_service
```

`command -v ffmpeg ffprobe` 确认两个工具均可用，混合片段测试实际执行了 AAC 流检查。该检查只证明音轨存在，不代表全部同步和探测失败场景已验证；本轮未检查真实历史导出文件。

## 历史与关联

- 2026-09-08：原修复增加音频探测、补齐与导出映射；同日文档核对补充剩余限制，修复本记录的本机绝对链接和索引表格分隔行，并执行上述复验。
- 长期流程见 [导出数据流](../architecture/data-flow.md#7-clips--export)，调用方和测试入口见 [代码地图](../architecture/code-map.md)。
