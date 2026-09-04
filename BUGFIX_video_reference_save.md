# Bug修复：视频提示词 @参考素材 保存失败

## 问题描述
在剧集编辑界面，如果视频提示词里面 @参考素材，点击保存会报错。

## 根本原因
在 `backend/app/api/v1/projects.py` 第671-675行，调用 `validate_video_reference_counts` 函数时，参数传递错误。

### 错误代码（修复前）
```python
elif field == "video_references":
    # Video has per-media caps; reuse the render path's validator.
    from app.services.generation_service import validate_video_reference_counts

    try:
        caps = models.video_capabilities(models.active_video_config(session, user_id))
        validate_video_reference_counts(resolved, caps)  # ❌ 参数错误
    except HTTPException:
        raise
    except Exception:
        pass
```

### 问题分析
1. ~~`validate_video_reference_counts` 从错误的模块导入（应该从 `video_service` 导入）~~
   - 实际上文件顶部第76行已经正确导入
2. **关键问题**：函数调用参数完全错误
   - 传入了 `resolved`（一个字典）和 `caps`
   - 但函数期望的是：`capabilities`, `image_count`, `video_count`, `audio_count`

### 正确的函数签名
```python
def validate_video_reference_counts(
    capabilities: dict[str, Any],
    image_count: int,
    video_count: int,
    audio_count: int,
) -> None:
```

### 修复后的代码
```python
elif field == "video_references":
    # Video has per-media caps; reuse the render path's validator.
    try:
        caps = models.video_capabilities(models.active_video_config(session, user_id))
        validate_video_reference_counts(
            caps,
            len(resolved["images"]),
            len(resolved["videos"]),
            len(resolved["audios"])
        )
    except HTTPException:
        raise
    except Exception:
        pass
```

## 影响范围
- **受影响功能**：剧集编辑页面，镜头编辑器中的视频提示词保存
- **触发条件**：在视频提示词中使用 @ 引用任何素材（角色、道具、音频、视频等）
- **错误表现**：保存时抛出异常，提示参数类型错误

## 测试验证

修复后，以下操作应该正常工作：

1. 在视频提示词中 @ 一个角色 → 保存成功
2. 在视频提示词中 @ 多个素材 → 保存成功（如果不超过模型限制）
3. 在视频提示词中 @ 超过模型限制的素材 → 保存失败，显示清晰的错误信息（如："selected model accepts at most 4 reference images"）

## 如何应用修复

1. 代码已经修改完成
2. 重启后端服务：
   ```bash
   # 如果使用 npm run dev:backend
   # 停止当前服务（Ctrl+C），然后重新运行：
   npm run dev:backend
   
   # 或者如果直接运行 uvicorn
   cd backend
   .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
   ```

## 相关代码位置

- **修复文件**：`backend/app/api/v1/projects.py` (第669-682行)
- **函数定义**：`backend/app/services/video_service.py` (第113-135行)
- **引用解析**：`backend/app/services/reference_service.py` (第48-150行)

## 技术细节

`resolve_generation_references` 返回的 `resolved` 结构：
```python
{
    "images": [path1, path2, ...],  # 图片类型的引用
    "videos": [path1, ...],         # 视频类型的引用
    "audios": [path1, ...],         # 音频类型的引用
    "labels": [label1, label2, ...],
    "items": [...]
}
```

验证逻辑会检查：
- 图片引用数量不超过 `maxReferenceImages`
- 视频引用数量不超过 `maxReferenceVideos`
- 音频引用数量不超过 `maxReferenceAudios`
- 如果模型要求必须有某类引用，则验证是否提供

## 相关 Issue

这个 bug 可能也影响了其他地方的视频引用验证。建议检查整个代码库中 `validate_video_reference_counts` 的所有调用。
