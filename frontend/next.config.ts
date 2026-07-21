import type { NextConfig } from "next";
import { codeInspectorPlugin } from "code-inspector-plugin";

const backendBaseURL =
  process.env.BACKEND_API_BASE_URL?.trim().replace(/\/$/, "") ||
  "http://127.0.0.1:8080";

const nextConfig: NextConfig = {
  reactCompiler: true,
  async rewrites() {
    return {
      fallback: [
        {
          source: "/api/bff/:path*",
          destination: `${backendBaseURL}/api/:path*`,
        },
      ],
    };
  },
  turbopack: {
    root: process.cwd(),
    rules:
      process.env.NODE_ENV === "development"
        ? codeInspectorPlugin({ bundler: "turbopack" })
        : {},
  },
};

export default nextConfig;
