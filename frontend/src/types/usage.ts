export interface UsageLogItem {
  id: string;
  createdAt: string;
  feature: string;
  source: "official" | "user";
  provider: string;
  model: string;
  durationMs: number;
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
  quantity: number;
  costMicros: number;
  pricingMultiplier: number;
  inputPricePerMillion: number;
  outputPricePerMillion: number;
  cacheReadPricePerMillion: number;
  cacheWritePricePerMillion: number;
  unitPrice: number;
  unitName: "token" | "request" | "image" | "second";
}

export interface UsageLogsResponse {
  summary: {
    calls: number;
    inputTokens: number;
    outputTokens: number;
    costMicros: number;
  };
  logs: UsageLogItem[];
}
