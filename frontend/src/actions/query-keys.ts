export const queryKeys = {
  me: ["me"] as const,
  userConfigs: ["user-configs"] as const,
  projectTemplates: ["project-templates"] as const,
  adminUsers: ["admin-users"] as const,
  officialConfigs: ["official-configs"] as const,
  chatSessions: ["chat-sessions"] as const,
  chatMessages: (sessionId: string | null) => ["chat-messages", sessionId] as const,
};
