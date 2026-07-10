import { authConfig, backendClient } from "@/lib/http/backend-client";
import type { UsageLogsResponse } from "@/types/usage";

export async function listUsageLogsByBff(feature: string, days: number, authorization?: string) {
  const response = await backendClient.get<UsageLogsResponse>("/api/usage/logs", {
    ...(authConfig(authorization) ?? {}),
    params: { feature, days },
  });
  return response.data;
}
