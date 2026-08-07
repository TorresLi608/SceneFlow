export type ConfigPurpose = "general" | "script" | "image" | "video" | "audio";
export type PricingUnit = "token" | "request" | "image" | "second";

export interface ModelPricing {
  pricingMultiplier: string;
  inputPricePerMillion: string;
  outputPricePerMillion: string;
  cacheReadPricePerMillion: string;
  cacheWritePricePerMillion: string;
  unitPrice: string;
  unitName: PricingUnit;
}

export interface AuthUser {
  id: number;
  username: string;
  role: "user" | "superAdmin";
  isDisabled: boolean;
  balanceMicros: string;
  level: 1 | 2 | 3;
  group: string;
  historicalCostMicros: string;
  requestCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface AuthResponse {
  token: string;
  user: AuthUser;
}

export interface RegisterInput {
  username: string;
  password: string;
  invitationCode: string;
}

export interface UserMeResponse {
  user: AuthUser;
}

export interface UpdateMeInput {
  username?: string;
  password?: string;
}

export interface RedeemCodeResponse {
  amountMicros: string;
  user: AuthUser;
}

export interface UserConfig extends ModelPricing {
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
  isEnabled: boolean;
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

export interface ModelListResponse {
  models: string[];
}

export interface ModelSecretResponse {
  apiKey: string;
}

export interface CreateUserConfigInput extends Partial<ModelPricing> {
  name?: string;
  description?: string;
  purpose: ConfigPurpose;
  provider: string;
  baseUrl?: string;
  modelSeries: string;
  apiKey: string;
  isActive: boolean;
  isEnabled?: boolean;
}

export interface UpdateUserConfigInput extends Partial<ModelPricing> {
  name?: string;
  description?: string;
  purpose?: ConfigPurpose;
  provider?: string;
  baseUrl?: string;
  modelSeries?: string;
  apiKey?: string;
  isActive?: boolean;
  isEnabled?: boolean;
}
