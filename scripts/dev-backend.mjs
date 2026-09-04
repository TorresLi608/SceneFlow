import { existsSync } from "node:fs";
import path from "node:path";
import { spawn, execSync } from "node:child_process";

const root = process.cwd();
const backendDir = path.join(root, "backend");
const venvDir = path.join(backendDir, ".venv");
const python = process.platform === "win32"
  ? path.join(venvDir, "Scripts", "python.exe")
  : path.join(venvDir, "bin", "python");

if (!existsSync(python)) {
  console.error("未找到 Python 虚拟环境，请先运行: pnpm run install:backend");
  process.exit(1);
}

const port = process.env.PORT || "8080";

// 启动前检查并释放已被占用的端口（防止 VS Code 重启/重试任务时遗留孤儿进程）
const freePort = (targetPort) => {
  try {
    if (process.platform === "win32") {
      const output = execSync(`netstat -ano -p tcp | findstr :${targetPort}`, {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "ignore"],
      });
      const pids = new Set();
      for (const line of output.trim().split("\n")) {
        const parts = line.trim().split(/\s+/);
        if (parts.length >= 5 && parts[1].endsWith(`:${targetPort}`) && parts[3] === "LISTENING") {
          const pid = parts[parts.length - 1];
          if (pid && pid !== "0" && pid !== String(process.pid)) {
            pids.add(pid);
          }
        }
      }
      for (const pid of pids) {
        console.log(`[dev-backend] 检测到端口 ${targetPort} 被 PID ${pid} 占用，正在释放...`);
        try {
          execSync(`taskkill /F /PID ${pid}`, { stdio: "ignore" });
        } catch {}
      }
    } else {
      const output = execSync(`lsof -ti :${targetPort}`, {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "ignore"],
      }).trim();
      if (output) {
        const pids = output.split(/\s+/).filter((p) => p && p !== String(process.pid));
        for (const pid of pids) {
          console.log(`[dev-backend] 检测到端口 ${targetPort} 被 PID ${pid} 占用，正在释放...`);
          try {
            process.kill(Number(pid), "SIGKILL");
          } catch {}
        }
      }
    }
  } catch {
    // 端口未被占用或查询失败时安全忽略
  }
};

freePort(port);
// 等待操作系统完成套接字回收
await new Promise((resolve) => setTimeout(resolve, 200));

const child = spawn(
  python,
  ["-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", String(port)],
  {
    cwd: backendDir,
    stdio: "inherit",
    env: {
      ...process.env,
      PYTHONUNBUFFERED: "1",
    },
  }
);

const killChild = () => {
  if (child.pid && !child.killed) {
    try {
      if (process.platform === "win32") {
        execSync(`taskkill /F /T /PID ${child.pid}`, { stdio: "ignore" });
      } else {
        child.kill("SIGKILL");
      }
    } catch {}
  }
};

const handleSignal = (signal) => {
  if (child.pid && !child.killed) {
    try {
      child.kill(signal);
    } catch {}
    setTimeout(() => {
      killChild();
      process.exit(1);
    }, 2000).unref();
  } else {
    process.exit(0);
  }
};

process.on("SIGINT", () => handleSignal("SIGINT"));
process.on("SIGTERM", () => handleSignal("SIGTERM"));
process.on("SIGHUP", () => handleSignal("SIGHUP"));
process.on("exit", killChild);

child.on("exit", (code) => {
  process.exit(code ?? 0);
});
