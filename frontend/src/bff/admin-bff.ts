import { backendClient } from "@/lib/http/backend-client";
import type {
  AdminDefaultModelItemResponse,
  AdminDefaultModelListResponse,
  AdminUserItemResponse,
  AdminUserListResponse,
  CreateOfficialConfigInput,
  UpdateOfficialConfigInput,
} from "@/types/admin";

export async function listAdminUsersByBff(authorization?: string) {
  const response = await backendClient.get<AdminUserListResponse>("/api/admin/users", {
    headers: { Authorization: authorization },
  });
  return response.data;
}

export async function updateAdminUserByBff(id: number, payload: { isDisabled: boolean }, authorization?: string) {
  const response = await backendClient.patch<AdminUserItemResponse>(`/api/admin/users/${id}`, payload, {
    headers: { Authorization: authorization },
  });
  return response.data;
}

export async function deleteAdminUserByBff(id: number, authorization?: string) {
  await backendClient.delete(`/api/admin/users/${id}`, {
    headers: { Authorization: authorization },
  });
}

export async function listOfficialConfigsByBff(authorization?: string) {
  const response = await backendClient.get<AdminDefaultModelListResponse>("/api/admin/default-models", {
    headers: { Authorization: authorization },
  });
  return response.data;
}

export async function createOfficialConfigByBff(payload: CreateOfficialConfigInput, authorization?: string) {
  const response = await backendClient.post<AdminDefaultModelItemResponse>("/api/admin/default-models", payload, {
    headers: { Authorization: authorization },
  });
  return response.data;
}

export async function updateOfficialConfigByBff(id: number, payload: UpdateOfficialConfigInput, authorization?: string) {
  const response = await backendClient.patch<AdminDefaultModelItemResponse>(`/api/admin/default-models/${id}`, payload, {
    headers: { Authorization: authorization },
  });
  return response.data;
}

export async function deleteOfficialConfigByBff(id: number, authorization?: string) {
  await backendClient.delete(`/api/admin/default-models/${id}`, {
    headers: { Authorization: authorization },
  });
}
