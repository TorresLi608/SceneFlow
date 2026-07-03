# SceneFlow 前后端运行文档

## 环境要求

- Python 3.11
- Node.js 20+ / npm

## 1. 启动后端

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8080
```

后端默认地址：

- API: `http://127.0.0.1:8080`
- 健康检查: `http://127.0.0.1:8080/healthz`
- WebSocket: `ws://127.0.0.1:8080`

启动成功后，访问健康检查应返回：

```json
{"status":"ok"}
```

后端会在启动时初始化 SQLite 数据库，并创建默认超级管理员：

- 账号: `superAdmin`
- 密码: `superAdmin@123`

## 2. 配置前端环境变量

```bash
cd frontend
cp .env.example .env.local
```

`.env.local` 默认内容可保持如下：

```env
NEXT_PUBLIC_BFF_BASE_URL=
NEXT_PUBLIC_WS_BASE_URL=ws://127.0.0.1:8080
BACKEND_API_BASE_URL=http://127.0.0.1:8080
```

说明：

- `NEXT_PUBLIC_BFF_BASE_URL` 为空时，前端会请求 Next.js 本地 BFF 路由。
- `BACKEND_API_BASE_URL` 是 Next.js BFF 转发到后端 FastAPI 的地址。
- `NEXT_PUBLIC_WS_BASE_URL` 是浏览器连接后端 WebSocket 的地址。

## 3. 启动前端

新开一个终端：

```bash
cd frontend
npm install
npm run dev
```

前端默认地址：

- `http://localhost:3000`

## 4. 本地验证流程

1. 先启动后端，确认 `http://127.0.0.1:8080/healthz` 返回 `{"status":"ok"}`。
2. 再启动前端，打开 `http://localhost:3000`。
3. 使用 `superAdmin` / `superAdmin@123` 登录。
4. 如需普通用户，可在注册页创建新账号。

## 常见问题

### 前端请求后端失败

确认后端运行在 `8080` 端口，并检查 `frontend/.env.local`：

```env
BACKEND_API_BASE_URL=http://127.0.0.1:8080
NEXT_PUBLIC_WS_BASE_URL=ws://127.0.0.1:8080
```

修改 `.env.local` 后需要重启前端开发服务。

### 端口被占用

后端可换端口启动：

```bash
cd backend
PORT=8090 python -m uvicorn app:app --host 0.0.0.0 --port 8090
```

同时修改 `frontend/.env.local`：

```env
BACKEND_API_BASE_URL=http://127.0.0.1:8090
NEXT_PUBLIC_WS_BASE_URL=ws://127.0.0.1:8090
```

### 重新初始化本地数据

后端默认数据库文件在 `backend/sceneflow.db`。需要清空本地开发数据时，停止后端后删除该文件，再重新启动后端。

## 生产构建

前端构建：

```bash
cd frontend
npm run build
npm run start
```

后端生产运行仍可使用 uvicorn：

```bash
cd backend
source .venv/bin/activate
python -m uvicorn app:app --host 0.0.0.0 --port 8080
```
