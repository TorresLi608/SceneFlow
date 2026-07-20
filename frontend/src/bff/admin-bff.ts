import { authConfig, backendClient } from "@/lib/http/backend-client";
import type {
  AdminDefaultModelItemResponse,
  AdminDefaultModelListResponse,
  AdminUserItemResponse,
  AdminUserListResponse,
  CreateAdminUserInput,
  InvitationCodeDays,
  InvitationCodeItemResponse,
  InvitationCodeListResponse,
  CreateOfficialConfigInput,
  ResetAdminUserPasswordResponse,
  UpdateOfficialConfigInput,
} from "@/types/admin";

export async function listAdminUsersByBff(authorization?: string) {
  const response = await backendClient.get<AdminUserListResponse>("/api/admin/users", authConfig(authorization));
  return response.data;
}

export async function createAdminUserByBff(payload: CreateAdminUserInput, authorization?: string) {
  const response = await backendClient.post<AdminUserItemResponse>("/api/admin/users", payload, authConfig(authorization));
  return response.data;
}

export async function updateAdminUserByBff(id: number, payload: { isDisabled: boolean }, authorization?: string) {
  const response = await backendClient.patch<AdminUserItemResponse>(`/api/admin/users/${id}`, payload, authConfig(authorization));
  return response.data;
}

export async function resetAdminUserPasswordByBff(id: number, authorization?: string) {
  const response = await backendClient.post<ResetAdminUserPasswordResponse>(`/api/admin/users/${id}`, undefined, authConfig(authorization));
  return response.data;
}

export async function deleteAdminUserByBff(id: number, authorization?: string) {
  await backendClient.delete(`/api/admin/users/${id}`, authConfig(authorization));
}

export async function listInvitationCodesByBff(authorization?: string) {
  const response = await backendClient.get<InvitationCodeListResponse>("/api/admin/invitation-codes", authConfig(authorization));
  return response.data;
}

export async function createInvitationCodeByBff(days: InvitationCodeDays, authorization?: string) {
  const response = await backendClient.post<InvitationCodeItemResponse>("/api/admin/invitation-codes", { days }, authConfig(authorization));
  return response.data;
}

export async function listOfficialConfigsByBff(authorization?: string) {
  const response = await backendClient.get<AdminDefaultModelListResponse>("/api/admin/default-models", authConfig(authorization));
  return response.data;
}

export async function createOfficialConfigByBff(payload: CreateOfficialConfigInput, authorization?: string) {
  const response = await backendClient.post<AdminDefaultModelItemResponse>("/api/admin/default-models", payload, authConfig(authorization));
  return response.data;
}

export async function updateOfficialConfigByBff(id: number, payload: UpdateOfficialConfigInput, authorization?: string) {
  const response = await backendClient.patch<AdminDefaultModelItemResponse>(`/api/admin/default-models/${id}`, payload, authConfig(authorization));
  return response.data;
}

export async function deleteOfficialConfigByBff(id: number, authorization?: string) {
  await backendClient.delete(`/api/admin/default-models/${id}`, authConfig(authorization));
}
