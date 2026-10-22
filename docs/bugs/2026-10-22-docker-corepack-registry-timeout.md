# BUG-20261022-docker-corepack-registry-timeout：Docker 构建下载 pnpm 超时

- 首次记录：2026-10-22
- 最近更新：2026-10-22
- 状态：已修改，Compose 配置及镜像源引导验证通过；完整容器构建待服务器验证
- 检索词：Docker、Corepack、pnpm-10.28.1.tgz、registry.npmjs.org、ETIMEDOUT、ENETUNREACH、NPM_REGISTRY、SCENEFLOW_NPM_REGISTRY

## 现象与复现

用户在 Linux 服务器执行 `docker compose build`，前端在 `deps` 阶段执行 `pnpm config set store-dir /pnpm/store && pnpm install --frozen-lockfile --prefer-offline` 时退出。日志显示 Node.js v22.23.4 下 Corepack 请求 `https://registry.npmjs.org/pnpm/-/pnpm-10.28.1.tgz`，IPv4 连接 `ETIMEDOUT`，IPv6 连接 `ENETUNREACH`。后端并行构建被取消；日志没有证明后端独立构建失败。

## 根因与定位

- 已确认：失败发生在 Corepack 获取 pnpm 的引导阶段，尚未执行依赖安装和 Next.js 编译。服务器构建网络无法连接该 npm 官方下载地址；具体出口/防火墙原因未确认。
- `frontend/Dockerfile` 未提供构建下载源配置。仅设置宿主机 pnpm registry 不能影响容器内 Corepack，而且 `pnpm config set` 自身就需要先启动 pnpm。
- 原 `build` 阶段重新从 Node 镜像开始，只复制依赖目录，未复用 `deps` 的 Corepack 下载缓存，可能再次触发 pnpm 下载。
- 与 [ERR_PNPM_IGNORED_BUILDS](2026-09-08-docker-pnpm-ignored-builds.md) 根因不同；当前已保留版本锁定及构建脚本白名单。

## 修复与影响

- `frontend/Dockerfile` 新增 `NPM_REGISTRY` 构建参数，默认仍为 npm 官方源，同时设置 `COREPACK_NPM_REGISTRY` 和 `npm_config_registry`，覆盖 pnpm 引导和依赖安装。
- `build` 阶段继承 `deps`，复用已安装的 pnpm 和 node_modules；运行时阶段保持独立。
- `docker-compose.yml` 将 `SCENEFLOW_NPM_REGISTRY` 传给构建参数。使用可访问的镜像源重试：`SCENEFLOW_NPM_REGISTRY=https://registry.npmmirror.com docker compose build frontend`。
- 不修改依赖版本、锁文件或应用数据。镜像源是否可达仍取决于服务器网络；Docker Hub、Debian/Python 下载源不在本次修改范围内。
- 操作说明维护在 [Docker 部署](../reference/local-setup.md#docker-deployment)。

## 验证

- `docker compose config --format json`：通过，默认前端构建参数为 `https://registry.npmjs.org`。
- `SCENEFLOW_NPM_REGISTRY=https://registry.npmmirror.com docker compose config --format json`：通过，断言镜像源传入 `frontend.build.args.NPM_REGISTRY`。
- 在 `frontend/`，使用全新临时缓存执行 `COREPACK_HOME=<temporary-dir> COREPACK_NPM_REGISTRY=https://registry.npmmirror.com npm_config_registry=https://registry.npmmirror.com corepack pnpm --version`：沙箱内 DNS 解析失败；获准在沙箱外联网重跑后通过，输出 `10.28.1`。本机测试使用 Node.js v24.13.0，未替代 Node 22 容器实测。
- `git diff --check`：通过。
- `docker info`：本机 Docker CLI 可用，但 daemon socket 不存在，无法执行完整镜像构建。没有启动或重建现有容器；服务器构建待实际重跑。
- 本次仅修改 Docker 构建配置和文档，未运行应用单测、前端类型检查或 lint。

## 历史与关联

- 2026-10-22：根据用户构建日志确认 Corepack 官方 registry 连接超时，补充可配置 registry 与构建阶段复用。
