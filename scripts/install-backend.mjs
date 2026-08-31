import { existsSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const venvDir = path.join(root, "backend", ".venv");
const python = process.platform === "win32"
  ? path.join(venvDir, "Scripts", "python.exe")
  : path.join(venvDir, "bin", "python");

if (!existsSync(python)) {
  const bootstrapCandidates = process.platform === "win32" ? ["python", "python3", "py"] : ["python", "python3"];
  const bootstrap = bootstrapCandidates.find((command) =>
    spawnSync(command, ["--version"], { stdio: "ignore" }).status === 0,
  );
  if (!bootstrap) {
    console.error("未找到 Python。请将 Python 加入 PATH 后重试，或在 Windows 使用 py 启动器。");
    process.exit(1);
  }
  const result = spawnSync(bootstrap, ["-m", "venv", venvDir], { stdio: "inherit" });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

const result = spawnSync(python, ["-m", "pip", "install", "-r", path.join(root, "backend", "requirements.txt")], {
  stdio: "inherit",
});
process.exit(result.status ?? 1);
