export type ModelOption = "qwen-plus" | "deepseek-chat" | "doubao-seed-1-6-250615" | "gpt-4o-mini";

export type ConfigPurpose = "script" | "image" | "video";

export interface AuthUser {
  id: number;
  username: string;
  createdAt: string;
  updatedAt: string;
}

export interface AuthResponse {
  token: string;
  user: AuthUser;
}

export interface UserMeResponse {
  user: AuthUser;
}

export interface UserConfig {
  id: number;
  purpose: ConfigPurpose;
  provider: string;
  model: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface UserConfigListResponse {
  configs: UserConfig[];
}

export interface UserConfigItemResponse {
  config: UserConfig;
}

export interface CreateUserConfigInput {
  purpose: ConfigPurpose;
  provider: string;
  model: string;
  apiKey: string;
  isActive: boolean;
}
