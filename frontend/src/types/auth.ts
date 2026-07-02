export type ConfigPurpose = "script" | "image" | "video";

export interface AuthUser {
  id: number;
  username: string;
  role: "user" | "superAdmin";
  isDisabled: boolean;
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
  source: "user" | "official";
  name: string;
  description: string;
  purpose: ConfigPurpose;
  provider: string;
  baseUrl: string;
  modelSeries: string;
  model?: string;
  isActive: boolean;
  isVerified: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface UserConfigListResponse {
  configs: UserConfig[];
  officialConfigs: UserConfig[];
}

export interface UserConfigItemResponse {
  config: UserConfig;
}

export interface CreateUserConfigInput {
  name?: string;
  description?: string;
  purpose: ConfigPurpose;
  provider: string;
  baseUrl?: string;
  modelSeries: string;
  apiKey: string;
  isActive: boolean;
}

export interface ValidateUserConfigInput {
  name?: string;
  description?: string;
  purpose: ConfigPurpose;
  provider: string;
  baseUrl?: string;
  modelSeries: string;
  apiKey: string;
}

export interface UpdateUserConfigInput {
  name?: string;
  description?: string;
  purpose?: ConfigPurpose;
  provider?: string;
  baseUrl?: string;
  modelSeries?: string;
  apiKey?: string;
  isActive?: boolean;
}

export interface ValidateUserConfigResponse {
  valid: boolean;
  purpose: ConfigPurpose;
  provider: string;
  baseUrl?: string;
  modelSeries: string;
  model?: string;
}
