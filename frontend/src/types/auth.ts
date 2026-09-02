export type ConfigPurpose = "general" | "script" | "image" | "video" | "audio";
export type PricingUnit = "token" | "request" | "image" | "second";

export interface VideoCapabilities {
  qualities: ("480p" | "720p" | "1080p" | "2K" | "4K")[];
  fps: (24 | 30 | 60)[];
  aspectRatios: ("21:9" | "16:9" | "4:3" | "1:1" | "3:4" | "9:16" | "adaptive")[];
  promptExtend: boolean;
  minDuration: number;
  maxDuration: number;
  referenceImages: boolean;
  referenceImagesRequired: boolean;
  maxReferenceImages: number;
  referenceVideo: boolean;
  maxReferenceVideos: number;
  referenceVideosRequired: boolean;
  referenceAudio: boolean;
  maxReferenceAudios: number;
  referenceAudiosRequired: boolean;
  audioParam?: "with_audio" | "audio" | "reference_voice" | null;
  audioDefault?: boolean;
  supportsStartEndFrames?: boolean;
  supportsFirstFrame?: boolean;
  supportsLastFrame?: boolean;
}

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
  nickname: string;
  email?: string;
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

export interface SendVerificationCodeInput {
  email: string;
}

export interface SendVerificationCodeResponse {
  success: boolean;
  cooldownSeconds: number;
  expiresInSeconds: number;
}

export interface RegisterInput {
  username: string;
  nickname?: string;
  email?: string;
  verificationCode?: string;
  password: string;
  invitationCode: string;
}

export interface UserMeResponse {
  user: AuthUser;
}

export interface UpdateMeInput {
  username?: string;
  nickname?: string;
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
  createdAt: string;
  updatedAt: string;
  imageMaxReferenceImages: number;
  videoCapabilities: VideoCapabilities | null;
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
  imageMaxReferenceImages?: number;
  videoCapabilities?: VideoCapabilities;
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
  imageMaxReferenceImages?: number;
  videoCapabilities?: VideoCapabilities;
}
