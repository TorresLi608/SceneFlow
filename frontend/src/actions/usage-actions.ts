import { httpClient } from "@/lib/http/client";
import type { TimeRangeParams } from "@/lib/date-time-range";
import type { UsageLogsResponse } from "@/types/usage";

export async function listUsageLogsAction(feature: string, range: TimeRangeParams, source: "all" | "official" | "user") {
  const response = await httpClient.get<UsageLogsResponse>("/api/bff/usage/logs", { params: { feature, ...range, source } });
  return response.data;
}
