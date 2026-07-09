import { httpClient } from "@/lib/http/client";
import type {
  CreateUserConfigInput,
  UpdateUserConfigInput,
  UserConfigItemResponse,
  UserConfigListResponse,
} from "@/types/auth";

export async function listUserConfigsAction() {
  const response = await httpClient.get<UserConfigListResponse>("/api/bff/settings/keys");
  return response.data;
}

export async function createUserConfigAction(payload: CreateUserConfigInput) {
  const response = await httpClient.post<UserConfigItemResponse>("/api/bff/settings/keys", payload);
  return response.data;
}

export async function updateUserConfigAction(id: number, payload: UpdateUserConfigInput) {
  const response = await httpClient.patch<UserConfigItemResponse>(`/api/bff/settings/keys/${id}`, payload);
  return response.data;
}

export async function deleteUserConfigAction(id: number) {
  await httpClient.delete(`/api/bff/settings/keys/${id}`);
}

export async function activateOfficialConfigAction(id: number) {
  const response = await httpClient.post<UserConfigItemResponse>(`/api/bff/settings/official/${id}/activate`);
  return response.data;
}
