export interface UsageLogItem {
  id: string;
  createdAt: string;
  feature: string;
  source: "official" | "user";
  provider: string;
  configName: string;
  model: string;
  durationMs: number;
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
  quantity: number;
  costMicros: string;
  pricingMultiplier: string;
  inputPricePerMillion: string;
  outputPricePerMillion: string;
  cacheReadPricePerMillion: string;
  cacheWritePricePerMillion: string;
  unitPrice: string;
  unitName: "token" | "request" | "image" | "second";
}

export interface UsageLogsResponse {
  summary: {
    calls: number;
    inputTokens: number;
    outputTokens: number;
    costMicros: string;
  };
  logs: UsageLogItem[];
}
