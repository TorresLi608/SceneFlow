import { httpClient } from "@/lib/http/client";
import type {
  AdminDefaultModelItemResponse,
  AdminDefaultModelListResponse,
  AdminUsageLogListResponse,
  AdminUserItemResponse,
  AdminUserListResponse,
  CreateAdminUserInput,
  InvitationCodeDays,
  InvitationCodeItemResponse,
  InvitationCodeListResponse,
  CreateOfficialConfigInput,
  ResetAdminUserPasswordResponse,
  RedemptionCodeItemResponse,
  RedemptionCodeListResponse,
  RedemptionCodeStatus,
  UpdateOfficialConfigInput,
} from "@/types/admin";

export async function listAdminUsersAction() {
  const response = await httpClient.get<AdminUserListResponse>("/api/bff/admin/users");
  return response.data;
}

export async function listAdminUsageLogsAction(params: { search?: string; page?: number; pageSize?: number } = {}) {
  const response = await httpClient.get<AdminUsageLogListResponse>("/api/bff/admin/usage-logs", { params });
  return response.data;
}

export async function createAdminUserAction(payload: CreateAdminUserInput) {
  const response = await httpClient.post<AdminUserItemResponse>("/api/bff/admin/users", payload);
  return response.data;
}

export async function updateAdminUserAction(id: number, payload: { isDisabled?: boolean; level?: 1 | 2 | 3 }) {
  const response = await httpClient.patch<AdminUserItemResponse>(`/api/bff/admin/users/${id}`, payload);
  return response.data;
}

export async function resetAdminUserPasswordAction(id: number) {
  const response = await httpClient.post<ResetAdminUserPasswordResponse>(`/api/bff/admin/users/${id}`);
  return response.data;
}

export async function deleteAdminUserAction(id: number) {
  await httpClient.delete(`/api/bff/admin/users/${id}`);
}

export async function listInvitationCodesAction(params: { status?: string; search?: string; page?: number; pageSize?: number } = {}) {
  const response = await httpClient.get<InvitationCodeListResponse>("/api/bff/admin/invitation-codes", { params });
  return response.data;
}

export async function listRedemptionCodesAction(params: { status?: RedemptionCodeStatus | "all"; page?: number; pageSize?: number } = {}) {
  const response = await httpClient.get<RedemptionCodeListResponse>("/api/bff/admin/redemption-codes", { params });
  return response.data;
}

export async function createRedemptionCodeAction(payload: { amount: string; days: InvitationCodeDays }) {
  const response = await httpClient.post<RedemptionCodeItemResponse>("/api/bff/admin/redemption-codes", payload);
  return response.data;
}

export async function createInvitationCodeAction(days: InvitationCodeDays) {
  const response = await httpClient.post<InvitationCodeItemResponse>("/api/bff/admin/invitation-codes", { days });
  return response.data;
}

export async function listOfficialConfigsAction() {
  const response = await httpClient.get<AdminDefaultModelListResponse>("/api/bff/admin/default-models");
  return response.data;
}

export async function createOfficialConfigAction(payload: CreateOfficialConfigInput) {
  const response = await httpClient.post<AdminDefaultModelItemResponse>("/api/bff/admin/default-models", payload);
  return response.data;
}

export async function updateOfficialConfigAction(id: number, payload: UpdateOfficialConfigInput) {
  const response = await httpClient.patch<AdminDefaultModelItemResponse>(`/api/bff/admin/default-models/${id}`, payload);
  return response.data;
}

export async function deleteOfficialConfigAction(id: number) {
  await httpClient.delete(`/api/bff/admin/default-models/${id}`);
}

export async function updateModelConfigAction(id: number, payload: UpdateOfficialConfigInput & { source: "user" | "official" }) {
  const response = await httpClient.patch<AdminDefaultModelItemResponse>(`/api/bff/admin/model-configs/${id}`, payload);
  return response.data;
}
