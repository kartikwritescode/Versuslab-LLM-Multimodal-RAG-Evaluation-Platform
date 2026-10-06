import {
  DocumentDetail,
  DocumentItem,
  RaceDetailResponse,
  RaceEvent,
  RaceListResponse,
  RaceRequest,
} from "./types";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "");
const AUTH_TOKEN_KEY = "versuslab_auth_token";

/**
 * Reads the stored JWT access token from localStorage.
 */
export function getAuthToken(): string | null {
  if (typeof window !== "undefined") {
    return localStorage.getItem(AUTH_TOKEN_KEY);
  }
  return null;
}

/**
 * Stores the JWT access token in localStorage.
 */
export function setAuthToken(token: string): void {
  if (typeof window !== "undefined") {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  }
}

/**
 * Clears the stored JWT access token.
 */
export function clearAuthToken(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem(AUTH_TOKEN_KEY);
  }
}

/**
 * Returns request headers directly. Authentication is disabled so all requests work directly.
 */
export function getAuthHeaders(customHeaders: Record<string, string> = {}): Record<string, string> {
  return { ...customHeaders };
}

/**
 * Resolves the full URL for an API endpoint.
 * Defaults to NEXT_PUBLIC_API_BASE_URL if configured, otherwise proxies via Next.js /api/backend rewrite.
 */
export function getApiUrl(path: string): string {
  if (API_BASE) {
    return `${API_BASE}${path}`;
  }
  return `/api/backend${path.replace(/^\/api/, "")}`;
}

/**
 * Direct access mode: login is a no-op that returns an empty string.
 */
export async function login(_username: string, _password: string): Promise<string> {
  return "";
}

/**
 * Signals backend coordinator to cancel all running tasks for the specified race.
 */
export async function cancelRace(raceId: string): Promise<boolean> {
  try {
    const res = await fetch(getApiUrl(`/api/races/${raceId}/cancel`), {
      method: "POST",
      headers: getAuthHeaders(),
    });
    return res.ok;
  } catch (err) {
    console.error("Failed to cancel race:", err);
    return false;
  }
}

/**
 * Fetches a paginated list of past races ordered newest first.
 */
export async function fetchRaces(
  limit = 20,
  offset = 0
): Promise<RaceListResponse> {
  const res = await fetch(getApiUrl(`/api/races?limit=${limit}&offset=${offset}`), {
    headers: getAuthHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch races: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetches detailed info and all contender runs for a specific past race.
 */
export async function fetchRaceDetail(
  raceId: string
): Promise<RaceDetailResponse> {
  const res = await fetch(getApiUrl(`/api/races/${raceId}`), {
    headers: getAuthHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch race details: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Triggers blind LLM judging and faithfulness evaluation for a finished race.
 */
export async function evaluateRace(
  raceId: string
): Promise<{ race_id: string; evaluated: boolean; evaluations_count: number }> {
  const res = await fetch(getApiUrl(`/api/races/${raceId}/evaluate`), {
    method: "POST",
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const err = await res.json();
      msg = err.detail || msg;
    } catch {
      // ignore
    }
    throw new Error(msg || "Failed to evaluate race");
  }
  return res.json();
}

/**
 * Fetches the list of all uploaded documents.
 */
export async function fetchDocuments(): Promise<DocumentItem[]> {
  const res = await fetch(getApiUrl("/api/documents"), {
    headers: getAuthHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch documents: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetches ordered chunk previews for an ingested document.
 */
export async function fetchDocumentDetail(documentId: string): Promise<DocumentDetail> {
  const res = await fetch(getApiUrl(`/api/documents/${documentId}`), {
    headers: getAuthHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch document detail: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetches all available benchmark datasets.
 */
export async function fetchDatasets(): Promise<import("./types").BenchmarkDataset[]> {
  const res = await fetch(getApiUrl("/api/datasets"), {
    headers: getAuthHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch datasets: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetches detail and cases for a specific benchmark dataset.
 */
export async function fetchDatasetDetail(
  datasetId: string
): Promise<import("./types").BenchmarkDataset> {
  const res = await fetch(getApiUrl(`/api/datasets/${datasetId}`), {
    headers: getAuthHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch dataset detail: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Creates a new experiment.
 */
export async function createExperiment(payload: {
  name: string;
  dataset_id: string;
  models: string[];
  include_llm_judge?: boolean;
}): Promise<import("./types").ExperimentSummary> {
  const res = await fetch(getApiUrl("/api/experiments"), {
    method: "POST",
    headers: getAuthHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const err = await res.json();
      msg = err.detail || msg;
    } catch {
      // ignore
    }
    throw new Error(msg || "Failed to create experiment");
  }
  return res.json();
}

/**
 * Fetches all past experiments.
 */
export async function fetchExperiments(): Promise<import("./types").ExperimentSummary[]> {
  const res = await fetch(getApiUrl("/api/experiments"), {
    headers: getAuthHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch experiments: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetches metadata for a single experiment.
 */
export async function fetchExperimentDetail(
  experimentId: string
): Promise<import("./types").ExperimentSummary> {
  const res = await fetch(getApiUrl(`/api/experiments/${experimentId}`), {
    headers: getAuthHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch experiment detail: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Triggers execution of an experiment in the background.
 */
export async function runExperiment(
  experimentId: string
): Promise<{ experiment_id: string; status: string }> {
  const res = await fetch(getApiUrl(`/api/experiments/${experimentId}/run`), {
    method: "POST",
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const err = await res.json();
      msg = err.detail || msg;
    } catch {
      // ignore
    }
    throw new Error(msg || "Failed to launch experiment run");
  }
  return res.json();
}

/**
 * Polls status and progress for an experiment.
 */
export async function fetchExperimentStatus(
  experimentId: string
): Promise<{
  experiment_id: string;
  status: string;
  total_cases: number;
  completed_cases: number;
  current_case_id?: string | null;
  error?: string | null;
}> {
  const res = await fetch(getApiUrl(`/api/experiments/${experimentId}/status`), {
    headers: getAuthHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch experiment status: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetches the aggregated multi-model comparison results and Pareto tradeoff points.
 */
export async function fetchExperimentResults(
  experimentId: string
): Promise<import("./types").ExperimentResultsResponse> {
  const res = await fetch(getApiUrl(`/api/experiments/${experimentId}/results`), {
    headers: getAuthHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const err = await res.json();
      msg = err.detail || msg;
    } catch {
      // ignore
    }
    throw new Error(msg || "Failed to fetch experiment results");
  }
  return res.json();
}

/**
 * Uploads and ingests a .txt or .md file into pgvector.
 */
export async function uploadDocument(file: File): Promise<DocumentItem> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(getApiUrl("/api/documents"), {
    method: "POST",
    headers: getAuthHeaders(),
    body: formData,
  });

  if (!res.ok) {
    let msg = res.statusText;
    try {
      const err = await res.json();
      msg = err.detail || msg;
    } catch {
      // ignore
    }
    throw new Error(msg || "Failed to upload document");
  }

  return res.json();
}

/**
 * Starts a multi-model race and streams SSE events via fetch ReadableStream.
 * Handles network chunks splitting across arbitrary byte boundaries using a persistent buffer.
 */
export async function startRaceStream(
  request: RaceRequest,
  onEvent: (event: RaceEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const response = await fetch(getApiUrl("/api/races"), {
    method: "POST",
    headers: getAuthHeaders({
      "Content-Type": "application/json",
    }),
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    let errorDetail = `Status ${response.status}`;
    try {
      const errJson = await response.json();
      errorDetail = errJson.detail || JSON.stringify(errJson);
    } catch {
      try {
        errorDetail = await response.text();
      } catch {
        // Fall back to status
      }
    }
    throw new Error(errorDetail || "Failed to start race");
  }

  if (!response.body) {
    throw new Error("Response body is null");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        if (trimmed.startsWith("data:")) {
          const rawJson = trimmed.slice(5).trim();
          if (rawJson) {
            try {
              const event: RaceEvent = JSON.parse(rawJson);
              onEvent(event);
            } catch (err) {
              console.warn("Failed to parse SSE JSON frame:", rawJson, err);
            }
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
