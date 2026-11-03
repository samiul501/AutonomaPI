import type { IngestSpecResponse, QuickEndpointDraft } from "./types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function wsUrlForRun(runId: string): string {
  const wsBase = API_BASE_URL.replace(/^http/, "ws");
  return `${wsBase}/ws/runs/${runId}`;
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: string };
    return data.detail ?? response.statusText;
  } catch {
    return response.statusText;
  }
}

export async function ingestSpecFromUrl(url: string): Promise<IngestSpecResponse> {
  const response = await fetch(`${API_BASE_URL}/api/specs/from-url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!response.ok) throw new Error(await readErrorDetail(response));
  return response.json();
}

export async function ingestSpecFromFile(file: File): Promise<IngestSpecResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/specs/from-file`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) throw new Error(await readErrorDetail(response));
  return response.json();
}

export async function ingestQuickBatch(
  drafts: QuickEndpointDraft[],
  token: string
): Promise<IngestSpecResponse> {
  const endpoints = drafts.map((draft) => ({
    method: draft.method === "auto" ? null : draft.method,
    url: draft.url.trim(),
    body_example: draft.bodyText.trim() ? JSON.parse(draft.bodyText) : null,
    public: draft.public,
  }));

  const response = await fetch(`${API_BASE_URL}/api/specs/quick`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token: token.trim() || null, endpoints }),
  });
  if (!response.ok) throw new Error(await readErrorDetail(response));
  return response.json();
}

export async function startRun(
  specId: string,
  credentials: Record<string, string>
): Promise<{ run_id: string }> {
  const response = await fetch(`${API_BASE_URL}/api/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ spec_id: specId, credentials }),
  });
  if (!response.ok) throw new Error(await readErrorDetail(response));
  return response.json();
}
