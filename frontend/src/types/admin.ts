import type { AuthUser, CreateUserConfigInput, UpdateUserConfigInput, UserConfig, UserConfigItemResponse } from "@/types/auth";

export interface AdminUserListResponse {
  users: AuthUser[];
}

export interface AdminUserItemResponse {
  user: AuthUser;
}

export interface AdminDefaultModelListResponse {
  configs: UserConfig[];
}

export type CreateOfficialConfigInput = CreateUserConfigInput;
export type UpdateOfficialConfigInput = UpdateUserConfigInput;
export type AdminDefaultModelItemResponse = UserConfigItemResponse;
