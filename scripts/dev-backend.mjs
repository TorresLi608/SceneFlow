import { existsSync } from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

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

const child = spawn(
  python,
  ["-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"],
  {
    cwd: backendDir,
    stdio: "inherit",
    env: {
      ...process.env,
      PYTHONUNBUFFERED: "1",
    },
  }
);

const handleSignal = (signal) => {
  if (child.pid && !child.killed) {
    try {
      child.kill(signal);
    } catch {
      // process already exited
    }
  }
};

process.on("SIGINT", () => handleSignal("SIGINT"));
process.on("SIGTERM", () => handleSignal("SIGTERM"));

child.on("exit", (code) => {
  process.exit(code ?? 0);
});
