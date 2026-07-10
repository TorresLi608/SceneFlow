import type { ReactNode } from "react";

import { WorkspaceShell } from "./_components/workspace-shell";

export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  return <WorkspaceShell>{children}</WorkspaceShell>;
}
