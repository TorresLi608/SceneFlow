import axios from "axios";

/** One entry of FastAPI's validation error list. */
interface ValidationDetail {
  loc?: unknown[];
  msg?: string;
}

function readDetail(detail: unknown): string {
  if (typeof detail === "string") {
    return detail;
  }

  // FastAPI reports body validation failures as an array. The backend normalizes these into
  // `error`, but a proxy or a route without that handler can still surface the raw shape.
  if (Array.isArray(detail)) {
    return detail
      .map((item: ValidationDetail) => {
        const field = (item?.loc ?? [])
          .filter((part) => part !== "body" && part !== "query" && part !== "path")
          .join(".");
        const message = item?.msg ?? "";
        return field ? `${field}: ${message}` : message;
      })
      .filter(Boolean)
      .join("; ");
  }

  return "";
}

export function resolveRequestError(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data;
    const backendMessage = readDetail(data?.detail) || readDetail(data?.error);
    if (backendMessage.trim()) {
      return backendMessage;
    }

    if (typeof error.message === "string" && error.message.trim()) {
      return error.message;
    }
  }

  return fallback;
}
