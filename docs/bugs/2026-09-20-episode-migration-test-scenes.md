# test_episode_migration 在当前迁移链上失败（NoSuchTableError: scenes）

- **问题 ID**：BUG-20260920-episode-migration-test-scenes
- **首次记录**：2026-09-20
- **状态**：已确认，未修复（仅记录；本次任务为保留策略功能开发，未排查根因）

## 现象

`backend/tests/test_episode_migration.py` 用 `LEGACY_SCHEMA`（无 `episodes` 表的旧库）建库后调用 `database.init_db()`，迁移链在 `a1b2c3d4e5f6_explicit_scene_references.py` 第 22 行 `inspect(op.get_bind()).get_columns("scenes")` 处抛出：

```
sqlalchemy.exc.NoSuchTableError: scenes
```

四个用例（`test_legacy_project_gains_episode_one_and_keeps_its_shots` 等）均在这一步失败。

## 复现

```bash
cd backend
check_dir=$(mktemp -d)
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh test_episode_migration
# FAIL  test_episode_migration；日志 /tmp/test_episode_migration.log
```

## 已核实

- 2026-09-20 在提交 `a1c71f1`（refactor/0918 分支 HEAD）的临时 worktree 上按同样命令复跑，结果相同，因此与当日新增的 `e4b7c2d9a1f5_split_retention_windows` 迁移无关（该迁移只操作 `system_settings` 行，且位于链尾）。
- 新库从空白 `alembic upgrade head` 及 `alembic check` 均通过（见保留策略功能验证），问题仅出现在从 `LEGACY_SCHEMA` 起步的旧库升级路径。

## 未做

- 未定位是哪一个早期迁移在旧库路径上把 `scenes` 表重命名/删除后未按预期重建；未修改任何迁移文件。
- 修复前请先确认 `345000649eb5_baseline_schema.py` 在旧库上的改名顺序，再决定是在 `a1b2c3d4e5f6` 增加表存在性守卫还是修正基线。
