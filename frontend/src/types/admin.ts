import type { AuthUser, CreateUserConfigInput, UpdateUserConfigInput, UserConfig, UserConfigItemResponse } from "@/types/auth";

export interface AdminUserListResponse {
  users: AuthUser[];
}

export interface AdminUserItemResponse {
  user: AuthUser;
}

export interface CreateAdminUserInput {
  username: string;
  password: string;
  level?: 1 | 2 | 3;
}

export interface ResetAdminUserPasswordResponse {
  password: string;
}

export type InvitationCodeStatus = "unused" | "expired" | "used";
export type InvitationCodeDays = 1 | 7 | 30;

export interface InvitationCode {
  id: number;
  code: string;
  status: InvitationCodeStatus;
  createdAt: string;
  expiresAt: string;
  usedAt: string | null;
  usedBy: { id: number; username: string } | null;
}

export interface InvitationCodeListResponse {
  invitationCodes: InvitationCode[];
  pagination: Pagination;
}

export interface InvitationCodeItemResponse {
  invitationCode: InvitationCode;
}

export interface Pagination {
  total: number;
  page: number;
  pageSize: number;
  pageCount: number;
}

export type RedemptionCodeStatus = "unused" | "expired" | "redeemed";

export interface RedemptionCode {
  id: number;
  code: string;
  status: RedemptionCodeStatus;
  amountMicros: number;
  createdAt: string;
  expiresAt: string;
  redeemedAt: string | null;
  redeemedBy: { id: number; username: string } | null;
}

export interface RedemptionCodeListResponse {
  redemptionCodes: RedemptionCode[];
  pagination: Pagination;
}

export interface RedemptionCodeItemResponse {
  redemptionCode: RedemptionCode;
}

export interface AdminDefaultModelListResponse {
  configs: UserConfig[];
}

export type CreateOfficialConfigInput = CreateUserConfigInput;
export type UpdateOfficialConfigInput = UpdateUserConfigInput;
export type AdminDefaultModelItemResponse = UserConfigItemResponse;
