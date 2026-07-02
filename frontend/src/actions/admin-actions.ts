import { httpClient } from "@/lib/http/client";
import type {
  AdminDefaultModelItemResponse,
  AdminDefaultModelListResponse,
  AdminUserItemResponse,
  AdminUserListResponse,
  CreateOfficialConfigInput,
  UpdateOfficialConfigInput,
} from "@/types/admin";

export async function listAdminUsersAction() {
  const response = await httpClient.get<AdminUserListResponse>("/api/bff/admin/users");
  return response.data;
}

export async function updateAdminUserAction(id: number, payload: { isDisabled: boolean }) {
  const response = await httpClient.patch<AdminUserItemResponse>(`/api/bff/admin/users/${id}`, payload);
  return response.data;
}

export async function deleteAdminUserAction(id: number) {
  await httpClient.delete(`/api/bff/admin/users/${id}`);
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
