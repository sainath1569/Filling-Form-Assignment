export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export function getWsBaseUrl(): string {
  const base = API_BASE.replace(/\/$/, "");
  if (base.startsWith("https://")) {
    return base.replace(/^https:/, "wss:");
  }
  return base.replace(/^http:/, "ws:");
}

export function getRunWebSocketUrl(runId: string): string {
  return `${getWsBaseUrl()}/ws/runs/${runId}`;
}
