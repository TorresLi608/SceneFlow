import { httpClient } from "@/lib/http/client";
import type {
  CreateUserConfigInput,
  ModelListResponse,
  ModelSecretResponse,
  UpdateUserConfigInput,
  UserConfigItemResponse,
  UserConfigListResponse,
} from "@/types/auth";

export async function listUserConfigsAction() {
  const response = await httpClient.get<UserConfigListResponse>("/api/bff/settings/keys");
  return response.data;
}

export async function getVideoModelCatalogAction() {
  const response = await httpClient.get<{ models: { model: string; provider: string; capabilities: import("@/types/auth").VideoCapabilities }[] }>("/api/bff/settings/video-models");
  return response.data;
}

export async function discoverModelsAction(payload: { provider: string; baseUrl: string; apiKey: string }) {
  const response = await httpClient.post<ModelListResponse>("/api/bff/settings/models", payload);
  return response.data;
}

export async function getUserConfigSecretAction(id: number) {
  const response = await httpClient.post<ModelSecretResponse>(`/api/bff/settings/keys/${id}/secret`);
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
