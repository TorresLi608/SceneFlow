# BUG-20260907-sqlite-persistence：SQLite 部署持久化路径与目录权限

- 首次记录：2026-09-07
- 最近更新：2026-09-07
- 状态：统一 DATABASE_URL、进程重启回归和本地数据迁移已验证；真实 Docker 重建待验证
- 检索词：SQLite、DATABASE_URL、SCENEFLOW_DB_PATH、Docker、重建丢数据、bind mount、WAL、目录权限

## 现象与复现

用户报告容器重新打包部署后数据丢失，要求数据库位于 `/app/data/app.db`、整个数据目录挂载到宿主机，并禁止将 SQLite 文件打包进镜像。

首轮排查未在本机复现部署现场：当时 Docker CLI 可用，但 Docker Desktop 引擎未启动，socket 不存在。不能据此断言用户的旧命名卷已被删除；首轮没有迁移真实数据。随后按用户明确要求完成了本地数据库迁移，见下方历史记录。

源码可确认的旧行为：直接运行后端镜像时，未配置 `SCENEFLOW_DB_PATH` 会使用工作目录下的 `./sceneflow.db`，即容器可写层中的 `/app/backend/sceneflow.db`；删除重建该容器不能保留这份文件。旧 Compose 则明确挂载了 `sceneflow_db:/app/backend/data` 并覆盖路径，普通 rebuild/down 本应保留该卷。具体部署是否使用 Compose、是否换了存储位置或删除卷，仍需现场证据。

## 根因与定位

- [配置](../../backend/app/core/config.py)：旧默认文件路径依赖工作目录，镜像自身没有持久化目录的默认连接 URL。
- [数据库共享入口](../../backend/app/core/database.py)：`engine()` / `_build_engine()` 在连接前未创建父目录；`db()`、FastAPI `lifespan` 的 `init_db()`、在线 Alembic 都经由此入口。测试还会直接替换 `database.DB_PATH`，需保留兼容。
- [Dockerfile](../../backend/Dockerfile) / [Compose](../../docker-compose.yml)：旧路径为 `/app/backend/data/sceneflow.db`。改成宿主机 bind mount 时，镜像内的 `chown` 会被挂载目录遮盖，Linux 新建宿主机目录的所有权可能导致 UID 10001 无法写库。
- [备份脚本](../../backup.sh)：旧版本只复制主数据库文件，未归档整个 SQLite 目录；需要兼容仍存在 WAL/SHM 文件的快照。
- 忽略规则只覆盖部分位置的 `.db`，未完整覆盖 SQLite sidecar 和数据目录。

## 修复与影响

1. 本地开发和部署仅使用 `DATABASE_URL`，未设置或为空时使用项目根目录 `data/app.db`；已按后续要求移除 `SCENEFLOW_DB_PATH` 兼容分支。镜像默认 `sqlite:////app/data/app.db`。使用 SQLAlchemy URL 解析；保留内存数据库的 `StaticPool`，文件库在建引擎前创建父目录。数据库文件权限仍为 `0600`。
2. Compose 将 `${SCENEFLOW_DATA_DIR:-./data}` 整个挂载到 `/app/data`。新增 [入口脚本](../../backend/docker-entrypoint.sh)，先修正专用数据目录的所有权/权限，再通过 `gosu` 以普通用户运行后端；不更换媒体卷。
3. Git 与后端/前端两个实际 Docker 构建上下文排除 `.db`、WAL/SHM/journal、数据库备份文件和数据目录。
4. 保留 `docker:up` 和 `docker:backup`：前者仍负责构建启动，后者仍提供恢复快照。备份改为归档整个 `data/` 加 `private_generated/`；启动状态的恢复逻辑保留。
5. 同次配置需求新增 `SCENEFLOW_SUPER_ADMIN_USERNAME`。新库使用配置名称；旧默认管理员原地改名，保留 ID、密码和归属。用户名冲突/非管理员占名会报错；已自定义账号后再改成一个不存在的名称不会偷偷创建第二个管理员。密码仍只在首次创建时使用。此项是新增配置能力，不另造 Bug 记录。
6. 测试 runner 覆盖唯一的 `DATABASE_URL`，防止默认路径或本地 `.env` 将测试导向真实库。没有模型/表结构变更，因此没有新增 Alembic revision 或改动 OpenAPI。

长期操作规则见[部署与迁移](../reference/local-setup.md#docker-deployment)、[管理员账号](../design/feature-auth.md#super-admin)、[环境变量](../../backend/README.md#environment)、[中文 README](../../README_zh.md) 和[英文 README](../../README.md)。新挂载目录不会自动导入旧库；升级前必须按文档复制/迁移，并保留原有加密密钥。应用启动不会自动迁移或删除旧存储；手动本地迁移步骤会在完整性检查通过后删除旧库。

## 验证

2026-09-07 首轮实现实际执行（移除旧变量前的历史验证；本轮结果见下方追加记录）：

```bash
cd backend
check_dir=$(mktemp -d)
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh test_database test_admin_users test_invitation_codes test_redemption_codes test_episodes_api test_project_guards
```

六个模块通过。`test_database` 覆盖默认/URL/旧路径优先级、内存库、目录缺失、配置校验、自定义管理员、占名拒绝、两个独立解释器开启 WAL 后的数据保留，以及默认管理员改名后旧登录失效、密码与 ID 保持、重复启动不增建账号。

- 在临时目录同时设置 `DATABASE_URL`、`SCENEFLOW_DB_PATH` 和 `SCENEFLOW_PRIVATE_GENERATED_DIR`，执行 `.venv/bin/alembic upgrade head` 与 `.venv/bin/alembic check`：通过，`No new upgrade operations detected.`；保留现有 SQLite 表达式索引近似签名警告。
- `docker compose config --quiet`：通过。另以 `docker compose config --format json` 检查默认和自定义 `SCENEFLOW_DATA_DIR` / `DATABASE_URL`，确认 `/app/data` 为 bind mount、解析路径正确、媒体卷仍在。
- 临时 Python 自检模拟 Docker CLI，使用真实含已提交 WAL 内容的 SQLite 文件运行 `backup.sh`：运行中、已停止、复制失败三种场景通过；归档含主库/WAL/SHM/媒体，解包后可读取 WAL 中的数据，复制失败后仍请求恢复后端。此项不是 Docker 引擎集成验证。
- `sh -n backup.sh backend/docker-entrypoint.sh backend/scripts/run_tests.sh`：通过。
- 文档校验：192 个本地链接目标、37 个 shell 代码块语法通过；两段迁移 Python 在临时 WAL 数据库上验证数据保留和禁止覆盖已有目标，其中 Docker 片段仅将容器路径映射到临时路径来检查 Python 逻辑，没有实际执行 Docker 命令。
- `git check-ignore --no-index -v` 检查根目录/后端/前端的数据库、sidecar 和数据目录样例：均被忽略；`git ls-files` 未发现仍在索引中的 SQLite 数据文件。
- `pnpm exec tsc --noEmit`：通过。
- `pnpm lint`：0 errors，1 个既有 warning（`use-unsaved-settings-check.ts` 中未使用的 `Project`）。

验证局限：

- `test_episode_migration` 单独复跑仍失败，具体为其最后一个只创建了配置/用户表的样例升级到后续引用 `scenes` 的 revision 时出现 `NoSuchTableError: scenes`。将本轮修改前 Git index 中的配置、数据库入口和迁移环境复制到临时源码目录后复跑，得到相同失败；未更改该既有问题，也不宣称迁移测试整模块通过。
- `docker info` 返回 Docker socket 不存在，故镜像构建、实际 UID/挂载权限、容器重建、Docker 卷迁移仍未执行。文档中的 Docker 步骤不能视为实测通过。
- 未执行生产部署、真实数据迁移或付费模型调用。

## 历史与关联

- 2026-09-07：本次修复与新增管理员配置；上述验证均为当日实际运行。代码已包含在本地提交 `dc3de00`，文档和忽略规则的最后验证记录随后补充。

### 2026-09-07：移除旧变量并迁移本地数据库

用户明确要求不再保留旧开发库及其配置兼容，本地开发统一使用 `DATABASE_URL`。确认兼容分支仅在 `app/core/config.py` 读取；启动、数据库共享入口和 Alembic 都沿用该配置。移除了运行时代码、测试、runner、环境示例和操作命令中的旧变量，更新本地 `.env` 的说明及相关文档。内部派生的 `DB_PATH` 仍由 URL 得到，供引擎和已有隔离测试使用。

实际数据迁移前，`data/app.db` 不存在，`backend/sceneflow.db` 无进程占用、无 SQLite sidecar，日志模式为 `delete`。通过排他创建目标文件、复制、校验后删除源文件完成迁移：

- 迁移前后 SHA-256 完全一致，双方 `PRAGMA integrity_check` 均为 `ok`。
- 24 张表、合计 416 条记录逐表核对一致，Alembic 版本保持 `a3f0c95d7e18`。
- 新库位于根目录 `data/app.db`，权限为 `0600`；旧文件已删除。媒体目录及加密配置未改动。
- 仅读取实际配置，从仓库根目录、`backend/` 和无关临时目录解析出的默认路径均为同一绝对路径；没有启动真实应用或 worker。

本轮实际验证：

```bash
cd backend
check_dir=$(mktemp -d)
SCENEFLOW_PRIVATE_GENERATED_DIR="$check_dir/media" sh scripts/run_tests.sh test_database test_episodes_api test_project_guards
schema_dir=$(mktemp -d)
DATABASE_URL="sqlite:///$schema_dir/check.db" SCENEFLOW_PRIVATE_GENERATED_DIR="$schema_dir/media" .venv/bin/alembic upgrade head
DATABASE_URL="sqlite:///$schema_dir/check.db" SCENEFLOW_PRIVATE_GENERATED_DIR="$schema_dir/media" .venv/bin/alembic check
cd ../frontend
pnpm exec tsc --noEmit
pnpm lint
```

三个后端模块、类型检查和 Alembic 检查通过，后者输出 `No new upgrade operations detected.`，仍有原有表达式索引近似签名警告。lint 为 0 errors、1 个既有 warning（`use-unsaved-settings-check.ts` 未使用的 `Project`）。更新后的配置自检覆盖未设置/空 URL、绝对/相对 URL、内存库及既有重启数据保留场景。

额外验证：操作文档的 shell 代码块和 `run_tests.sh` 语法通过；本地迁移片段在临时 WAL 数据库上验证了已提交数据保留、旧库/sidecar 清理、`0600` 权限以及拒绝覆盖已有目标。实际开发数据迁移只做只读校验，没有对其运行 schema 升级或业务测试。

本次未执行浏览器验收或真实 Docker 重建；首轮记录的 `test_episode_migration` 既有失败未在本轮复跑，也未宣称全量后端测试通过。
