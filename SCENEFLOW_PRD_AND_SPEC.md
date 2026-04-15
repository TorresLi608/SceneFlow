```markdown
# SceneFlow (分镜流) - AI 漫剧可视化工作台 全栈技术规范

## 1. 产品概述 (Product Vision)
**定位**：一款面向自媒体创作者的“文本到漫剧”提效工作台。
**核心理念**：将繁琐的“剧本拆解、提示词编写、多模态生成（生图/TTS）”折叠进一个优雅的“分镜卡片流”中。支持多用户、自定义 API Key 及全局大模型切换。
**视觉风格**：极简、暗色模式为主（Dark Mode），注重骨架屏加载、平滑滚动与拖拽反馈。

## 2. 核心用户故事 (User Flow)
1. **鉴权与配置**：用户注册/登录。在“设置”页填入个人的第三方 AI API Key（将在后端 AES-256 加密存储）。在顶部导航栏选择本次生成使用的大模型（如 GPT-4o, DeepSeek-V3）。
2. **输入阶段**：新建 Project，输入故事剧本。
3. **解析阶段**：点击“智能分镜”，后端调用大模型解析文本，生成结构化的分镜卡片（Scene）。
4. **编排阶段**：工作台渲染卡片流。用户可拖拽排序，微调单张卡片的画面 Prompt 或旁白。
5. **并发生成**：用户点击“一键生成”，后端 Go 启动高并发 Goroutines，同时请求图文/音频接口。前端通过 WebSocket 接收实时进度条更新，UI 呈现优雅的 Loading 骨架动画。

## 3. 全栈技术选型 (Tech Stack)
### 3.1 Frontend (前端)
* **框架**：Next.js 16.x (App Router) / React 19+
* **语言**：TypeScript (严格模式)
* **UI/样式**：Tailwind CSS + shadcn/ui (Radix UI) + Lucide React (图标)
* **状态管理**：Zustand (持久化 UserStore + 会话级 ProjectStore)
* **核心交互库**：dnd-kit (卡片拖拽)

### 3.2 Backend (Go 后端)
* **语言与框架**：Go 1.21+ / Gin (Web 框架)
* **实时通信**：Gorilla WebSocket
* **数据库**：SQLite + GORM (V1 版本，便于本地极速启动)
* **安全**：golang-jwt/jwt (鉴权) + AES-256-GCM (API Key 加密)

## 4. 数据库与领域模型 (Data Models)

### 4.1 Go 后端 GORM 模型
```go
// User (用户与认证)
type User struct {
    gorm.Model
    Username string `gorm:"uniqueIndex"`
    Password string // bcrypt 哈希
    Configs  []UserConfig
}

// UserConfig (API配置，安全存储)
type UserConfig struct {
    gorm.Model
    UserID       uint
    Provider     string // "OpenAI", "DeepSeek", etc.
    EncryptedKey string // AES 加密存储的 Key
    IsActive     bool
}

// Project (漫剧项目)
type Project struct {
    gorm.Model
    ID             string `gorm:"primaryKey"`
    UserID         uint
    OriginalScript string `gorm:"type:text"`
    Status         string `gorm:"default:'idle'"` // idle, parsing, generating, done
    Scenes         []Scene `gorm:"foreignKey:ProjectID"`
}

// Scene (分镜片段)
type Scene struct {
    gorm.Model
    ID            string `gorm:"primaryKey"`
    ProjectID     string
    OrderNum      int
    Narration     string `gorm:"type:text"`
    VisualPrompt  string `gorm:"type:text"`
    ImageURL      string
    ImageStatus   string `gorm:"default:'idle'"` // idle, generating, success, error
    AudioURL      string
    AudioStatus   string `gorm:"default:'idle'"`
}
```

### 4.2 Frontend TypeScript 接口
```typescript
interface Scene {
  id: string;
  order: number;
  narration: string;
  visualPrompt: string;
  image: { url: string | null; status: 'idle' | 'generating' | 'success' | 'error'; progress: number; };
  audio: { url: string | null; status: 'idle' | 'generating' | 'success' | 'error'; duration: number; };
}
```

## 5. 核心架构与通讯协议 (Architecture & API)

### 5.1 RESTful API 概览 (需 Header 携带 Bearer JWT Token)
* `POST /api/auth/register` & `POST /api/auth/login`
* `POST /api/settings/keys` (保存/更新 API Key，后端需执行 AES 加密落库)
* `POST /api/projects/:id/parse` (触发剧本拆解)
* `POST /api/projects/:id/generate` (触发多模态生成，启动 Goroutines)

### 5.2 后端动态 Client 与任务调度 (Go 核心要求)
* **动态解密**：每次发起 AI 请求前，从 `UserConfig` 查出用户的 `EncryptedKey`，AES 解密后注入 HTTP Request Header。
* **并发控制**：在处理 `/generate` 接口时，必须使用 Goroutine 为每个 Scene 并发调用生图/TTS API，并用 `sync.WaitGroup` 或 Channel 控制最大并发数。

### 5.3 WebSocket 实时状态流协议
前端连接 `ws://domain/ws/projects/:id?token=xxx`。
后端下发的消息结构体规范：
```json
{
  "type": "SCENE_UPDATE",
  "projectId": "proj_123",
  "sceneId": "scene_456",
  "data": {
    "imageStatus": "generating",
    "imageProgress": 45,
    "imageUrl": null,
    "errorMsg": "" 
  }
}
```

## 6. AI 辅助开发执行路径 (Execution Phases)
请 AI 编程助手严格按照以下阶段按顺序执行，完成一个阶段并确认无误后，再进行下一阶段：

### Phase 1: 基础设施与认证中心 (Go 后端先行)
* **任务**：初始化 Go Mod，配置 Gin 路由，连接 SQLite (GORM)。
* **核心**：实现 JWT Middleware，编写 AES-256 加密/解密工具函数。完成 User 和 UserConfig 的 CRUD 接口。

### Phase 2: 前端基建与鉴权闭环 (Next.js)
* **任务**：初始化 Next.js + Tailwind + shadcn/ui。
* **核心**：创建 Zustand `userStore` (含持久化)。实现登录/注册页面，以及全局设置弹窗（输入 API Key 和选择 Model）。实现 Axios 请求拦截器自动注入 Token。

### Phase 3: 工作台静态 UI 与拖拽 (Next.js)
* **任务**：构建带侧边栏（剧本输入）和主工作区（卡片流）的 Layout。
* **核心**：集成 `dnd-kit`，实现 `SceneCard` 组件。通过 Zustand `projectStore` 管理卡片状态。此阶段使用 Mock 数据预览卡片排版。

### Phase 4: 后端大模型解析与 WebSocket 基建 (Go)
* **任务**：实现 `POST /api/projects/:id/parse` 接口。从数据库解密 Key，调用大模型（GPT-4o/DeepSeek 格式），要求严格输出 JSON，落库生成 Scene。
* **核心**：实现基于 Gorilla 的 WebSocket Hub 广播中心，处理客户端连接与心跳。

### Phase 5: 高并发调度与状态打通 (全栈合并)
* **任务**：实现后端的 `/generate` 接口，用 Goroutine 模拟调用生图和 TTS 接口（可先用 time.Sleep 模拟耗时）。
* **核心**：在 Goroutine 内部将进度不断推送到 Channel -> WebSocket 广播。前端 Zustand 监听到 WS 消息，更新对应卡片的 progress 和 status，UI 展示骨架屏和进度条动画。
```