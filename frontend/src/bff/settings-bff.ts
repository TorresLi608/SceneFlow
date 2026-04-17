import type {
  CreateUserConfigInput,
  UpdateUserConfigInput,
  ValidateUserConfigInput,
  ValidateUserConfigResponse,
  UserConfigItemResponse,
  UserConfigListResponse,
} from "@/types/auth";
import { backendClient } from "@/lib/http/backend-client";

export async function getUserConfigsByBff(authorization?: string) {
  const response = await backendClient.get<UserConfigListResponse>("/api/settings/keys", {
    headers: {
      Authorization: authorization,
    },
  });

  return response.data;
}

export async function createUserConfigByBff(
  payload: CreateUserConfigInput,
  authorization?: string
) {
  const response = await backendClient.post<UserConfigItemResponse>("/api/settings/keys", payload, {
    headers: {
      Authorization: authorization,
    },
  });

  return response.data;
}

export async function validateUserConfigByBff(
  payload: ValidateUserConfigInput,
  authorization?: string
) {
  const response = await backendClient.post<ValidateUserConfigResponse>(
    "/api/settings/keys/validate",
    payload,
    {
      headers: {
        Authorization: authorization,
      },
    }
  );

  return response.data;
}

export async function updateUserConfigByBff(
  id: number,
  payload: UpdateUserConfigInput,
  authorization?: string
) {
  const response = await backendClient.patch<UserConfigItemResponse>(`/api/settings/keys/${id}`, payload, {
    headers: {
      Authorization: authorization,
    },
  });

  return response.data;
}

export async function deleteUserConfigByBff(id: number, authorization?: string) {
  await backendClient.delete(`/api/settings/keys/${id}`, {
    headers: {
      Authorization: authorization,
    },
  });
}
