export interface Source {
  ref: number;
  file_path: string;
  start_line: number;
  end_line: number;
  symbol: string;
  kind: string;
  language: string;
  score: number;
  text: string;
}

export interface QueryResponse {
  answer: string;
  sources: Source[];
}

export interface Health {
  status: "ok" | "degraded";
  ollama: { ok: boolean; llm_model?: string; embed_model?: string; missing_models?: string[]; error?: string };
  qdrant: { ok: boolean; collection?: string; indexed?: boolean; points?: number; error?: string };
  codebase_path: string;
  index_job: string;
}

export interface IndexStatus {
  state: "idle" | "running" | "done" | "error";
  full: boolean;
  started_at: string | null;
  finished_at: string | null;
  recent_progress: string[];
  report: {
    scanned: number;
    added: string[];
    updated: string[];
    deleted: string[];
    unchanged: number;
    skipped: string[];
    errors: Record<string, string>;
    chunks_written: number;
    duration_seconds: number;
  } | null;
  error: string | null;
}

const BASE = "/api";

/**
 * Where a failed request broke:
 * - "backend-timeout": the backend gave up waiting for Ollama (504 with a JSON detail)
 * - "gateway-timeout": a proxy in front of the backend gave up (nginx, or a port
 *   forwarder such as Codespaces): 504 without the backend's JSON body
 * - "network": the connection was dropped before any HTTP response arrived
 * - "http": any other error status
 */
export type ApiErrorKind = "backend-timeout" | "gateway-timeout" | "network" | "http";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly kind: ApiErrorKind,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isTimeout(): boolean {
    return this.kind !== "http";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (e) {
    throw new ApiError((e as Error).message || "連線中斷", "network");
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    let fromBackend = false;
    try {
      const body = await res.json();
      if (body?.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
        fromBackend = true;
      }
    } catch {
      /* not JSON: an error page from nginx or another proxy */
    }
    const kind: ApiErrorKind =
      res.status === 504 ? (fromBackend ? "backend-timeout" : "gateway-timeout") : "http";
    throw new ApiError(detail, kind, res.status);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),
  query: (question: string, top_k?: number) =>
    request<QueryResponse>("/query", { method: "POST", body: JSON.stringify({ question, top_k }) }),
  startIndex: (full: boolean) => request<IndexStatus>("/index", { method: "POST", body: JSON.stringify({ full }) }),
  indexStatus: () => request<IndexStatus>("/index/status"),
};
