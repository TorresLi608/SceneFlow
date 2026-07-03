import type {
  GenerateProjectInput,
  GenerateProjectResponse,
  GenerateVideoInput,
  GenerateVideoResponse,
  OptimizeProjectInput,
  OptimizeProjectResponse,
  ParseProjectInput,
  ParseProjectResponse,
  CreateProjectInput,
  ProjectItemResponse,
  ProjectListResponse,
  ReorderScenesInput,
  UpdateProjectInput,
  UpdateSceneInput,
} from "@/types/project";
import { backendClient } from "@/lib/http/backend-client";

export async function getProjectsByBff(authorization?: string) {
  const response = await backendClient.get<ProjectListResponse>("/api/projects", {
    headers: {
      Authorization: authorization,
    },
  });

  return response.data;
}

export async function createProjectByBff(payload: CreateProjectInput, authorization?: string) {
  const response = await backendClient.post<ProjectItemResponse>("/api/projects", payload, {
    headers: {
      Authorization: authorization,
    },
  });

  return response.data;
}

export async function updateProjectByBff(projectID: string, payload: UpdateProjectInput, authorization?: string) {
  const response = await backendClient.patch<ProjectItemResponse>(`/api/projects/${projectID}`, payload, {
    headers: {
      Authorization: authorization,
    },
  });

  return response.data;
}

export async function updateProjectSceneByBff(
  projectID: string,
  sceneID: string,
  payload: UpdateSceneInput,
  authorization?: string
) {
  const response = await backendClient.patch(`/api/projects/${projectID}/scenes/${sceneID}`, payload, {
    headers: {
      Authorization: authorization,
    },
  });

  return response.data;
}

export async function reorderProjectScenesByBff(
  projectID: string,
  payload: ReorderScenesInput,
  authorization?: string
) {
  const response = await backendClient.patch<ProjectItemResponse>(`/api/projects/${projectID}/scenes/reorder`, payload, {
    headers: {
      Authorization: authorization,
    },
  });

  return response.data;
}

export async function parseProjectByBff(
  projectID: string,
  payload: ParseProjectInput,
  authorization?: string
) {
  const response = await backendClient.post<ParseProjectResponse>(`/api/projects/${projectID}/parse`, payload, {
    headers: {
      Authorization: authorization,
    },
  });

  return response.data;
}

export async function generateProjectByBff(
  projectID: string,
  payload: GenerateProjectInput,
  authorization?: string
) {
  const response = await backendClient.post<GenerateProjectResponse>(
    `/api/projects/${projectID}/generate`,
    payload,
    {
      headers: {
        Authorization: authorization,
      },
    }
  );

  return response.data;
}

export async function optimizeProjectByBff(
  projectID: string,
  payload: OptimizeProjectInput,
  authorization?: string
) {
  const response = await backendClient.post<OptimizeProjectResponse>(
    `/api/projects/${projectID}/optimize`,
    payload,
    {
      headers: {
        Authorization: authorization,
      },
    }
  );

  return response.data;
}

export async function generateVideoByBff(
  projectID: string,
  payload: GenerateVideoInput,
  authorization?: string
) {
  const response = await backendClient.post<GenerateVideoResponse>(
    `/api/projects/${projectID}/generate-video`,
    payload,
    {
      headers: {
        Authorization: authorization,
      },
    }
  );

  return response.data;
}

export async function deleteProjectByBff(projectID: string, authorization?: string) {
  await backendClient.delete(`/api/projects/${projectID}`, {
    headers: {
      Authorization: authorization,
    },
  });

  return {
    projectId: projectID,
    deleted: true,
  };
}
