import { httpClient } from "@/lib/http/client";
import type { UsageLogsResponse } from "@/types/usage";

export async function listUsageLogsAction(feature: string, days: number, source: "all" | "official" | "user") {
  const response = await httpClient.get<UsageLogsResponse>("/api/bff/usage/logs", { params: { feature, days, source } });
  return response.data;
}
