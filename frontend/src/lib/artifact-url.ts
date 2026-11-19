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

const ARTIFACT_LINK_ORIGIN = /https?:\/\/[^\s/()<>"'\]]+\/api\/chat\/artifacts\//g;

/**
 * Rewrites signed artifact links embedded in free text (chat Markdown) to the same-origin BFF proxy.
 *
 * The backend bakes SCENEFLOW_PUBLIC_BASE_URL into every signed link, and chat messages persist that
 * text. When the variable is left at its loopback default (or changes after messages were stored),
 * the link points at an address the browser cannot reach. The page origin always can, and the BFF
 * fallback rewrite forwards the token unchanged. The result stays absolute so Markdown URL hardening
 * treats it exactly like the original link; an empty origin (server render) leaves the text alone.
 */
export function rewriteArtifactLinks(text: string, origin: string) {
  if (!origin || !text.includes("/api/chat/artifacts/")) {
    return text;
  }
  return text.replace(ARTIFACT_LINK_ORIGIN, `${origin.replace(/\/+$/, "")}/api/bff/chat/artifacts/`);
}
