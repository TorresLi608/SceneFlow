# BUG-20260908-docker-pnpm-ignored-builds：Docker 前端构建 ERR_PNPM_IGNORED_BUILDS

- 首次记录：2026-09-08
- 最近更新：2026-09-08
- 状态：已验证
- 检索词：ERR_PNPM_IGNORED_BUILDS、docker:build、Dockerfile、pnpm-workspace.yaml、allowBuilds、onlyBuiltDependencies、Corepack、pnpm 10

## 现象与复现
- **触发条件**：在仓库根目录执行 `pnpm run docker:build`（调用 `docker compose build`）。
- **实际表现**：前端镜像在 `deps` 构建阶段执行 `RUN pnpm install --frozen-lockfile` 时失败并退出（exit code 1），报错：
  ```
  Error: ERR_PNPM_IGNORED_BUILDS
    × installing dependencies
    ╰─▶ Ignored build scripts: node-pty@1.1.0, sharp@0.34.5, unrs-resolver@1.12.2
    help: Run "pnpm approve-builds" to pick which dependencies should be allowed to run scripts.
  ```
- **预期表现**：Docker 镜像能够顺利安装依赖并完成 Next.js 前端应用构建。

## 根因与定位
1. **缺少 `pnpm-workspace.yaml` 复制**：
   本地 `frontend/pnpm-workspace.yaml` 中配置了允许执行构建脚本的依赖名单：
   ```yaml
   allowBuilds:
     node-pty: true
     sharp: true
     unrs-resolver: true
   ```
   但 `frontend/Dockerfile` 的 `deps` 阶段仅执行了 `COPY package.json pnpm-lock.yaml ./`，未复制 `pnpm-workspace.yaml`，导致容器内执行 `pnpm install` 时缺少白名单配置。
2. **Corepack 版本未锁定**：
   `package.json` 中未设置 `packageManager`，容器内的 `corepack enable` 自动从网络拉取了最新版的 `pnpm 12.3.4`，脱离了项目约定的 `pnpm 10`。

## 修复与影响
1. 在 `frontend/Dockerfile` 中修改为 `COPY package.json pnpm-lock.yaml pnpm-workspace.yaml* ./`，确保构建阶段带有脚本批准白名单。
2. 在 `frontend/package.json` 和根目录 `package.json` 中添加 `"packageManager": "pnpm@10.28.1"`，锁定 Corepack 使用与开发环境一致的 pnpm 版本。
3. 在 `frontend/package.json` 中显式添加 `"pnpm": { "onlyBuiltDependencies": ["node-pty", "sharp", "unrs-resolver"] }` 配置，与 `pnpm-workspace.yaml` 互为备份。

## 验证
- [x] 本地执行 `pnpm --dir frontend install --frozen-lockfile`，顺利通过（Done in 839ms using pnpm v10.28.1）。
- [x] 本地执行 `pnpm exec tsc --noEmit`（前端），无错误顺利通过（exit code 0）。
- [x] 执行 `docker compose build frontend`，顺利完成依赖安装与 Next.js 独立产物构建打包（Done in 36s using pnpm v10.28.1, exit code 0）。
- [x] 执行完整构建 `pnpm run docker:build`（对应 `docker compose build`），后端和前端镜像全部构建成功（exit code 0）。

## 历史与关联
- 2026-09-08：首次定位并修复 `pnpm-workspace.yaml` 拷贝缺失与 packageManager 版本锁定问题。
