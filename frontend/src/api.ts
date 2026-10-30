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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
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
