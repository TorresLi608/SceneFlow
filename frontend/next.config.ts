import type { NextConfig } from "next";
import { codeInspectorPlugin } from 'code-inspector-plugin'

const nextConfig: NextConfig = {
  reactCompiler: true,
  turbopack: {
    root: process.cwd(),
    rules: codeInspectorPlugin({
      bundler: 'turbopack',
    })
  },
};

export default nextConfig;
