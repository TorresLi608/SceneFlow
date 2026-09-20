export type GenerationHistoryKind = "image" | "video";

/** One standalone image/video result on the account's history, served by the backend. */
export interface GenerationHistoryItem {
  id: string;
  kind: GenerationHistoryKind;
  /** Signed media URL minted per response; null when the stored file is gone. */
  url: string | null;
  prompt: string;
  provider: string;
  model: string;
  source: string;
  options: Record<string, string | number | boolean>;
  createdAt: string | null;
}

export interface GenerationHistoryListResponse {
  items: GenerationHistoryItem[];
  /** Admin retention window for this kind in whole days; 0 means results are kept forever. */
  retentionDays: number;
}
