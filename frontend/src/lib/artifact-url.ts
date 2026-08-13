export function artifactBffUrl(value: string) {
  try {
    const url = new URL(value, "http://sceneflow.local");
    const prefix = "/api/chat/artifacts/";
    if (url.pathname.startsWith(prefix)) {
      return `/api/bff/chat/artifacts/${url.pathname.slice(prefix.length)}${url.search}${url.hash}`;
    }
  } catch {
    // Keep malformed provider URLs unchanged so their existing error handling applies.
  }
  return value;
}
